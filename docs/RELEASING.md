# Release process

[README](../README.md) · [Binary installation](INSTALL.md) · [Architecture](ARCHITECTURE.md)

## Candidate contract

`release/config.json` pins the candidate version, exact Go toolchain, and six
OS/CPU targets. `scripts/build_release.py` requires a clean Git checkout and
records its full source commit and tree. Candidate version strings are validated
before they enter build flags or filenames.

The build uses CGO-disabled binaries, trimmed paths, no build ID, and embedded
version/commit values. Archive ordering, metadata, ownership, modes, and timestamps
are normalized. Rebuilding with the same source, toolchain, and builder produces
identical candidate files. The workflow verifies this by building twice.

Each candidate includes:

- Six `.tar.gz`/`.zip` archives, with binary, licenses, sample context, and build info
- `release-manifest.json`: target names, sizes, hashes, toolchain, flags, dependency
  version, and immutable source identity
- `provenance.json`: an **unsigned** statement tying the manifest to the local build
  or GitHub workflow run; its contents differ across build environments
- `SHA256SUMS`: archive and metadata checksums
- `VERIFICATION.json`: produced only after six native installation checks pass

Moby's Apache-2.0 license and NOTICE, Go's BSD license, and this project's MIT
license ship in every archive.
No signing keys, OIDC grants, package-registry credentials, or publishing tokens
are used. A Go-generated ad-hoc Mach-O signature, if present, is not a publisher
signature or notarization.

## Build and verify locally

```sh
python3 -m unittest discover -s scripts -v
python3 scripts/build_release.py --output dist
python3 scripts/verify_release.py dist --commit "$(git rev-parse HEAD)"
python3 scripts/smoke_release.py dist/ignoreimpact_0.1.0-rc.1_linux_amd64.tar.gz
```

Use the archive matching the host for smoke testing. The smoke harness extracts
into a temporary directory, rejects unsafe paths and special entries, clears
`PATH`, and checks version identity, exact fixture JSON, exit codes `0/1/2`, rule
explanation, and license files. It does not require Go to run the extracted binary.

The builder refuses to overwrite a nonempty output directory. On failure, use a
new empty directory for the next attempt; do not publish partial output.

## GitHub workflow

[Release candidate](../.github/workflows/release-candidate.yml) runs automatically
when release scripts or runtime source change on `main`, and supports manual runs
with an optional candidate version. All repository permissions remain read-only.

1. Test source and packaging; build every target twice; compare bytes and hashes.
2. Run installation smoke tests on native Linux x86-64/ARM64, macOS Intel/Apple
   Silicon, and Windows x86-64/ARM64 runners.
3. Verify every result against the source commit and archive digest.
4. Upload the final `verified-candidate-...` artifact and write checksums to the
   job summary. Artifacts are retained for 30 days.

The workflow **does not create a tag or publish a release**. An artifact upload
digest is not a project signing certificate or a cryptographic provenance claim.

## Publication checklist

Before publishing, the maintainer should review:

- Candidate version and exact source commit
- Green source CI and the complete native release-candidate workflow for that commit
- The six archive names, sizes, SHA-256 hashes, and the verification report
- Draft release notes, compatibility limitations, and unsigned-build disclosure

Create a draft GitHub prerelease for the approved version, targeting the exact
reviewed commit. Upload the verified files without rebuilding them. Compare the
uploaded asset checksums with the candidate. Publish only after that review;
never move a published version tag to another commit. If bytes or source change,
create a new candidate version.

`release/NOTES.md` is the initial release-note draft. Update binary-install docs
only after a release actually exists. A Homebrew tap needs its own named
repository authorization and install verification; do not silently create one or
submit to Homebrew Core. External pilot invitations and community posts are
separate from release engineering and need their intended recipients/content.

References: [GitHub workflow artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data),
[GitHub releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).
