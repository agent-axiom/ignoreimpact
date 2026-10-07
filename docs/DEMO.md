# Reproduce the terminal demo

[README](../README.md) · [First CI check](CI.md) · [Public cases](CASE_STUDIES.md)

The 28-second recording builds the CLI from source, reads both bundled policies,
compares the same tiny synthetic tree, and demonstrates `--fail-on added`
returning exit `1`. It includes both before/after rule explanations. No Docker
build or dependency installation is part of this example.

## Try the commands

Requires Git and Go 1.24+. From a directory without an `ignoreimpact` checkout:

```sh
git clone https://github.com/agent-axiom/ignoreimpact.git
cd ignoreimpact
# Immutable CLI/fixture revision used by the initial recording:
git checkout --detach fe8cbeab660a5955a7a635567f96dfe522ed443e
go build -trimpath -o bin/ignoreimpact ./cmd/ignoreimpact
./bin/ignoreimpact compare \
  --context examples/demo/context \
  --before examples/demo/before.dockerignore \
  --after examples/demo/after.dockerignore
```

These are POSIX shell commands. Windows users can build `bin/ignoreimpact.exe`
and run `.\bin\ignoreimpact.exe` with flags on one line. This source-build route
does not depend on a published binary release. For a source install to PATH:

```sh
go install github.com/agent-axiom/ignoreimpact/cmd/ignoreimpact@fe8cbeab660a5955a7a635567f96dfe522ed443e
```

The fixture is deliberately small:

- Before, `node_modules` excludes the synthetic 18-byte `cache.bin`.
- After, `.env*` excludes the 11-byte `.env.example`; `node_modules` is included
  by default because its exclusion was removed.
- One path is added and one removed. Logical regular-file bytes grow by **7 B**.

The fixture's name does not make it an installed production dependency or a
measured real cache. Bytes are neither image size nor actual build transfer.
Read both directions: required inputs can be removed, and a correct policy can
intentionally add files, as the [Excalidraw case](CASE_STUDIES.md#2-excalidraw-an-intended-increase-fixes-missing-inputs)
illustrates. This is policy-review evidence, not secret detection.

To try the CI gate, append `--fail-on added`. The same complete report is
returned, with exit `1`. Exit `2` means an error; never treat it as a passing or
complete comparison. Start adoption with `--fail-on none`, review both additions
and removals, and then choose a gate. Follow the [CI guide](CI.md) for safe
policy extraction, source installation, and status handling.

## Record and render

Use a checkout containing these scripts. The immutable CLI revision above
predates the recording scripts; checking it out is for the manual CLI example,
not sufficient on its own to run the media generator.

Recording needs Python 3.10+, POSIX PTYs, Git and Go 1.24+. Rendering additionally
needs Pillow, ffmpeg with libx264, and DejaVu Sans / DejaVu Sans Mono fonts.
These are optional authoring dependencies; no Go module dependencies change.
The integrity tests use only the Python standard library; on non-POSIX systems,
only the PTY-capture test is skipped.
If these dependencies are not already installed, install them through your
normal trusted package-management workflow.

```sh
python3 scripts/record_demo.py
python3 scripts/render_demo.py
python3 -m unittest discover -s scripts -p 'test_demo.py' -v
```

For an existing repo-local Go toolchain, the recorder also supports:

```sh
python3 scripts/record_demo.py --go .tools/go/bin/go
```

The renderer defaults to `/usr/share/fonts/truetype/dejavu`. Use `--font-dir`
for another directory containing the same font filenames. Both scripts accept
an output/input directory within this checkout via `--output` / `--input`.
Do not put that directory inside `examples/demo/context` or another measured
fixture. The default `dist/demo` is ignored by Git and lies outside the context.
Commands run with `GOWORK=off`, `GOTOOLCHAIN=local`, and `LC_ALL=C`. Existing
`GOCACHE` / `GOPATH` values are respected; otherwise repo-local `.tools` caches
are used. Go module acquisition, if needed, is a build step, separate from the
network-free scanner.

The recorder rejects changed or untracked CLI/fixture sources, builds the local
checkout, and saves its exact Git revision. The renderer verifies terminal text
against the raw PTY files and their recorded SHA256 digests before rendering.
The initial recording used Linux/amd64 and Go 1.27.1. Re-running captures the
actual toolchain on your machine; timings, build bytes and platform text can
vary. With identical capture inputs, fonts, Pillow and ffmpeg, the rendering is
deterministic.

## Outputs and evidence

All outputs are local files under `dist/demo/` until separately reviewed and
published:

| File | Purpose |
| --- | --- |
| `ignoreimpact-demo.mp4` | 1600 × 1080 H.264 video, 28 seconds, no audio |
| `ignoreimpact-demo.gif` | Same 28-second storyboard, looping, full resolution |
| `poster.png` | Static rule-explanation preview |
| `session.cast` | Asciinema v2 stream with actual PTY timings |
| `*.pty` | Unmodified output bytes from each executed command |
| `transcript.txt` | Searchable commands/output, with CRLF normalized to LF |
| `storyboard.json` | Captured commands/output, repository-relative working directories |
| `report.json` | Independent JSON run, compared with the committed golden |
| `gated-report.txt` | Complete report retained even when the added-path gate fails |
| `manifest.json` | Source revision, input/binary hashes, commands, real durations and exit checks |
| `media.json` | Rendered file hashes, dimensions, duration and storyboard schedule |
| `frame-*.png` | Full-size render frames for visual review |

**Playback pacing is illustrative.** The video/GIF gives each explanation time
to be read and is not a runtime benchmark. Headings and highlights are editorial
annotations around genuine command output. Terminal output is only wrapped to
fit the screen, not rewritten. No AI-generated terminal screenshot is used.
The raw cast preserves actual timing; installing asciinema is optional if you
want to replay that file.

Before sharing, inspect the actual encoded video/GIF, not only the source PNGs.
Check that both rule explanations, the source-build command, and `exit=1` are
readable. Keep a text fallback and the reproduction instructions alongside the
media. Keep the README short; link here rather than embedding this reference.
