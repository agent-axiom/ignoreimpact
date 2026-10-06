# IgnoreImpact

**Review what a `.dockerignore` change actually does.**

IgnoreImpact compares two Docker ignore policies against **the same local tree**.
It shows which files become included or excluded, their byte impact, and the
matching rule on each side. One small Go binary. No Docker daemon, telemetry,
file uploads, or content hashing.

```text
+ "node_modules/cache.bin" (file, 18 B)
    before: exclude by line 1 "node_modules"
    after:  included by default
- ".env.example" (file, 11 B)
    before: included by default
    after:  exclude by line 1 ".env*"
```

Use it when reviewing a policy edit, tightening a build context, or preventing
unexpected inclusion in CI. It does not assess whether a file is a secret.

## Install

Requires Go 1.24 or newer to build. Linux, macOS, and Windows are tested in CI.

```sh
go install github.com/agent-axiom/ignoreimpact/cmd/ignoreimpact@latest
```

Or build the checked-out source:

```sh
go build -trimpath -o bin/ignoreimpact ./cmd/ignoreimpact
```

No registry release or prebuilt binaries are required. To reproduce an exact
build, install using a reviewed commit instead of `@latest`.

## Try it in 10 seconds

From this repository, after building:

```sh
./bin/ignoreimpact compare \
  --context examples/demo/context \
  --before examples/demo/before.dockerignore \
  --after examples/demo/after.dockerignore
```

This intentionally removes the `node_modules` exclusion and adds `.env*`.
The result is 18 added bytes, 11 removed bytes, and a net increase of 7 bytes.
The fixture contains sample data only.

## Compare a policy edit

```sh
git show HEAD:.dockerignore > /tmp/before.dockerignore
ignoreimpact compare --before /tmp/before.dockerignore --after .dockerignore
```

Both policies see the current working tree, including untracked and hidden
files. This is a **policy diff**, not a diff between Git revisions. A changed
policy that includes the same files produces no changes.

Explicit policy paths are relative to the current working directory. The scan
root is `--context` (default `.`). Keep exported policies and redirected reports
outside the context, or exclude them, so they don't affect their own inventory.

### Dockerfile-specific policies

```sh
ignoreimpact compare --before-dockerfile docker/dev.Dockerfile \
  --after-dockerfile docker/prod.Dockerfile --context .
```

Dockerfile paths are relative to the context. For each side, the tool selects
`<Dockerfile>.dockerignore`, then root `.dockerignore`, then an empty policy.
These files are **not merged**. With no candidate selector, the Dockerfile is
`Dockerfile`. Choose `--before-empty` or `--after-empty` for no exclusions.
An explicit policy must exist; a missing auto-discovered policy is normal.

### Explain a path

```sh
ignoreimpact explain --policy .dockerignore src/app.go vendor/keep.go
ignoreimpact explain --dockerfile docker/prod.Dockerfile --json .env
```

This evaluates paths without checking their existence. It identifies the last
matching rule, including a rule that matches an ancestor directory. `rule: null`
means default inclusion. Rules retain their original line number and text, plus
the normalized pattern used by Moby.

## CI: make the policy visible

```sh
ignoreimpact compare --before /tmp/base.dockerignore --after .dockerignore \
  --json --fail-on added > /tmp/ignoreimpact.json
```

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | Complete comparison; selected gates passed |
| `1` | Complete comparison; a requested gate failed |
| `2` | Invalid arguments, unreadable input, limit reached, or another error |

`--fail-on` accepts `none` (default), `change`, `added`, or `growth`. `growth`
uses the net byte difference; `added` also catches newly included zero-byte
files and symlinks. `--max-added-bytes N` independently fails when added bytes
are **greater than** N, even if removals make the net change negative. It can be
combined with any `--fail-on` mode. Machine output still prints on exit `1`.

JSON has `schema_version: 1`, integer byte counts, policy sources, before/after
totals, added/removed totals, and a lexically sorted `changes` array. There are
no timestamps or absolute context paths. Human output defaults to 100 changes;
`--limit=-1` displays all. JSON always contains every retained change. See
[the schema](docs/report.schema.json) and [the committed demo](examples/demo/report.json).

A [GitHub Actions example](examples/github-actions.yml) shows how to compare a
PR's policy with its base version without executing PR code.

## Semantics and limits

- Parsing and matching use [`moby/patternmatcher` v0.6.1](https://github.com/moby/patternmatcher/tree/v0.6.1), including its ignore-file reader. No Git ignore substitution or custom glob syntax.
- Negation, `**`, parent-directory matches, comments, whitespace, and BOM handling follow that library. [Docker documents the policy rules and precedence](https://docs.docker.com/build/concepts/context/#dockerignore-files).
- Excluded directories are still traversed to find re-included descendants. An unreadable directory is an error, including one excluded by both policies. Nothing is silently skipped.
- Regular files contribute logical size from metadata. Hard links count once per path; sparse files count logical bytes. Directories and filesystem metadata do not contribute bytes or change entries. Empty-directory changes are outside this tool's scope.
- Symlinks, including broken links, contribute one entry and zero bytes. Their targets are not read or traversed. A rooted filesystem handle prevents traversal outside the selected context. Explicit external policy paths are intentionally allowed; auto-discovered policy symlinks cannot escape the context.
- Included special files (devices, FIFOs, sockets) cause an error. Hidden files, `.git`, and nested `.dockerignore` files are ordinary entries unless the selected policy excludes them. Nested ignore files do not introduce additional policies.
- Limits default to 1,000,000 visited entries, 100,000 changed entries, depth 256, 1 MiB per policy, 10,000 rules, and the upstream reader's line limit (about 64 KiB). `--max-entries` and `--max-changes` are configurable positive bounds. Exceeding a bound fails the whole comparison.
- Paths and policies must be valid UTF-8; NUL policy bytes are rejected. Human output escapes control characters and non-ASCII text to avoid terminal injection. Matching follows the host OS, as the upstream library does; Windows escaping differs from Unix.
- The filesystem must remain stable while scanning. This is not an atomic snapshot, and intentionally hostile concurrent directory mutation is outside the contract.

Byte impact is **not** Docker's compressed upload size, actual BuildKit transfer,
cache invalidation, or final-image size. Docker may still send excluded build
control files separately. IgnoreImpact reports their policy inclusion, without
pretending to model build execution, `COPY` selection, remote/Git contexts, or
named contexts. It is not a security scanner.

## Why another tool?

[`docker-show-context`](https://github.com/pwaller/docker-show-context) already
helps inspect context size. IgnoreImpact focuses on the review question:
“Given the same tree, what changed when this ignore policy changed?” Its output
pairs each changed path with both policy decisions and offers explicit CI gates.
These tools are complementary; this project does not claim to be first or best.

## Development

```sh
go test -race -cover ./...
go vet ./...
go test ./internal/policy -fuzz=FuzzMatchesOfficial -fuzztime=30s
go test ./internal/scan -bench=. -benchmem
```

The implementation is split into policy parsing/evaluation, bounded traversal,
reporting, and command-line behavior. Tests cover Docker-style edge cases,
upstream differential fuzzing, nested negation, symlinks, sparse files, limits,
terminal escaping, deterministic output, and CI exit codes. There are no
frameworks, background services, or AI dependencies.

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).
