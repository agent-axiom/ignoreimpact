# Binary installation

[README](../README.md) · [Usage](USAGE.md) · [Release process](RELEASING.md)

## Current status

The binary release pipeline is being prepared for `0.1.0-rc.1`. A public GitHub
Release has not been published yet. Completed candidate builds are available as
workflow artifacts on the [Release candidate workflow](https://github.com/agent-axiom/ignoreimpact/actions/workflows/release-candidate.yml).
GitHub may require you to sign in to download an artifact. Use the final artifact
whose name starts with `verified-candidate-`; a build-only artifact is not evidence
that all native installation checks passed.

## Choose an archive

| System | CPU | Filename suffix |
| --- | --- | --- |
| Linux | x86-64 | `linux_amd64.tar.gz` |
| Linux | ARM64 | `linux_arm64.tar.gz` |
| macOS | Intel | `darwin_amd64.tar.gz` |
| macOS | Apple Silicon | `darwin_arm64.tar.gz` |
| Windows | x86-64 | `windows_amd64.zip` |
| Windows | ARM64 | `windows_arm64.zip` |

The full name starts with `ignoreimpact_0.1.0-rc.1_`. Each archive contains a
standalone binary, licenses, build information, and the sample context. Running
it needs neither Go nor Docker. Python is used by the release verification
workflow, not by the installed CLI.

## Verify, extract, run

Download the selected archive and `SHA256SUMS` from the same candidate or release.
Compare its checksum before extraction:

```sh
# Linux: compare this output with the corresponding line in SHA256SUMS.
sha256sum ignoreimpact_0.1.0-rc.1_linux_amd64.tar.gz
# macOS:
shasum -a 256 ignoreimpact_0.1.0-rc.1_darwin_arm64.tar.gz
```

Windows PowerShell:

```powershell
Get-FileHash .\ignoreimpact_0.1.0-rc.1_windows_amd64.zip -Algorithm SHA256
```

Extract into a new folder. On Linux/macOS, use `tar -xzf ARCHIVE.tar.gz`; on
Windows, use `Expand-Archive ARCHIVE.zip DESTINATION`. From the extracted folder:

```sh
./ignoreimpact version
./ignoreimpact compare --context examples/demo/context \
  --before examples/demo/before.dockerignore \
  --after examples/demo/after.dockerignore
```

On Windows, use `.\ignoreimpact.exe` and put the command on one line.
The demo takes only a few seconds and shows **18 added bytes, 11 removed bytes,
net +7 bytes**, with both matching-rule explanations. Add `--json` for JSON or
`--fail-on added` to exercise exit `1`. Copy the executable to a directory on your
`PATH` if desired; no service or automatic updater is installed.

## Trust and platform prompts

`BUILDINFO.json` identifies the version, exact source commit, target, and binary
hash. The release's manifest, checksum index, unsigned provenance record, and
native verification report provide further traceability.

These builds are **not publisher-signed, notarized, or cryptographically
attested**. Checksums detect corruption; they do not independently prove who
published a file. macOS Gatekeeper and Windows SmartScreen may show warnings for
unsigned downloads. Do not automatically bypass OS warnings; use a reviewed
source build if your policy requires it. Source builds are documented in [Usage](USAGE.md).

A dedicated Homebrew tap is planned but has not been created. No `brew install`
command is advertised until its repository, formula, and install test exist.
