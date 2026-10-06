#!/usr/bin/env python3
"""Extract and exercise a native candidate archive with no Go executable on PATH."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
import zipfile


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or not path.parts:
        raise ValueError(f"unsafe archive member: {name!r}")
    return path.as_posix()


def extract(archive: Path, directory: Path) -> None:
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as source:
            for info in source.infolist():
                if info.is_dir():
                    continue
                mode = info.external_attr >> 16
                if mode & 0o170000 not in (0, 0o100000):
                    raise ValueError("archive contains a non-regular entry")
                destination = directory / safe_name(info.filename)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read(info))
                destination.chmod(mode & 0o777 or 0o644)
    else:
        with tarfile.open(archive, "r:gz") as source:
            for info in source.getmembers():
                if not info.isfile():
                    raise ValueError("archive contains a non-regular entry")
                destination = directory / safe_name(info.name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                stream = source.extractfile(info)
                require(stream is not None, "unreadable archive member")
                destination.write_bytes(stream.read())
                destination.chmod(info.mode)


def smoke(archive: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="ignoreimpact-install-") as tmp:
        root = Path(tmp)
        extract(archive, root)
        metadata = json.loads((root / "BUILDINFO.json").read_text())
        binary = root / ("ignoreimpact.exe" if os.name == "nt" else "ignoreimpact")
        require(hashlib.sha256(binary.read_bytes()).hexdigest() == metadata["binary_sha256"], "binary checksum mismatch")
        # Empty PATH models installation on a machine without Go; the CLI may not spawn tools.
        env = dict(os.environ, PATH="")
        def run(*args: str, expected: int = 0) -> str:
            result = subprocess.run([str(binary), *args], cwd=root, env=env, capture_output=True,
                                    text=True, timeout=30)
            require(result.returncode == expected, repr((args, result.returncode, result.stdout, result.stderr)))
            return result.stdout
        expected_version = f"ignoreimpact {metadata['version']} ({metadata['source_commit']})\n"
        require(run("version") == expected_version, "version identity mismatch")
        args = ("compare", "--context", "examples/demo/context", "--before", "examples/demo/before.dockerignore",
                "--after", "examples/demo/after.dockerignore")
        actual = json.loads(run(*args, "--json"))
        expected_report = json.loads((root / "examples/demo/report.json").read_text())
        require(actual == expected_report, "installed binary does not reproduce committed fixture")
        require(actual["added"]["bytes"] == 18 and actual["removed"]["bytes"] == 11, "unexpected fixture totals")
        require(json.loads(run(*args, "--json", "--fail-on", "added", expected=1)) == actual, "CI gate report differs")
        run("compare", "--before", "missing-policy", expected=2)
        run("explain", "--policy", "examples/demo/after.dockerignore", ".env.example")
        require((root / "LICENSE").is_file(), "missing project license")
        for name in ("moby-patternmatcher.txt", "moby-patternmatcher-NOTICE.txt", "go.txt"):
            require((root / "THIRD_PARTY_LICENSES" / name).is_file(), f"missing license or notice: {name}")
        result = {"archive": archive.name, "target": metadata["target"],
                  "version": metadata["version"], "source_commit": metadata["source_commit"],
                  "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                  "host_system": platform.system(), "host_machine": platform.machine(),
                  "path_during_test": "", "checks": ["version", "json_fixture", "exit_0_1_2", "explain", "licenses"],
                  "result": "passed"}
        print(json.dumps(result, indent=2))
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = smoke(args.archive)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
