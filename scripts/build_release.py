#!/usr/bin/env python3
"""Build deterministic, unsigned release candidates from a clean Git checkout."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/agent-axiom/ignoreimpact"
CLI_PACKAGE = "github.com/agent-axiom/ignoreimpact/internal/cli"
VERSION_RE = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z")


def command(*args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.check_output(args, cwd=ROOT, env=env, text=True).strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def validate_version(version: str) -> str:
    if len(version) > 128 or not VERSION_RE.fullmatch(version):
        raise ValueError("version must be a numeric semver, optionally with a prerelease suffix")
    if "-" in version:
        for identifier in version.split("-", 1)[1].split("."):
            if identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0"):
                raise ValueError("numeric prerelease identifiers cannot have leading zeros")
    return version


def archive_bytes(files: dict[str, tuple[bytes, int]], epoch: int, windows: bool) -> bytes:
    """Normalize order, ownership, timestamps and permissions; never archive paths from disk implicitly."""
    result = io.BytesIO()
    if windows:
        stamp = time.gmtime(max(epoch, 315532800))[:6]  # ZIP starts in 1980.
        with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, (data, mode) in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=stamp)
                info.create_system = 3
                info.external_attr = (0o100000 | mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data, compresslevel=9)
    else:
        with gzip.GzipFile(filename="", fileobj=result, mode="wb", mtime=0, compresslevel=9) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, (data, mode) in sorted(files.items()):
                    info = tarfile.TarInfo(name)
                    info.size, info.mode, info.mtime = len(data), mode, epoch
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info, io.BytesIO(data))
    return result.getvalue()


def base_files(dependency_dir: Path) -> dict[str, tuple[bytes, int]]:
    files = {
        "LICENSE": ((ROOT / "LICENSE").read_bytes(), 0o644),
        "INSTALL.txt": ((ROOT / "release/INSTALL.txt").read_bytes(), 0o644),
        "THIRD_PARTY_LICENSES/moby-patternmatcher.txt": ((dependency_dir / "LICENSE").read_bytes(), 0o644),
        "THIRD_PARTY_LICENSES/moby-patternmatcher-NOTICE.txt": ((dependency_dir / "NOTICE").read_bytes(), 0o644),
        "THIRD_PARTY_LICENSES/go.txt": ((Path(command("go", "env", "GOROOT")) / "LICENSE").read_bytes(), 0o644),
    }
    for path in sorted((ROOT / "examples/demo").rglob("*")):
        if path.is_file():
            files[path.relative_to(ROOT).as_posix()] = (path.read_bytes(), 0o644)
    return files


def build(output: Path, version: str | None = None) -> dict:
    config = json.loads((ROOT / "release/config.json").read_text())
    version = validate_version(version or config["version"])
    commit = command("git", "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("a full Git commit is required")
    if command("git", "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("release builds require a clean checkout, including untracked source files")
    tree = command("git", "rev-parse", "HEAD^{tree}")
    epoch = int(command("git", "show", "-s", "--format=%ct", "HEAD"))
    goversion = command("go", "env", "GOVERSION")
    if goversion != config["go_version"]:
        raise ValueError(f"expected {config['go_version']}, found {goversion}")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty; existing artifacts are never overwritten")
    output.mkdir(parents=True, exist_ok=True)
    dependency = json.loads(command("go", "list", "-m", "-json", "github.com/moby/patternmatcher"))
    common = base_files(Path(dependency["Dir"]))
    flags = ["-trimpath", "-buildvcs=false", "-ldflags",
             f"-s -w -buildid= -X {CLI_PACKAGE}.Version={version} -X {CLI_PACKAGE}.SourceCommit={commit}"]
    manifest = {
        "schema_version": 1,
        "project": "IgnoreImpact",
        "version": version,
        "source": {"repository": REPOSITORY, "commit": commit, "tree": tree, "dirty": False},
        "build": {"go_version": goversion, "flags": flags, "cgo_enabled": False,
                  "goamd64": "v1", "goarm64": "v8.0",
                  "go_mod_sha256": sha256((ROOT / "go.mod").read_bytes()),
                  "go_sum_sha256": sha256((ROOT / "go.sum").read_bytes())},
        "dependencies": [{"module": dependency["Path"], "version": dependency["Version"],
                          "sum": dependency["Sum"]}],
        "verification": {"signatures": "none", "attestation": "none",
                         "native_smoke_tests": "see associated Release candidate workflow run"},
        "assets": [],
    }
    # Workflow provenance is a separate unsigned statement, not part of deterministic archives.
    provenance = {
        "schema_version": 1, "signed": False,
        "statement": "Unsigned build metadata; not a cryptographic attestation or platform code signature.",
        "source_commit": commit, "version": version,
        "builder": "GitHub Actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "local",
        "workflow_run_url": None,
    }
    if os.environ.get("GITHUB_ACTIONS") == "true":
        provenance["workflow_run_url"] = (
            f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
            f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        )
    for target in config["targets"]:
        goos, goarch = target.split("/")
        windows = goos == "windows"
        binary_name = "ignoreimpact.exe" if windows else "ignoreimpact"
        env = dict(os.environ, GOOS=goos, GOARCH=goarch, CGO_ENABLED="0", GOAMD64="v1", GOARM64="v8.0")
        with tempfile.TemporaryDirectory(prefix="ignoreimpact-build-") as tmp:
            binary = Path(tmp) / binary_name
            subprocess.run(["go", "build", *flags, "-o", str(binary), "./cmd/ignoreimpact"],
                           cwd=ROOT, env=env, check=True)
            build_info = command("go", "version", "-m", str(binary))
            for expected in (f"GOOS={goos}", f"GOARCH={goarch}", "CGO_ENABLED=0"):
                if expected not in build_info:
                    raise ValueError(f"binary build metadata is missing {expected}")
            binary_data = binary.read_bytes()
        metadata = {"version": version, "source_commit": commit, "target": target,
                    "go_version": goversion, "binary_sha256": sha256(binary_data),
                    "publisher_signature": False}
        files = dict(common)
        files[binary_name] = (binary_data, 0o755)
        files["BUILDINFO.json"] = (json_bytes(metadata), 0o644)
        extension = "zip" if windows else "tar.gz"
        name = f"ignoreimpact_{version}_{goos}_{goarch}.{extension}"
        data = archive_bytes(files, epoch, windows)
        (output / name).write_bytes(data)
        manifest["assets"].append({"name": name, "target": target, "bytes": len(data),
                                   "sha256": sha256(data), "binary_sha256": sha256(binary_data)})
        print(f"Built {name}: {len(data)} bytes", flush=True)
    (output / "release-manifest.json").write_bytes(json_bytes(manifest))
    provenance["release_manifest_sha256"] = sha256((output / "release-manifest.json").read_bytes())
    (output / "provenance.json").write_bytes(json_bytes(provenance))
    checksums = "".join(f"{sha256(p.read_bytes())}  {p.name}\n" for p in sorted(output.iterdir()))
    (output / "SHA256SUMS").write_text(checksums, encoding="utf-8", newline="\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--version", help="override the checked-in candidate version")
    args = parser.parse_args()
    try:
        build(args.output, args.version)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"release build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
