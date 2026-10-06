# Semantics

[README](../README.md) · [Usage](USAGE.md) · [Limits](LIMITS.md)

## Matching

Parsing and evaluation use [`moby/patternmatcher` v0.6.1](https://github.com/moby/patternmatcher/tree/v0.6.1),
including its ignore-file reader. The tool does not substitute Git ignore rules
or maintain an independent glob engine.

Negation, `**`, parent-directory matches, comments, whitespace normalization,
and BOM handling follow the pinned library. Matching follows the host OS;
Windows escaping differs from Unix. See Docker's
[ignore-file documentation](https://docs.docker.com/build/concepts/context/#dockerignore-files).

Rule explanations identify the last matching rule, even if an earlier rule made
the same decision. A matching rule can apply to the path or an ancestor directory.
An unmatched path is included by default.

For example:

```dockerignore
vendor
!vendor/keep.go
```

`vendor/keep.go` is included by the second rule. Other files under `vendor` remain
excluded. Excluded directories are traversed to find re-included descendants;
this is why an unreadable excluded directory still causes an error.

Dockerfile-specific selection uses `<Dockerfile>.dockerignore` before root
`.dockerignore`. They are not merged. Nested ignore files never introduce new
policies; they are ordinary files evaluated by the selected policy.

## What is counted

| Entry | Entries | Regular files | Symlinks | Bytes |
| --- | --- | --- | --- | --- |
| Regular file | 1 | 1 | 0 | Logical size from metadata |
| Symlink, including a broken link | 1 | 0 | 1 | 0 |
| Directory | 0 | 0 | 0 | 0 |

Hard links count once per path. Sparse files contribute logical size rather than
allocated disk space. Directories are included in `scanned_entries`, but not in
inclusion totals or `changes`. Empty-directory changes are outside the report.

Hidden files and `.git` are ordinary entries. They are included unless the
selected policy excludes them. The scanner never reads regular-file contents,
resolves symlink targets for reporting, or hashes file bodies.

## Two policies, one tree

Each non-directory path is evaluated under both policies against one current
filesystem tree. A path appears in `changes` only when its inclusion changes.
The same metadata size contributes to each side that includes it. Therefore:

```text
delta_bytes = after.bytes - before.bytes
            = added.bytes - removed.bytes
```

A policy edit that merely changes the winning rule, with no inclusion change,
produces no changed entry. Use `explain` to inspect that rule directly.

## Relationship to Docker and other tools

The report describes policy inclusion. Docker may send excluded build-control
files separately because the builder needs them. IgnoreImpact does not model
that transfer or Dockerfile execution. See the complete [scope limits](LIMITS.md).

[`docker-show-context`](https://github.com/pwaller/docker-show-context) helps
inspect context size. IgnoreImpact focuses on comparing two policies against the
same tree, with paired explanations and CI gates. The tools are complementary.
