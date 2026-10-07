# Usage

[README](../README.md) · [Semantics](SEMANTICS.md) · [Limits](LIMITS.md)

## Install or build

For standalone binaries, see [binary installation](INSTALL.md).

Go 1.24 or newer is required. CI tests Linux, macOS, and Windows.

```sh
go install github.com/agent-axiom/ignoreimpact/cmd/ignoreimpact@latest
```

For a reproducible installation, replace `@latest` with a reviewed commit.
The binary is installed into `GOBIN`, or the Go workspace's `bin` directory;
ensure that directory is on your `PATH`.

From a checkout:

```sh
go build -trimpath -o bin/ignoreimpact ./cmd/ignoreimpact
./bin/ignoreimpact --help
```

Windows builds use `bin/ignoreimpact.exe`. The shell examples below use Unix
syntax; the CLI flags and JSON contract are the same on all supported platforms.

## Compare an edit

```sh
git show HEAD:.dockerignore > /tmp/before.dockerignore
ignoreimpact compare --before /tmp/before.dockerignore --after .dockerignore
```

Both policies see the **current working tree**, including untracked and hidden
files. This compares policy inclusion, not files from two Git revisions. A policy
edit with no change to included files produces an empty `changes` array.

Explicit policy paths are relative to the current working directory. The scan
root is `--context` (default `.`). Keep exported policies and redirected reports
outside the context, or exclude them, so they do not affect their own inventory.
An explicitly selected policy must exist.

Choose exactly one baseline selector:

| Selector | Meaning |
| --- | --- |
| `--before FILE` | Read an explicit policy |
| `--before-dockerfile FILE` | Discover the effective policy for a Dockerfile |
| `--before-empty` | Include everything by default |

The candidate has equivalent `--after`, `--after-dockerfile`, and `--after-empty`
selectors. Without one, it discovers the policy for root `Dockerfile`.

## Dockerfile-specific policies

```sh
ignoreimpact compare --before-dockerfile docker/dev.Dockerfile \
  --after-dockerfile docker/prod.Dockerfile --context .
```

Dockerfile selectors are relative to the context. Each side selects the first
available policy:

1. `<Dockerfile>.dockerignore`
2. Root `.dockerignore`
3. An empty policy

Policies are not merged. An empty Dockerfile-specific policy still takes
precedence over the root policy. See [matching semantics](SEMANTICS.md).

## Explain paths

```sh
ignoreimpact explain --policy .dockerignore src/app.go vendor/keep.go
ignoreimpact explain --dockerfile docker/prod.Dockerfile --json .env
```

Paths must be context-relative. Existence is not checked. Without `--policy` or
`--dockerfile`, selection uses root `Dockerfile` and the precedence above.
The result names the last matching rule, including ancestor-directory matches.
`rule: null` means default inclusion. Rules carry the original line number and
text, normalized pattern, and `include` or `exclude` action.

## CI gates

```sh
ignoreimpact compare --before /tmp/base.dockerignore --after .dockerignore \
  --json --fail-on added > /tmp/ignoreimpact.json
```

| Exit code | Meaning |
| --- | --- |
| `0` | Complete comparison; selected gates passed |
| `1` | Complete comparison; a requested gate failed |
| `2` | Invalid arguments, unreadable input, a limit reached, or another error |

| `--fail-on` | Fail when |
| --- | --- |
| `none` | Never based on the comparison; the default |
| `change` | Any file or symlink changes inclusion |
| `added` | Any file or symlink becomes included |
| `growth` | Net regular-file bytes increase |

`added` catches newly included zero-byte files and symlinks. Independently,
`--max-added-bytes N` fails when added regular-file bytes are **greater than** N,
even when removals make the net change negative. Combine it with any gate.
The complete report still prints on exit `1`. Scan failures return no report.
An output-stream failure may leave partial output and returns `2`.

See [CI adoption](CI.md) for ready-to-adapt workflows, safe policy extraction,
gate selection, and clean-checkout limitations. The source workflow pins an
immutable tool revision; the binary-only template requires a published release
and a reviewed archive checksum.

## Output

Human output displays up to 100 changed paths. Use `--limit=-1` for all,
`--limit=0` for the summary, or `--json` for the complete machine report.
Truncation of human output is stated explicitly and does not affect totals.

JSON uses `schema_version: 1` and contains:

- Policy sources and the number of visited filesystem entries
- Before, after, added, and removed totals
- Net byte change and a lexically sorted `changes` array
- Both policy decisions for every changed path

Byte counts are integers. Reports contain no timestamps or absolute context
root; explicit policy paths are preserved as supplied. JSON always includes
all retained changes. [Schema](report.schema.json) · [Example](../examples/demo/report.json)

Run `ignoreimpact --help` for the flag summary. Resource controls are documented
in [Limits](LIMITS.md).
