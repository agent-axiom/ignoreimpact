# Contributing

Small, focused pull requests are welcome. Open an issue before a large change.

Start with the [architecture](docs/ARCHITECTURE.md) and
[repository guide](AGENTS.md). User-facing details live in focused documents
linked from the README.

1. Add a failing test that demonstrates the issue.
2. Make the smallest clear change that fixes it.
3. Run `go test -race ./...`, `go vet ./...`, and `gofmt`.
4. Explain any user-visible behavior or JSON contract change.

Matching belongs to Moby. Please do not introduce an independent glob engine.
Compare behavior against the pinned upstream version and link authoritative
Docker/Moby evidence when changing semantics. Do not add network calls to scans,
file-body reads for size estimation, or silent partial-success behavior.

Version 1 report fields are a machine-readable contract. New optional fields may
be added; renaming, removing, or changing field meanings needs a schema version
change. There is no stable public Go API yet; packages live under `internal`.

Please use synthetic fixtures. Never commit real credentials, production files,
or private paths. The project's MIT license applies to contributions.
