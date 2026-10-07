# Three reproducible public-repository policy changes

[CI adoption](CI.md) · [Semantics](SEMANTICS.md) · [Evidence manifest](../examples/case-studies/cases.json)

These are **historical upstream changes**, not proposed optimizations. Both
policies in each case were measured against the same pinned after-commit tree.
The examples deliberately include a decrease, an intended increase, and zero
change. Measurements were recorded on Linux/amd64 with Go 1.27.1 on 2026-10-07,
using IgnoreImpact source commit
[`2183d2a5407559e94fc08d2d7f070ac9ae811127`](https://github.com/agent-axiom/ignoreimpact/commit/2183d2a5407559e94fc08d2d7f070ac9ae811127).

## Results

All entries in these three snapshots are regular files; there are no symlinks or
submodules. Bytes below are exact logical file bytes, not compressed transfer or
image size.

| Pinned case | Before files / bytes | After files / bytes | Added files / bytes | Removed files / bytes | Net bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Uptime Kuma | 141 / 679,135 | 127 / 673,547 | 0 / 0 | 14 / 5,588 | -5,588 |
| Excalidraw | 443 / 6,194,801 | 445 / 6,196,969 | 2 / 2,168 | 0 / 0 | +2,168 |
| Docker Getting Started | 84 / 6,388,136 | 84 / 6,388,136 | 0 / 0 | 0 / 0 | 0 |

### 1. Uptime Kuma: remove tracked development material

- [Historical change](https://github.com/louislam/uptime-kuma/commit/2b8c049e7b1b67ba99f52eee578180ca2f6d5bcf): adds `/test` and `/kubernetes` to the root policy.
- Before policy: `803029a9e4a9c8a68e716a59f966cc70f39ded6d`.
- After policy and measured tree: `2b8c049e7b1b67ba99f52eee578180ca2f6d5bcf`.
- Root [MIT license](https://github.com/louislam/uptime-kuma/blob/2b8c049e7b1b67ba99f52eee578180ca2f6d5bcf/LICENSE), copyright 2021 Louis Lam.

The change removes seven Kubernetes files and seven test Dockerfiles: 14 files,
5,588 bytes. The full tracked snapshot contains 164 files and 1,344,950 bytes;
other existing exclusions already remove part of it. No dependency install,
`node_modules`, `dist`, or generated data was added to inflate the effect.

This is a modest, concrete file-set change. It does not establish a faster build
or a smaller final image. Check required build inputs before adopting similar
exclusions in another repository.

[Exact before policy](../examples/case-studies/uptime-kuma/before.dockerignore) ·
[Exact after policy](../examples/case-studies/uptime-kuma/after.dockerignore) ·
[Every changed path and winning rule](../examples/case-studies/uptime-kuma/report.json) ·
[Provenance](../examples/case-studies/uptime-kuma/provenance.json)

### 2. Excalidraw: an intended increase fixes missing inputs

- [Historical change](https://github.com/excalidraw/excalidraw/commit/e1c5c706c684223c63b009b8136862cdd97fc989): replaces `!.env` with `!.env.development` and `!.env.production` in an allowlist policy.
- Before policy: `bdc56090d780d601be2f5dac2cea082a374f06f6`.
- After policy and measured tree: `e1c5c706c684223c63b009b8136862cdd97fc989`.
- Root [MIT license](https://github.com/excalidraw/excalidraw/blob/e1c5c706c684223c63b009b8136862cdd97fc989/LICENSE), copyright 2020 Excalidraw.

The candidate includes `.env.development` (1,154 bytes) and `.env.production`
(1,014 bytes): two files, 2,168 bytes added. No root `.env` is tracked in this
522-file snapshot. These are public repository defaults, not private local
credentials. No dependencies, build output, or local environment files were
created for the measurement.

The [upstream PR](https://github.com/excalidraw/excalidraw/pull/5809) describes
fixing broken Browse Libraries links in self-hosted/Docker builds. That is the
upstream author's motivation; this measurement only verifies policy inclusion.
A strict `--fail-on added` gate would correctly ask for review here. Review may
approve the increase because those files are required.

[Exact before policy](../examples/case-studies/excalidraw/before.dockerignore) ·
[Exact after policy](../examples/case-studies/excalidraw/after.dockerignore) ·
[Report](../examples/case-studies/excalidraw/report.json) ·
[Provenance](../examples/case-studies/excalidraw/provenance.json)

### 3. Docker Getting Started: a useful zero-effect result

- [Historical change](https://github.com/docker/getting-started/commit/615af9ff0d0ee7b085b36ee09ef9b63d2322a6bf): adds `app/Dockerfile` after the existing `node_modules` rule.
- Before policy: `fec54de67bd359ae4d8544242ca7e9e71d105d4a`.
- After policy and measured tree: `615af9ff0d0ee7b085b36ee09ef9b63d2322a6bf`.
- Root [Apache-2.0 license](https://github.com/docker/getting-started/blob/615af9ff0d0ee7b085b36ee09ef9b63d2322a6bf/LICENSE).

Neither `app/Dockerfile` nor installed `node_modules` is present in this
84-file tracked snapshot. The change therefore produces **zero added files,
zero removed files, and zero bytes of impact**. The tracked root `Dockerfile`
is a different path. The same upstream commit also ignores `app/Dockerfile` in
Git, but Git ignore rules are not inputs to this comparison.

This does not make the Docker ignore rule redundant. It can matter when a user
creates the tutorial's local file. We did not synthesize that file or install
dependencies, so there is no measured saving to claim on those absent inputs.
The original policy bytes have no final newline; the saved evidence preserves
that detail.

[Exact before policy](../examples/case-studies/docker-getting-started/before.dockerignore) ·
[Exact after policy](../examples/case-studies/docker-getting-started/after.dockerignore) ·
[Report](../examples/case-studies/docker-getting-started/report.json) ·
[Provenance](../examples/case-studies/docker-getting-started/provenance.json)

## Reproduce and verify

Requires Git, Python 3.10+, and Go 1.24+ (the recorded run used Go 1.27.1).
From a checkout containing these docs, build the immutable measurement version
in a separate directory; do not substitute the current main branch:

```sh
mkdir -p .adoption-work
revision=2183d2a5407559e94fc08d2d7f070ac9ae811127
git clone https://github.com/agent-axiom/ignoreimpact.git .adoption-work/tool-source
git -C .adoption-work/tool-source checkout --detach "$revision"
test "$(git -C .adoption-work/tool-source rev-parse HEAD)" = "$revision"
root="$PWD"
(
  cd .adoption-work/tool-source
  GOWORK=off GOTOOLCHAIN=local go build -trimpath \
    -ldflags="-X github.com/agent-axiom/ignoreimpact/internal/cli.SourceCommit=$revision" \
    -o "$root/.adoption-work/ignoreimpact" ./cmd/ignoreimpact
)
python3 scripts/measure_case_studies.py \
  --ignoreimpact .adoption-work/ignoreimpact
```

Use a fresh `.adoption-work/tool-source` path for the clone. The version string
is a sanity check, not a signature; trust comes from reviewing the pinned source
and building it yourself. The runner fetches the exact public Git commits,
checks tree/policy object IDs, and materializes raw tracked blobs. It does not
execute any scripts from the three measured repositories. Each scan runs twice
and must produce identical bytes. Saved policies, licenses, reports, and
provenance must match exactly; a mismatch fails rather than updating evidence.
`--record` is an explicit maintainer-only way to regenerate reviewed evidence.

For each case the executed scan, from a temporary directory outside its context,
is exactly this command (the binary and context paths are absolute):

```sh
ignoreimpact compare --context "$PINNED_CONTEXT" \
  --before before.dockerignore --after after.dockerignore --json
```

The [manifest](../examples/case-studies/cases.json) records repository URLs,
full before/after commits, tree IDs, policy blob IDs, and licenses. Per-case
provenance adds SHA256 digests for both policies, the report, the copied root
license, and a canonical inventory of tracked paths, modes, Git blob IDs, and
blob sizes. Root license texts are preserved alongside the small policy excerpts;
the upstream repositories are not vendored.

## Scope and exclusions

All comparisons use raw tracked Git blobs from one immutable after-commit tree.
They exclude `.git` metadata, untracked files, dependency installation, newly
generated caches/build outputs, submodule contents, and LFS downloads. Any
generated file already tracked by Git remains part of the snapshot. Git archive export
attributes, smudge filters, and platform newline conversion are not applied.
These three trees have no submodules or symlinks; no tracked entries were omitted.
The snapshot exporter reads source bytes to reconstruct files. The IgnoreImpact
scan itself reads file metadata and the two selected policies only.

Policies and output reports are outside the measured context. No Docker builds,
network transfers inside the scanner, production workloads, timing benchmarks,
or final-image measurements were performed. Public root licenses were checked
at the pinned commits; the examples imply no upstream endorsement or adoption.
