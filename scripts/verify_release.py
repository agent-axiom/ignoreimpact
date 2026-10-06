#!/usr/bin/env python3
"""Verify candidate hashes and source identity, and optionally collect native smoke evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory: Path, commit: str, smoke_dir: Path | None = None) -> dict:
    manifest = json.loads((directory / "release-manifest.json").read_text())
    require(manifest["source"]["commit"] == commit, "unexpected source commit")
    require(not manifest["source"]["dirty"], "dirty source tree")
    recorded = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        value, name = line.split("  ", 1)
        require(Path(name).name == name and name not in recorded and name not in (".", ".."), "invalid checksum entry")
        require(digest(directory / name) == value, f"checksum mismatch: {name}")
        recorded[name] = value
    expected_names = {item["name"] for item in manifest["assets"]} | {"release-manifest.json", "provenance.json"}
    require(expected_names <= recorded.keys(), "missing checksum entries")
    for asset in manifest["assets"]:
        require(recorded[asset["name"]] == asset["sha256"], "manifest/archive mismatch")
        require((directory / asset["name"]).stat().st_size == asset["bytes"], "archive size mismatch")
    provenance = json.loads((directory / "provenance.json").read_text())
    require(provenance["source_commit"] == commit and provenance["signed"] is False, "invalid provenance identity")
    require(provenance["release_manifest_sha256"] == digest(directory / "release-manifest.json"), "provenance manifest checksum mismatch")
    verification = {"source_commit": commit, "version": manifest["version"], "checksums": "passed", "native_smoke_tests": []}
    if smoke_dir is not None:
        reports = [json.loads(path.read_text()) for path in sorted(smoke_dir.rglob("smoke-*.json"))]
        require(len(reports) == len(manifest["assets"]), "expected one native smoke result per target")
        by_target = {item["target"]: item for item in reports}
        require(len(by_target) == len(reports), "duplicate smoke target")
        for asset in manifest["assets"]:
            result = by_target[asset["target"]]
            require(result["result"] == "passed" and result["path_during_test"] == "", "native smoke did not pass without Go")
            require(result["source_commit"] == commit and result["version"] == manifest["version"], "smoke identity mismatch")
            require(result["archive_sha256"] == asset["sha256"], "smoke archive checksum mismatch")
        verification["native_smoke_tests"] = reports
        (directory / "VERIFICATION.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
        # Preserve archive bytes and add the verification record to the checksum index.
        paths = sorted(p for p in directory.iterdir() if p.name != "SHA256SUMS")
        (directory / "SHA256SUMS").write_text("".join(f"{digest(p)}  {p.name}\n" for p in paths), encoding="utf-8", newline="\n")
    print(json.dumps(verification, indent=2))
    return verification


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--smoke-dir", type=Path)
    args = parser.parse_args()
    verify(args.directory, args.commit, args.smoke_dir)
