"""Which font directories the runtime fontconfig scans for an identity's OS."""

import json
from pathlib import Path

import pytest

from camoufox import utils


READ_BY = {"lin": ["L", "LW"], "mac": ["M"], "win": ["W", "LW"]}


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "INSTALL_DIR", tmp_path / "cache")
    conf = tmp_path / "fontconfig"
    conf.mkdir()
    (conf / "fonts.conf").write_text(
        '<fontconfig><dir prefix="cwd">fonts</dir></fontconfig>'
    )
    fonts = tmp_path / "bin" / "fonts"
    for group in ("L", "LW", "M", "W"):
        (fonts / group).mkdir(parents=True)
    return conf, tmp_path / "bin" / "camoufox-bin", fonts


def scanned(runtime_conf):
    return [
        Path(line.split("<dir>")[1].split("</dir>")[0]).name
        for line in Path(runtime_conf).read_text().splitlines()
        if "<dir>" in line
    ]


def test_groups_json_picks_the_os_groups(bundle):
    conf, binary, fonts = bundle
    (fonts / "groups.json").write_text(json.dumps({"readBy": READ_BY}))

    assert scanned(utils._generate_fontconfig(str(conf), binary, "windows")) == [
        "W",
        "LW",
    ]


def test_a_corrupt_groups_json_fails_instead_of_scanning_every_os(bundle):
    conf, binary, fonts = bundle
    (fonts / "groups.json").write_text("{not json")

    with pytest.raises(ValueError):
        utils._generate_fontconfig(str(conf), binary, "windows")


def test_a_missing_groups_json_keeps_the_legacy_per_os_layout(bundle):
    conf, binary, fonts = bundle
    (fonts / "windows").mkdir()

    assert scanned(utils._generate_fontconfig(str(conf), binary, "windows")) == [
        "windows"
    ]
