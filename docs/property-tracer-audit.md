# Property tracer source audit

The Firefox 152 PropertyTracer was a runtime native instrumentation system. It
changed 77 Firefox source sites, compiled a C++ singleton and two background
threads into `xul`, and could write JSONL from parent and content processes.
That is not suitable for the current tree: it changes the engine path being
measured, can perturb timing-sensitive fingerprint probes, and requires the
generated Firefox tree to be edited after every patch application.

This branch keeps the useful part only: a read-only manifest and checker for
the native entry points behind page-observable properties. It can detect source
drift after a Firefox upgrade. It does not claim that a page read a property,
because proving that needs runtime observation.

## Scope

- 77 native source definitions: 51 gets, one set (`document.cookie`), and 25 calls.
- Four `localStorage` targets: `LSObject::GetItem`,
  `LSObject::SetItem`, `PartitionedLocalStorage::GetItem`, and
  `PartitionedLocalStorage::SetItem`.
- Firefox 158 signatures for `Navigator.userAgent` (`nsACString`) and the
  caller-aware `window.innerWidth` / `window.innerHeight` overloads.
- A failure if the source tree still contains old PropertyTracer injection
  markers or compiled tracer sources, or uses the legacy
  `dom/storage/LocalStorage.cpp` path.

The tool reads only `browser/config/version.txt` and the target source files.
It does not write to the tree, launch Firefox, compile C++, alter preferences, or
expose anything to page JavaScript. It is deliberately absent from the build
entry points, so it adds no shipping code or binary input.

## Run it

Prepare the source tree only if it is not already present:

```bash
cd browser
make dir
```

`make dir` fetches, patches, and copies additions; it does not build Firefox.
Then run the audit:

```bash
cd browser
python3 scripts/audit-property-tracer.py
```

The default source directory is derived from `version` and `release` in
`browser/upstream.sh`. A successful run prints:

```text
verified 77/77 native sites for source 158.0-beta.33
```

To inspect the resolved source files, SHA-256 digests, and line numbers:

```bash
python3 scripts/audit-property-tracer.py --json
```

To audit an explicit prepared tree:

```bash
python3 scripts/audit-property-tracer.py /path/to/camoufox-158.0-beta.33 \
  --expect-version 158.0-beta.33
```

The command exits non-zero with every mismatch named. A missing or ambiguous
definition, a version mismatch, a path outside the source root, a legacy
localStorage target, or a runtime injection marker fails the audit.

## Limits

This is a source-manifest drift check, not data-flow analysis and not evidence
that a page used a property. For `localStorage` it preserves the four `getItem`
and `setItem` targets from the 152 fix. It does not enumerate `removeItem`,
`clear`, `key`, `length`, storage events, or distinguish a content-process
cache hit from a parent-process checkpoint.

## Tests

The tests are network-free and need no browser:

```bash
python3 -m pytest ci/tests/test_property_tracer_audit.py -q
```

They cover the 77-site manifest, the four Firefox 158 localStorage paths,
declaration-versus-definition matching, read-only behaviour, fail-closed version
and path checks, stable JSON output, and the absence of compiled tracer sources.

## Why not port the runtime tracer

The old implementation required all of the following on every prepared source
tree:

- edits at 77 native entry points and matching `moz.build` include changes;
- a C++ singleton with control and flush threads plus JSONL files;
- an out-of-line rewrite of the inline `AudioContext::SampleRate()` accessor;
- a `MaskConfig` startup hook and process-wide state;
- localStorage coverage spread across two implementation paths.

Keeping that path would either duplicate the old patch stack in generated
sources or turn a diagnostic into permanent shipping attack surface. The static
manifest preserves the useful version-drift guard without either cost.
