#!/usr/bin/env python3
"""Reproduce pinned public-source measurements; never execute source-repo code.

Network access is only Git acquisition here, outside IgnoreImpact's runtime.
Requires Python 3.10+, Git, and an IgnoreImpact binary built from the pinned commit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "examples" / "case-studies"


def run(*args, **kwargs):
    return subprocess.check_output(args, **kwargs)


def git(repository, *args):
    return run("git", "--git-dir=" + str(repository), *args)


def safe_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("Unsafe tree path: " + repr(value))
    return path


def materialize(repository, revision, destination):
    """Raw Git blobs, without .git, archive attributes, smudge filters or LFS fetch."""
    entries = []
    skipped = []
    for entry in git(repository, "ls-tree", "-rz", "--full-tree", revision).split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8")
        safe_path(path)
        if mode == "160000" and kind == "commit":
            skipped.append(path)
            continue
        if kind != "blob" or mode not in ("100644", "100755", "120000"):
            raise ValueError("Unsupported tracked entry: " + path)
        entries.append((mode, oid, path))
    # One Git process avoids a separate process per file. Git trees cannot place
    # descendants under a symlink; still check every parent before writing.
    inventory = []
    with subprocess.Popen(["git", "--git-dir=" + str(repository), "cat-file", "--batch"],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        assert process.stdin is not None and process.stdout is not None
        for mode, oid, path in entries:
            process.stdin.write((oid + "\n").encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii").split()
            if len(header) != 3 or header[:2] != [oid, "blob"]:
                raise ValueError("Unexpected Git blob response")
            size = int(header[2])
            data = process.stdout.read(size)
            if len(data) != size or process.stdout.read(1) != b"\n":
                raise ValueError("Truncated Git blob")
            output = destination / path
            for parent in output.parents:
                if parent == destination:
                    break
                if parent.is_symlink():
                    raise ValueError("Symlink tree ancestor")
            output.parent.mkdir(parents=True, exist_ok=True)
            if mode == "120000":
                output.symlink_to(os.fsdecode(data))
            else:
                output.write_bytes(data)
                output.chmod(0o755 if mode == "100755" else 0o644)
            inventory.append({"path": path, "mode": mode, "blob": oid, "blob_bytes": size})
        process.stdin.close()
        if process.wait() != 0:
            raise ValueError("Git blob export failed")
    return inventory, skipped


def write_or_verify(path, data, record):
    if record:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    elif not path.exists() or path.read_bytes() != data:
        raise ValueError("Reproduction differs: " + str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ignoreimpact", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=ROOT / ".adoption-work" / "cases")
    parser.add_argument("--record", action="store_true", help="Explicitly update committed evidence")
    args = parser.parse_args()
    binary = args.ignoreimpact.resolve(strict=True)
    config = json.loads((CASES / "cases.json").read_text())
    version = run(str(binary), "version").decode().strip()
    if config["tool_commit"] not in version:
        raise ValueError("Build the binary with the documented SourceCommit ldflag")
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    for case in config["cases"]:
        for key in ("before_commit", "after_commit", "tree", "before_blob", "after_blob"):
            if not re.fullmatch(r"[0-9a-f]{40}", case[key]):
                raise ValueError("Expected immutable Git SHA: " + key)
        if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+\.git", case["repository"]):
            raise ValueError("Expected public GitHub repository URL")
        repository = work / (case["id"] + ".git")
        if not repository.exists():
            run("git", "init", "--bare", "--quiet", str(repository))
        git(repository, "fetch", "--quiet", "--depth=1", case["repository"],
            case["before_commit"], case["after_commit"])
        if git(repository, "rev-parse", case["after_commit"] + "^{tree}").decode().strip() != case["tree"]:
            raise ValueError("Source tree mismatch")
        evidence = CASES / case["id"]
        with tempfile.TemporaryDirectory(prefix=case["id"] + "-", dir=work) as tmp:
            temporary = Path(tmp)
            context = temporary / "context"
            context.mkdir()
            inventory, submodules = materialize(repository, case["after_commit"], context)
            for side in ("before", "after"):
                oid = git(repository, "rev-parse", case[side + "_commit"] + ":" + case["policy_path"]).decode().strip()
                if oid != case[side + "_blob"]:
                    raise ValueError("Policy blob mismatch")
                data = git(repository, "cat-file", "blob", oid)
                name = side + ".dockerignore"
                (temporary / name).write_bytes(data)
                write_or_verify(evidence / name, data, args.record)
            license_data = git(repository, "show", case["after_commit"] + ":" + case["license_path"])
            write_or_verify(evidence / "LICENSE.upstream", license_data, args.record)
            command = [str(binary), "compare", "--context", str(context), "--before", "before.dockerignore",
                       "--after", "after.dockerignore", "--json"]
            report_bytes = run(*command, cwd=temporary)
            if run(*command, cwd=temporary) != report_bytes:
                raise ValueError("Nondeterministic comparison")
            report = json.loads(report_bytes)
            if report["delta_bytes"] != report["added"]["bytes"] - report["removed"]["bytes"]:
                raise ValueError("Inconsistent report totals")
            write_or_verify(evidence / "report.json", report_bytes, args.record)
            provenance = {
                "tool_commit": config["tool_commit"], "repository": case["repository"],
                "source_commit": case["after_commit"], "source_tree": case["tree"],
                "inventory_sha256": hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                "tracked_blobs": len(inventory), "tracked_blob_bytes": sum(x["blob_bytes"] for x in inventory),
                "tracked_symlinks": sum(x["mode"] == "120000" for x in inventory),
                "omitted_submodules": submodules,
                "license_sha256": hashlib.sha256(license_data).hexdigest(),
                "before_policy_sha256": hashlib.sha256((temporary / "before.dockerignore").read_bytes()).hexdigest(),
                "after_policy_sha256": hashlib.sha256((temporary / "after.dockerignore").read_bytes()).hexdigest(),
                "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
                "snapshot": "Raw tracked Git blobs; no .git, filters, LFS downloads, dependency installation, additional generated files, or submodule contents.",
            }
            write_or_verify(evidence / "provenance.json", (json.dumps(provenance, indent=2) + "\n").encode(), args.record)
            print(f'{case["id"]}: {report["before"]["entries"]} -> {report["after"]["entries"]} entries; '
                  f'{report["before"]["bytes"]} -> {report["after"]["bytes"]} bytes; '
                  f'added {report["added"]["entries"]}/{report["added"]["bytes"]} B; '
                  f'removed {report["removed"]["entries"]}/{report["removed"]["bytes"]} B; '
                  f'delta {report["delta_bytes"]} B')


if __name__ == "__main__":
    main()
