#!/usr/bin/env bash
# Generate the bundled uBlock Origin's selfie into an unpackaged build, after
# `fetch-ubo.py stage` (tests.yml's browser artifact; a release seeds its zip in
# build.yml). The build's own browser runs, so this needs its runtime
# libraries and the camoufox package, in a venv of its own.
#
#     browser/scripts/seed-ubo.sh <dir with camoufox-bin>
set -euo pipefail

bin_dir="$1"
venv="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ubo-seed-venv"

if [ -n "${CI:-}" ]; then
  sudo apt-get update -qq
  sudo apt-get install -y --no-install-recommends \
    libgtk-3-0t64 libasound2t64 libdbus-glib-1-2 libx11-xcb1 libxtst6
fi
python3 -m venv "$venv"
"$venv/bin/pip" install -q ./python
# fpgen fetches its model on first import, unverified: install the pinned one.
"$venv/bin/python" python/scripts/pin-fpgen-model.py
"$venv/bin/python" browser/scripts/fetch-ubo.py seed "$bin_dir/camoufox-bin"
