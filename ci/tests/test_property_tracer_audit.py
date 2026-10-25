"""Tests for the read-only PropertyTracer source audit."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "browser" / "scripts" / "audit-property-tracer.py"
SPEC = importlib.util.spec_from_file_location("property_tracer_audit", SCRIPT)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


def _write_source(tmp_path: Path, files: dict[str, str], version: str = "158.0") -> Path:
    root = tmp_path / "source"
    (root / "browser" / "config").mkdir(parents=True)
    (root / "browser" / "config" / "version.txt").write_text(
        version + "\n", encoding="utf-8"
    )
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_manifest_keeps_all_77_sites_and_the_four_current_storage_entries():
    assert len(audit.SITES) == 77
    assert len({site.site_id for site in audit.SITES}) == 77
    assert {site.kind for site in audit.SITES} == {audit.GET, audit.SET, audit.CALL}
    kinds = [site.kind for site in audit.SITES]
    assert (kinds.count(audit.GET), kinds.count(audit.SET), kinds.count(audit.CALL)) == (
        51,
        1,
        25,
    )

    storage = [site for site in audit.SITES if site.object_name == "localStorage"]
    assert len(storage) == 4
    assert [site.property_name for site in storage].count("getItem") == 2
    assert [site.property_name for site in storage].count("setItem") == 2
    assert {site.path for site in storage} == {
        "dom/localstorage/LSObject.cpp",
        "dom/storage/PartitionedLocalStorage.cpp",
    }
    assert all(site.kind == audit.CALL for site in storage)


def test_ff158_signature_changes_are_pinned():
    signatures = {site.site_id: site.signature for site in audit.SITES}
    assert "nsACString" in signatures[
        "navigator.userAgent@dom/base/Navigator.cpp"
    ]
    assert "CallerType" in signatures[
        "window.innerWidth@dom/base/nsGlobalWindowInner.cpp"
    ]
    assert "CallerType" in signatures[
        "window.innerHeight@dom/base/nsGlobalWindowInner.cpp"
    ]


def test_default_source_path_follows_the_upstream_pin():
    version, release = audit._read_pin(ROOT / "browser")
    args = audit._parse_args([])

    assert args.expect_version == f"{version}-{release}"
    assert args.source == ROOT / "browser" / f"camoufox-{version}-{release}"


def test_audit_accepts_current_storage_definitions_without_writing(tmp_path):
    root = _write_source(
        tmp_path,
        {
            "dom/localstorage/LSObject.cpp": (
                "void LSObject::GetItem(const nsAString& aKey, nsAString& aResult,\n"
                "                       nsIPrincipal& aPrincipal, ErrorResult& aError) {\n"
                "}\n"
                "void LSObject::SetItem(const nsAString& aKey,\n"
                "                       const nsAString& aValue,\n"
                "                       nsIPrincipal& aPrincipal, ErrorResult& aError) {\n"
                "}\n"
            ),
            "dom/storage/PartitionedLocalStorage.cpp": (
                "void PartitionedLocalStorage::GetItem(\n"
                "    const nsAString& aKey, nsAString& aResult,\n"
                "    nsIPrincipal& aPrincipal, ErrorResult& aError) {}\n"
                "void PartitionedLocalStorage::SetItem(\n"
                "    const nsAString& aKey, const nsAString& aValue,\n"
                "    nsIPrincipal& aPrincipal, ErrorResult& aError) {}\n"
            ),
        },
    )
    before = {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    storage = tuple(site for site in audit.SITES if site.object_name == "localStorage")

    result = audit.audit_source(root, expect_version="158.0", sites=storage)

    assert result["ok"], result["errors"]
    assert result["verified"] == 4
    assert [site["line"] for site in result["sites"]] == [1, 4, 1, 4]
    assert len(result["sources"]) == 2
    assert all(
        len(source["sha256"]) == 64 and int(source["sha256"], 16) >= 0
        for source in result["sources"]
    )
    after = {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_audit_rejects_a_declaration_instead_of_a_definition(tmp_path):
    root = _write_source(
        tmp_path,
        {"dom/base/Test.cpp": "void Test::Read();\n"},
    )
    site = audit.Site("dom/base/Test.cpp", r"\bTest::Read\s*\(", "test", "read")

    result = audit.audit_source(root, expect_version="158.0", sites=(site,))

    assert not result["ok"]
    assert "matched a declaration, not a function body" in result["errors"][0]


def test_commented_code_is_not_counted_as_a_definition(tmp_path):
    root = _write_source(
        tmp_path,
        {"dom/base/Test.cpp": "/* int Test::Read() { return 1; } */\n"},
    )
    site = audit.Site("dom/base/Test.cpp", r"\bTest::Read\s*\(", "test", "read")

    result = audit.audit_source(root, expect_version="158.0", sites=(site,))

    assert not result["ok"]
    assert "found 0" in result["errors"][0]


def test_audit_rejects_legacy_localstorage_and_runtime_markers(tmp_path):
    root = _write_source(
        tmp_path,
        {
            "dom/storage/LocalStorage.cpp": (
                "void LocalStorage::GetItem() {}\n"
                "/* PropertyTracer injected: "
                "localStorage.getItem@dom/storage/LocalStorage.cpp */\n"
            ),
        },
    )
    site = audit.Site(
        "dom/storage/LocalStorage.cpp",
        r"\bLocalStorage::GetItem\s*\(",
        "localStorage",
        "getItem",
        audit.CALL,
    )

    result = audit.audit_source(root, expect_version="158.0", sites=(site,))

    assert not result["ok"]
    assert result["runtime_markers"]
    assert any("legacy LocalStorage path" in error for error in result["errors"])


def test_audit_rejects_compiled_runtime_tracer_sources(tmp_path):
    root = _write_source(
        tmp_path,
        {
            "camoucfg/PropertyTracer.cpp": '#include "PropertyTracer.hpp"\n',
            "camoucfg/MaskConfig.hpp": '#include "PropertyTracer.hpp"\n',
        },
    )

    result = audit.audit_source(root, expect_version="158.0", sites=())

    assert not result["ok"]
    assert result["runtime_tracer_sources"] == ["camoucfg/PropertyTracer.cpp"]
    assert result["runtime_markers"]


def test_audit_fails_closed_on_version_mismatch_and_path_escape(tmp_path):
    root = _write_source(tmp_path, {})
    site = audit.Site("../outside.cpp", r"\bOutside::Read\s*\(", "outside", "read")

    with pytest.raises(audit.AuditError, match="source path must stay"):
        audit.audit_source(root, expect_version="158.0", sites=(site,))

    result = audit.audit_source(root, expect_version="157.0", sites=())
    assert not result["ok"]
    assert "expected '157.0'" in result["errors"][0]


def test_cli_reports_machine_readable_results(tmp_path, capsys):
    root = _write_source(
        tmp_path,
        {"dom/base/Test.cpp": "int Test::Read() {\n  return 1;\n}\n"},
    )
    site = audit.Site("dom/base/Test.cpp", r"\bTest::Read\s*\(", "test", "read")

    old_sites = audit.SITES
    audit.SITES = (site,)
    try:
        assert audit.main(
            [str(root), "--expect-version", "158.0", "--json"]
        ) == 0
    finally:
        audit.SITES = old_sites

    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
    assert report["verified"] == 1
    assert report["sites"][0]["line"] == 1


def test_the_audit_is_not_part_of_the_browser_build():
    from ci.browser_inputs import NON_NATIVE_SCRIPTS

    relative = "browser/scripts/audit-property-tracer.py"
    assert relative in NON_NATIVE_SCRIPTS
    assert not (ROOT / "browser" / "additions" / "camoucfg" / "PropertyTracer.cpp").exists()
    assert not (ROOT / "browser" / "additions" / "camoucfg" / "PropertyTracer.hpp").exists()
    assert not list((ROOT / "browser" / "patches").glob("*property*tracer*"))
