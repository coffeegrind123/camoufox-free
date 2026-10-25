#!/usr/bin/env python3
"""Audit the native property surfaces formerly targeted by PropertyTracer.

This is a read-only source audit. It does not inject code, change config, run
Firefox, or create runtime trace files. Run it after the Firefox source tree
has been prepared with `make dir`; that command prepares sources, not a build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

GET = "get"
SET = "set"
CALL = "call"

RUNTIME_MARKERS = (
    "PropertyTracer injected:",
    "camou::PropertyTracer::Instance()",
    '#include "PropertyTracer.hpp"',
    "CAMOU_PROPERTY_TRACER",
    "inject-trace-to-source",
)
LEGACY_LOCAL_STORAGE_PATH = "dom/storage/LocalStorage.cpp"
RUNTIME_TRACER_PATHS = (
    "camoucfg/PropertyTracer.cpp",
    "camoucfg/PropertyTracer.hpp",
)
RUNTIME_SUPPORT_PATHS = (
    "camoucfg/MaskConfig.hpp",
    "camoucfg/moz.build",
)


@dataclass(frozen=True)
class Site:
    path: str
    signature: str
    object_name: str
    property_name: str
    kind: str = GET

    @property
    def site_id(self) -> str:
        return f"{self.object_name}.{self.property_name}@{self.path}"


# These signatures are native entry points, not page-visible JavaScript. Keep
# the list declarative so a Firefox source move is a reviewable one-line change.
SITES: tuple[Site, ...] = (
    Site("dom/base/Navigator.cpp", r"Navigator::GetUserAgent\s*\(\s*nsACString\s*&", "navigator", "userAgent"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::GetAppCodeName\s*\(", "navigator", "appCodeName"),
    Site("dom/base/Navigator.cpp", r"Navigator::GetAppVersion\s*\(\s*nsAString\s*&\s*aAppVersion\s*,\s*CallerType", "navigator", "appVersion"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::GetAppName\s*\(", "navigator", "appName"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::GetLanguage\s*\(", "navigator", "language"),
    Site("dom/base/Navigator.cpp", r"Navigator::GetPlatform\s*\(\s*nsAString\s*&\s*aPlatform\s*,\s*CallerType", "navigator", "platform"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::GetOscpu\s*\(", "navigator", "oscpu"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::GetProduct\s*\(", "navigator", "product"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::GetProductSub\s*\(", "navigator", "productSub"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::GetBuildID\s*\(", "navigator", "buildID"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::GetDoNotTrack\s*\(", "navigator", "doNotTrack"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::HardwareConcurrency\s*\(", "navigator", "hardwareConcurrency"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::MaxTouchPoints\s*\(", "navigator", "maxTouchPoints"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::CookieEnabled\s*\(", "navigator", "cookieEnabled"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::OnLine\s*\(", "navigator", "onLine"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::PdfViewerEnabled\s*\(", "navigator", "pdfViewerEnabled"),
    Site("dom/base/Navigator.cpp", r"\bNavigator::GlobalPrivacyControl\s*\(", "navigator", "globalPrivacyControl"),
    Site("dom/base/nsScreen.cpp", r"\bnsScreen::PixelDepth\s*\(", "screen", "pixelDepth"),
    Site("dom/base/nsScreen.cpp", r"\bnsScreen::GetRect\s*\(", "screen", "rect"),
    Site("dom/base/nsScreen.cpp", r"\bnsScreen::GetAvailRect\s*\(", "screen", "availRect"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"double\s+nsGlobalWindowInner::GetInnerWidth\s*\(\s*CallerType\s+", "window", "innerWidth"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"double\s+nsGlobalWindowInner::GetInnerHeight\s*\(\s*CallerType\s+", "window", "innerHeight"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"\bnsGlobalWindowInner::GetOuterWidth\s*\(", "window", "outerWidth"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"\bnsGlobalWindowInner::GetOuterHeight\s*\(", "window", "outerHeight"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"\bnsGlobalWindowInner::GetScreenX\s*\(", "window", "screenX"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"\bnsGlobalWindowInner::GetScreenY\s*\(", "window", "screenY"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"\bnsGlobalWindowInner::GetDevicePixelRatio\s*\(", "window", "devicePixelRatio"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"\bnsGlobalWindowInner::GetScrollMinX\s*\(", "window", "scrollMinX"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"\bnsGlobalWindowInner::GetScrollMinY\s*\(", "window", "scrollMinY"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"\bnsGlobalWindowInner::GetScrollMaxX\s*\(", "window", "scrollMaxX"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"\bnsGlobalWindowInner::GetScrollMaxY\s*\(", "window", "scrollMaxY"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"\bnsGlobalWindowInner::GetScrollX\s*\(", "window", "scrollX"),
    Site("dom/base/nsGlobalWindowInner.cpp", r"\bnsGlobalWindowInner::GetScrollY\s*\(", "window", "scrollY"),
    Site("dom/workers/WorkerNavigator.cpp", r"\bWorkerNavigator::GetUserAgent\s*\(", "navigator", "userAgent"),
    Site("dom/workers/WorkerNavigator.cpp", r"\bWorkerNavigator::GetAppVersion\s*\(", "navigator", "appVersion"),
    Site("dom/workers/WorkerNavigator.cpp", r"\bWorkerNavigator::GetPlatform\s*\(", "navigator", "platform"),
    Site("dom/workers/WorkerNavigator.cpp", r"\bWorkerNavigator::HardwareConcurrency\s*\(", "navigator", "hardwareConcurrency"),
    Site("dom/workers/WorkerNavigator.cpp", r"\bWorkerNavigator::GlobalPrivacyControl\s*\(", "navigator", "globalPrivacyControl"),
    Site("dom/base/nsHistory.cpp", r"\bnsHistory::GetLength\s*\(", "history", "length"),
    Site("dom/battery/BatteryManager.cpp", r"\bBatteryManager::Charging\s*\(", "battery", "charging"),
    Site("dom/battery/BatteryManager.cpp", r"\bBatteryManager::ChargingTime\s*\(", "battery", "chargingTime"),
    Site("dom/battery/BatteryManager.cpp", r"\bBatteryManager::DischargingTime\s*\(", "battery", "dischargingTime"),
    Site("dom/battery/BatteryManager.cpp", r"\bBatteryManager::Level\s*\(", "battery", "level"),
    Site("dom/canvas/CanvasRenderingContext2D.cpp", r"\bCanvasRenderingContext2D::GetImageData\s*\(", "canvas2d", "getImageData", CALL),
    Site("dom/html/HTMLCanvasElement.cpp", r"\bHTMLCanvasElement::ToDataURL\s*\(", "canvas", "toDataURL", CALL),
    Site("dom/html/HTMLCanvasElement.cpp", r"\bHTMLCanvasElement::ToBlob\s*\(", "canvas", "toBlob", CALL),
    Site("dom/html/HTMLCanvasElement.cpp", r"already_AddRefed<nsISupports>\s+HTMLCanvasElement::GetContext\s*\(\s*JSContext\s*\*", "canvas", "getContext", CALL),
    Site("dom/canvas/ClientWebGLContext.cpp", r"\bClientWebGLContext::GetParameter\s*\(", "webgl", "getParameter", CALL),
    Site("dom/canvas/ClientWebGLContext.cpp", r"\bClientWebGLContext::GetSupportedExtensions\s*\(", "webgl", "getSupportedExtensions", CALL),
    Site("dom/canvas/WebGLContextExtensions.cpp", r"void\s+ClientWebGLContext::GetExtension\s*\(\s*JSContext\s*\*\s*cx\s*,", "webgl", "getExtension", CALL),
    Site("dom/canvas/ClientWebGLContext.cpp", r"\bClientWebGLContext::GetShaderPrecisionFormat\s*\(", "webgl", "getShaderPrecisionFormat", CALL),
    Site("dom/media/webaudio/AudioContext.cpp", r"\bAudioContext::OutputLatency\s*\(", "audioContext", "outputLatency"),
    Site("dom/base/nsPluginArray.cpp", r"\bnsPluginArray::IndexedGetter\s*\(", "navigator.plugins", "indexedGetter"),
    Site("dom/base/nsPluginArray.cpp", r"\bnsPluginArray::NamedGetter\s*\(", "navigator.plugins", "namedGetter"),
    Site("dom/base/nsMimeTypeArray.cpp", r"\bnsMimeTypeArray::IndexedGetter\s*\(", "navigator.mimeTypes", "indexedGetter"),
    Site("dom/base/nsMimeTypeArray.cpp", r"\bnsMimeTypeArray::NamedGetter\s*\(", "navigator.mimeTypes", "namedGetter"),
    Site("dom/performance/PerformanceMainThread.cpp", r"\bPerformanceMainThread::Timing\s*\(", "performance", "timing"),
    Site("dom/base/Document.cpp", r"\bDocument::GetCookie\s*\(", "document", "cookie.get"),
    Site("dom/base/Document.cpp", r"\bDocument::SetCookie\s*\(", "document", "cookie.set", SET),
    Site("dom/media/webrtc/jsapi/PeerConnectionImpl.cpp", r"PeerConnectionImpl::CreateOffer\s*\(\s*const\s+RTCOfferOptions\s*&", "webrtc", "createOffer", CALL),
    Site("dom/media/webrtc/jsapi/PeerConnectionImpl.cpp", r"\bPeerConnectionImpl::CreateAnswer\s*\(", "webrtc", "createAnswer", CALL),
    Site("dom/media/webrtc/jsapi/PeerConnectionImpl.cpp", r"already_AddRefed<RTCDataChannel>\s+PeerConnectionImpl::CreateDataChannel\s*\(", "webrtc", "createDataChannel", CALL),
    Site("dom/media/MediaDevices.cpp", r"\bMediaDevices::EnumerateDevices\s*\(", "mediaDevices", "enumerateDevices", CALL),
    Site("dom/media/MediaDevices.cpp", r"already_AddRefed<Promise>\s+MediaDevices::GetUserMedia\s*\(", "mediaDevices", "getUserMedia", CALL),
    Site("dom/localstorage/LSObject.cpp", r"\bLSObject::GetItem\s*\(", "localStorage", "getItem", CALL),
    Site("dom/localstorage/LSObject.cpp", r"\bLSObject::SetItem\s*\(", "localStorage", "setItem", CALL),
    Site("dom/storage/PartitionedLocalStorage.cpp", r"\bPartitionedLocalStorage::GetItem\s*\(", "localStorage", "getItem", CALL),
    Site("dom/storage/PartitionedLocalStorage.cpp", r"\bPartitionedLocalStorage::SetItem\s*\(", "localStorage", "setItem", CALL),
    Site("dom/storage/SessionStorage.cpp", r"\bSessionStorage::GetItem\s*\(", "sessionStorage", "getItem", CALL),
    Site("dom/storage/SessionStorage.cpp", r"\bSessionStorage::SetItem\s*\(", "sessionStorage", "setItem", CALL),
    Site("layout/style/FontFaceSet.cpp", r"\bFontFaceSet::Check\s*\(", "fonts", "check", CALL),
    Site("layout/style/FontFaceSet.cpp", r"\bFontFaceSet::ForEach\s*\(", "fonts", "forEach", CALL),
    Site("dom/canvas/OffscreenCanvas.cpp", r"\bOffscreenCanvas::GetContext\s*\(", "offscreenCanvas", "getContext", CALL),
    Site("dom/canvas/OffscreenCanvas.cpp", r"\bOffscreenCanvas::TransferToImageBitmap\s*\(", "offscreenCanvas", "transferToImageBitmap", CALL),
    Site("dom/geolocation/Geolocation.cpp", r"void\s+Geolocation::GetCurrentPosition\s*\(\s*PositionCallback\s*&", "geolocation", "getCurrentPosition", CALL),
    Site("dom/geolocation/Geolocation.cpp", r"int32_t\s+Geolocation::WatchPosition\s*\(\s*PositionCallback\s*&", "geolocation", "watchPosition", CALL),
    Site("dom/media/webaudio/AudioContext.h", r"float\s+SampleRate\(\)\s+const\s*\{", "audioContext", "sampleRate"),
)


class AuditError(RuntimeError):
    """The source tree or audit manifest cannot be checked safely."""


def _validate_sites(sites: Sequence[Site]) -> None:
    errors: list[str] = []
    seen: set[str] = set()
    for site in sites:
        if site.kind not in {GET, SET, CALL}:
            errors.append(f"{site.site_id}: unknown kind {site.kind!r}")
        if not all((site.path, site.signature, site.object_name, site.property_name)):
            errors.append(f"{site.site_id}: incomplete site")
        if site.site_id in seen:
            errors.append(f"{site.site_id}: duplicate site id")
        seen.add(site.site_id)
        if Path(site.path).is_absolute() or ".." in Path(site.path).parts:
            errors.append(f"{site.site_id}: source path must stay under the source root")
        try:
            re.compile(site.signature, re.MULTILINE)
        except re.error as exc:
            errors.append(f"{site.site_id}: invalid signature: {exc}")
    if errors:
        raise AuditError("; ".join(errors))


def _source_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AuditError(f"source path escapes the source root: {relative}") from exc
    return candidate


def _mask_non_code(text: str) -> str:
    """Blank comments and literals while preserving offsets and newlines."""

    masked = list(text)
    index = 0
    while index < len(text):
        if text.startswith("//", index):
            end = text.find("\n", index)
            end = len(text) if end < 0 else end
            for offset in range(index, end):
                masked[offset] = " "
            index = end
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = len(text) if end < 0 else end + 2
            for offset in range(index, end):
                if masked[offset] != "\n":
                    masked[offset] = " "
            index = end
            continue
        if text[index] in {'"', "'"}:
            quote = text[index]
            masked[index] = " "
            index += 1
            escaped = False
            while index < len(text):
                char = text[index]
                if char != "\n":
                    masked[index] = " "
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    index += 1
                    break
                index += 1
            continue
        index += 1
    return "".join(masked)


def _body_brace(text: str, match: re.Match[str], site_id: str) -> int:
    """Return the opening brace of a definition, rejecting declarations."""

    opening = text.find("(", match.start(), match.end())
    if opening < 0:
        raise AuditError(f"{site_id}: signature has no opening parenthesis")

    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    closing = -1
    for index in range(opening, len(text)):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            line_comment = char != "\n"
            continue
        if block_comment:
            if char == "*" and following == "/":
                block_comment = False
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char == "/" and following == "/":
            line_comment = True
            continue
        if char == "/" and following == "*":
            block_comment = True
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                closing = index
                break
    if closing < 0:
        raise AuditError(f"{site_id}: signature has unbalanced parentheses")

    tail = text[closing + 1 : closing + 1001]
    brace = tail.find("{")
    semicolon = tail.find(";")
    if brace < 0 or (semicolon >= 0 and semicolon < brace):
        raise AuditError(f"{site_id}: matched a declaration, not a function body")
    return closing + 1 + brace


def _read_pin(browser_root: Path) -> tuple[str, str]:
    pin_path = browser_root / "upstream.sh"
    try:
        lines = pin_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AuditError(f"cannot read {pin_path}: {exc}") from exc
    pin: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        pin[key.strip()] = value.strip()
    missing = [key for key in ("version", "release") if not pin.get(key)]
    if missing:
        raise AuditError(f"{pin_path} has no {', '.join(missing)}")
    return pin["version"], pin["release"]


def audit_source(
    source_root: str | Path,
    *,
    expect_version: str | None = None,
    sites: Sequence[Site] | None = None,
) -> dict[str, object]:
    """Check every selected native entry point without modifying the tree."""

    selected = SITES if sites is None else tuple(sites)
    _validate_sites(selected)
    root = Path(source_root).resolve()
    errors: list[str] = []
    verified: list[dict[str, object]] = []
    runtime_tracer_sources: list[str] = []

    if not root.is_dir():
        raise AuditError(f"source directory not found: {root}")

    version_path = _source_path(root, "browser/config/version.txt")
    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AuditError(f"cannot read {version_path}: {exc}") from exc
    if expect_version is not None and version != expect_version:
        errors.append(
            f"Firefox source is {version!r}; expected {expect_version!r}"
        )

    texts: dict[Path, str] = {}
    masked_texts: dict[Path, str] = {}
    source_hashes: dict[str, str] = {}
    checked_paths = (
        {site.path for site in selected}
        | {LEGACY_LOCAL_STORAGE_PATH}
        | set(RUNTIME_SUPPORT_PATHS)
    )
    for relative in sorted(checked_paths):
        path = _source_path(root, relative)
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
            texts[path] = raw.decode("utf-8")
        except OSError as exc:
            errors.append(f"cannot read {relative}: {exc}")
        else:
            masked_texts[path] = _mask_non_code(texts[path])
            source_hashes[relative] = hashlib.sha256(raw).hexdigest()

    for relative in RUNTIME_TRACER_PATHS:
        if _source_path(root, relative).is_file():
            runtime_tracer_sources.append(relative)
            errors.append(
                f"{relative}: compiled PropertyTracer source is present; "
                "the audit must run against a clean tree"
            )

    for site in selected:
        if site.path == LEGACY_LOCAL_STORAGE_PATH:
            errors.append(
                f"{site.site_id}: legacy LocalStorage path is not a current target"
            )
            continue
        path = _source_path(root, site.path)
        text = texts.get(path)
        if text is None:
            errors.append(f"{site.site_id}: required file not found: {site.path}")
            continue
        masked = masked_texts[path]
        matches = list(re.finditer(site.signature, masked, re.MULTILINE))
        if len(matches) != 1:
            errors.append(
                f"{site.site_id}: expected one definition in {site.path}, "
                f"found {len(matches)}"
            )
            continue
        try:
            _body_brace(masked, matches[0], site.site_id)
        except AuditError as exc:
            errors.append(str(exc))
            continue
        verified.append(
            {
                "id": site.site_id,
                "path": site.path,
                "line": text.count("\n", 0, matches[0].start()) + 1,
                "object": site.object_name,
                "property": site.property_name,
                "kind": site.kind,
            }
        )

    runtime_markers: list[dict[str, object]] = []
    for path in sorted(texts):
        text = texts[path]
        for marker in RUNTIME_MARKERS:
            for match in re.finditer(re.escape(marker), text):
                runtime_markers.append(
                    {
                        "path": str(path.relative_to(root)),
                        "line": text.count("\n", 0, match.start()) + 1,
                        "marker": marker,
                    }
                )
    for marker in runtime_markers:
        errors.append(
            f"{marker['path']}:{marker['line']}: runtime tracer marker "
            f"{marker['marker']!r}; use a clean generated source tree"
        )

    return {
        "schema": 1,
        "tool": "property-tracer-audit",
        "source": str(root),
        "source_version": version,
        "expected": len(selected),
        "verified": len(verified),
        "ok": not errors,
        "sites": verified,
        "runtime_tracer_sources": runtime_tracer_sources,
        "sources": [
            {"path": relative, "sha256": source_hashes[relative]}
            for relative in sorted(source_hashes)
        ],
        "runtime_markers": runtime_markers,
        "errors": errors,
    }


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    browser_root = Path(__file__).resolve().parent.parent
    version, release = _read_pin(browser_root)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=browser_root / f"camoufox-{version}-{release}",
        help="prepared Firefox source tree (default: the pin in upstream.sh)",
    )
    parser.add_argument(
        "--expect-version",
        default=f"{version}-{release}",
        help="required browser/config/version.txt value",
    )
    parser.add_argument("--json", action="store_true", help="emit the full report")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = audit_source(args.source, expect_version=args.expect_version)
    except AuditError as exc:
        print(f"property tracer audit failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        print(
            f"verified {result['verified']}/{result['expected']} native sites "
            f"for source {result['source_version']}"
        )
    else:
        for error in result["errors"]:
            print(error, file=sys.stderr)
        print(
            f"verified {result['verified']}/{result['expected']} native sites; "
            "the source tree is not compatible",
            file=sys.stderr,
        )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
