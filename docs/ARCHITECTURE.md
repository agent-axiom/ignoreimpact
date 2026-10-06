# Architecture

[README](../README.md) · [Agent guide](../AGENTS.md) · [Contributing](../CONTRIBUTING.md)

## Code map

| Location | Responsibility |
| --- | --- |
| `cmd/ignoreimpact` | Process entry point, interrupt cancellation, exit status |
| `internal/cli` | Flags, selector validation, command orchestration, CI gates |
| `internal/policy` | Moby parsing/matching, source selection, line-aware explanations |
| `internal/scan` | Rooted traversal, metadata accounting, bounds, sorted changes |
| `internal/report` | Versioned JSON and terminal-safe text rendering |

The dependency direction is `cmd → cli → policy/scan/report`; scan depends on
policy, and report depends on the report types. There are no background services,
frameworks, network clients, or AI dependencies in the scanner.

## Data flow

1. The CLI validates options and opens the selected context with `os.OpenRoot`.
2. Each policy is explicitly loaded or discovered independently.
3. Moby's reader normalizes policy patterns. Rule records retain source lines.
4. One walk evaluates non-directory entries under both policies. Excluded
   directories are traversed so negated descendant rules remain effective.
5. Included regular files and symlinks contribute metadata totals. Only changed
   inclusion receives a paired explanation in the report.
6. The completed changes are sorted by path, then rendered. CI gates inspect the
   completed totals and return the requested exit status.

Policy instances use Moby's mutable compiled matchers and must not be evaluated
concurrently. The scanner is intentionally single-threaded. The filesystem must
remain stable while it is scanned; see [Limits](LIMITS.md).

## Contracts

- Matching and normalization come from the pinned Moby dependency.
- Scans either return a complete report or fail. They never return a successful
  partial inventory after a read error or resource limit.
- Bytes are metadata-derived logical regular-file sizes, accumulated with an
  overflow check. Symlinks contribute zero bytes.
- JSON schema version 1 is a machine-readable contract. Additive optional fields
  are allowed; changed meanings, renamed fields, or removals need a new version.
- Packages are under `internal`; there is no stable public Go API yet.

[Schema](report.schema.json) · [Demo report](../examples/demo/report.json)

## Verification

```sh
go test -race -cover ./...
go vet ./...
go test ./internal/policy -fuzz=FuzzMatchesOfficial -fuzztime=30s
go test ./internal/scan -bench=. -benchmem
```

Tests cover upstream differential matching, original line numbers, negation,
Dockerfile-specific precedence, symlinks, sparse files, hard links, unreadable
directories, special files, limits, deterministic output, escaping, and CI gates.
Some filesystem tests are skipped on Windows where symlink permissions vary.

The [CI workflow](../.github/workflows/ci.yml) runs tests, vet, and builds on Linux,
macOS, and Windows. Linux also checks formatting, a differential fuzz smoke test,
and exact reproduction of the committed JSON demo. Local checks are not evidence
that a later remote commit's CI passed; inspect that commit's run.

## Release engineering

[Release process](RELEASING.md) covers reproducible cross-builds, native install
checks, checksums, and unsigned build metadata. These scripts are separate from
the runtime CLI and do not add network behavior to scans.
