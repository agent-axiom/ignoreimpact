# IgnoreImpact

[![CI](https://github.com/agent-axiom/ignoreimpact/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/agent-axiom/ignoreimpact/actions/workflows/ci.yml)
[![Go version](https://img.shields.io/github/go-mod/go-version/agent-axiom/ignoreimpact?logo=go)](go.mod)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)](.github/workflows/ci.yml)

**See what a `.dockerignore` change actually includes or excludes.**

Compare two policies against the same local tree. Get added and removed files,
byte impact, and the matching rule on each side. Use readable output for review
or deterministic JSON and exit-code gates in CI.

One Go binary. Official Moby matching. No Docker daemon or file uploads.

## Install

[Binary candidates, no Go required](docs/INSTALL.md) · [Release verification](docs/RELEASING.md)

```sh
go install github.com/agent-axiom/ignoreimpact/cmd/ignoreimpact@latest
```

## 10-second demo

From a checkout:

```sh
go run ./cmd/ignoreimpact compare \
  --context examples/demo/context \
  --before examples/demo/before.dockerignore \
  --after examples/demo/after.dockerignore
```

```text
Added:    1 entries | 18 B
Removed:  1 entries | 11 B
```

The demo includes `node_modules/cache.bin` and excludes `.env.example`: **+7 B**.
Each changed path also shows its before/after rule. [Full JSON output →](examples/demo/report.json)

[Reproduce the 28-second terminal demo](docs/DEMO.md).

## Read next

- [Usage](docs/USAGE.md): commands, policy selection, JSON, and CI gates
- [CI adoption](docs/CI.md) · [Reproducible public case studies](docs/CASE_STUDIES.md)
- [Semantics](docs/SEMANTICS.md): matching rules and byte accounting
- [Limits](docs/LIMITS.md): filesystem safety, resource bounds, and scope
- [Architecture](docs/ARCHITECTURE.md): code map, contracts, and tests
- [Agent guide](AGENTS.md): working on this repository
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [MIT license](LICENSE)

Bytes describe local regular-file sizes. Image size, actual build transfer, and
secret detection are outside the tool's scope. See [limits](docs/LIMITS.md).
