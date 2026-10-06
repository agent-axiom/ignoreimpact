# Limits and safety

[README](../README.md) · [Usage](USAGE.md) · [Semantics](SEMANTICS.md)

## Filesystem contract

- Use a stable filesystem. Scanning is not an atomic snapshot; intentionally
  hostile concurrent directory mutation is outside the contract.
- Symlink targets are not read or traversed. Rooted filesystem access prevents
  traversal outside the selected context.
- Explicit policy paths outside the context are allowed. Auto-discovered policy
  symlinks cannot escape the context. Selected policy inputs must be regular files.
- Unreadable directories fail the whole comparison, even when both policies
  exclude them. The tool does not silently skip incomplete subtrees.
- Included devices, FIFOs, sockets, and other special files cause an error.
  Special files excluded by both policies do not enter the report.
- Scanned paths and policy text must be valid UTF-8. Policy NUL bytes are rejected.
  Human output escapes control characters and non-ASCII text for terminal safety.

The scanner reads directory metadata and selected ignore-file contents. It does
not upload files, send telemetry, require Docker, or read regular-file bodies to
estimate size. Reports themselves contain filenames and rule text; review where
you store or share them. See [Security](../SECURITY.md).

## Resource bounds

| Resource | Default bound | Override |
| --- | --- | --- |
| Visited filesystem entries | 1,000,000 | `--max-entries N` |
| Changed entries retained | 100,000 | `--max-changes N` |
| Path depth | 256 components | Fixed |
| Policy size | 1 MiB | Fixed |
| Rules per policy | 10,000 | Fixed |
| Policy line length | Upstream reader limit, about 64 KiB | Fixed |

Configurable bounds must be positive. Exceeding a bound fails the comparison
with exit `2`; no partial inventory is reported as successful. `--limit` only
controls human output length, not scanning, totals, or JSON completeness.

The directory walker enumerates directory entries before visiting them. The
entry cap is a traversal limit, not an exact memory budget. Very wide directories
can require additional memory. Large regular files need only metadata reads.

## Outside the scope

Byte counts are logical regular-file sizes. They do not predict:

- Compressed context archives or actual BuildKit network transfers
- Final image size, cache invalidation, or Dockerfile execution
- `COPY`/`ADD` selection or build-time bind mounts
- Remote/Git contexts or multiple named contexts
- Secret detection or vulnerability risk

This tool compares local ignore-policy inclusion. A passing CI gate is not a
security certification. Empty-directory changes and directory metadata are not
part of its byte or change counts.
