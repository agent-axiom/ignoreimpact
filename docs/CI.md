# Adopt IgnoreImpact in CI

[Usage](USAGE.md) · [Measured public examples](CASE_STUDIES.md) · [Limits](LIMITS.md)

Use this check when reviewing ignore-policy edits: **which paths would this
policy include on the current tree?** It neither builds the image nor compares
file contents between commits.

## Start with one build context

1. Choose the context and Dockerfile used by the real build.
2. Copy the [source-install workflow](../examples/github-actions.yml) into
   `.github/workflows/ignoreimpact.yml`. Review its pinned tool and action commits.
   It works now with Go; no published IgnoreImpact release is required.
3. Start with `--fail-on none` if you want reports without blocking merges. The
   template uses the stricter `--fail-on added` once you are ready to gate.
4. Review the JSON in the job log, including removed files. A smaller context can
   break a build just as a larger one can expose an unintended path.

The [binary-only workflow](../examples/github-actions-binary.yml) is an
**unpublished-release template**, not a working download promise. Enable it only
when the selected release exists and you have reviewed and pinned its archive
SHA256. It deliberately rejects its placeholder checksum.

## What these workflows actually compare

- The base commit's root `.dockerignore` and the PR head commit's root
  `.dockerignore`, both evaluated against the **same checked-out PR head tree**.
- An absent policy at a verified commit means an empty policy, including on
  deletion. An unavailable/malformed commit is an error, never an empty policy.
- Policy inputs come from regular Git blobs. Symlinks, directories, submodules,
  and oversized policies are rejected; a working-tree `cp` must not follow a
  PR-controlled policy symlink.
- A root `Dockerfile.dockerignore` on either side stops this root-policy recipe.
  Adapt selection before using it for Dockerfile-specific builds.

The checkout is the PR head, not GitHub's synthetic merge commit. Dependencies,
LFS objects, submodules, build outputs, and caches are not installed/materialized
by this job. Untracked files already present in the runner and `.git` metadata
can still be scanned. IgnoreImpact follows neither file nor directory symlink
targets. Policies and reports are kept in the runner's temporary directory,
outside the context.

A clean checkout often has no `node_modules`, `.venv`, `dist`, or local secrets.
A zero delta does not show that an ignore rule is unnecessary, and it does not
predict the effect on a populated developer machine. For that question, repeat
the comparison locally against a stable, representative tree. Do not run
untrusted PR install/build scripts merely to make the report look realistic.

## Pick a gate deliberately

| Gate | Useful for | Important caveat |
| --- | --- | --- |
| `--fail-on none` | Review-only adoption | Operational failures still fail |
| `--fail-on added` | Prevent any newly included path | Includes zero-byte files and symlinks |
| `--fail-on growth` | Block net regular-file growth | Removals can hide newly included paths |
| `--fail-on change` | Require review of all inclusion changes | Intentional removals also fail |
| `--max-added-bytes 1048576` | Allow at most 1 MiB of added regular-file bytes | Combine with another gate; symlinks count zero bytes |

Exit `0` means a complete scan passed the selected gates. Exit `1` means a
complete report failed a gate. Exit `2` means a usage, input, traversal, resource,
or output error. Do not blanket `continue-on-error`, append `|| true`, or publish
an empty/partial report as success. The templates preserve the exit status and
print complete JSON for both `0` and `1`. Workflow-command processing is disabled
with a fresh random token while printing PR-controlled report text.

## Other CI systems and local review

Install a reviewed revision or verified binary separately from the checkout.
Supply two regular policy files outside the context, then run:

```sh
status=0
ignoreimpact compare --context /path/to/stable/context \
  --before /path/outside/context/before.dockerignore \
  --after /path/outside/context/after.dockerignore \
  --json --fail-on added > /path/outside/context/report.json || status=$?
if [ "$status" -gt 1 ]; then exit "$status"; fi
cat /path/outside/context/report.json
exit "$status"
```

For a Dockerfile such as `docker/build.Dockerfile`, resolve each revision's
`docker/build.Dockerfile.dockerignore`, then root `.dockerignore`, then an empty
policy. Extract the selected Git blob before scanning. Do not resolve the base
using only files in the head checkout. For a subdirectory context, policy paths
in Git are repository-relative while matching is context-relative. Keep these
separate. An empty Dockerfile-specific policy still overrides the root policy.

## Trust and reporting boundaries

Use the ordinary `pull_request` event with read-only permissions and an ephemeral
runner. Do not switch to `pull_request_target` to gain secrets or write access,
and do not run these jobs on a privileged persistent self-hosted runner for
untrusted forks. These workflows execute pinned tools and inline workflow code;
they do not execute repository-provided scripts. Go installation runs outside
the checkout with workspace discovery disabled. Normal platform workflow-review
and fork-approval controls still apply.

The scan itself has no network calls. Checkout, Go installation, and optional
binary download are separate CI setup steps. Reports contain paths and policy
text: review log/artifact visibility and retention before sharing them or adding
PR comments. The examples do not post comments or upload artifacts.

Passing is evidence about policy inclusion only. It is not secret detection,
a build test, compressed transfer size, final image size, or a speed benchmark.
