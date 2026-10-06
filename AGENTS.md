# Working on IgnoreImpact

This guide is for coding agents and human contributors. Keep changes focused on
local Docker ignore-policy comparison.

## Start here

- [README](README.md): purpose and runnable demo
- [Usage](docs/USAGE.md): CLI and output contract
- [Semantics](docs/SEMANTICS.md): matching and counting rules
- [Limits](docs/LIMITS.md): filesystem and resource assumptions
- [Architecture](docs/ARCHITECTURE.md): package map and verification

## Preserve these invariants

1. Delegate ignore parsing and matching to the pinned `moby/patternmatcher`.
   Do not introduce a separate glob engine or substitute Git ignore rules.
2. Compare both policies against one current tree. Do not silently turn this
   into a Git-revision diff or final-image estimator.
3. Never read file bodies to calculate size, follow symlink targets, or add
   network calls to a scan. Selected policy files are intentionally read.
4. Fail on incomplete scans. Do not suppress traversal errors or resource limits.
5. Keep reports deterministic and human text terminal-safe. Preserve schema v1
   meanings; incompatible JSON changes require a new schema version.
6. Treat policy instances as non-concurrent. Keep filesystem mutation assumptions
   and host-specific matching differences explicit.

## Make a change

Add a focused regression test, then make the smallest clear implementation change.
Use synthetic fixtures only. For semantic changes, compare against upstream Moby
and link official evidence. Update the relevant focused document instead of
expanding the README into a reference manual.

Before handing off:

```sh
gofmt -w cmd internal
go test -race -cover ./...
go vet ./...
go build -trimpath -o bin/ignoreimpact ./cmd/ignoreimpact
```

For matcher changes, also run the differential fuzz target described in
[Architecture](docs/ARCHITECTURE.md). For report changes, reproduce
[the demo JSON](examples/demo/report.json), review the schema, and exercise exit
codes `0`, `1`, and `2`. Verify links and executable examples for documentation
changes. Report checks that were skipped or blocked accurately.

Do not create releases, change access controls, merge pull requests, or publish
unrelated changes without the maintainer's authorization. A completed local test
run does not establish that remote CI passed.
