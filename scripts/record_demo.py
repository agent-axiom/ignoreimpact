#!/usr/bin/env python3
"""Execute the bundled demo and preserve genuine PTY output plus a paced storyboard.

Python 3.10+, POSIX, Git and Go 1.24+. No media dependencies are needed to record.
Run from any directory; commands run at the documented repository-relative cwd.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture(command: str, cwd: Path, env: dict[str, str]):
    """Run the exact displayed shell command through a PTY; capture unchanged bytes."""
    # Keep module import portable for non-recording tests. PTY capture itself
    # is explicitly a POSIX-only authoring operation.
    import fcntl
    import pty
    import termios

    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 96, 0, 0))
    start = time.monotonic()
    process = subprocess.Popen(["/bin/sh", "-c", command], cwd=cwd, env=env,
                               stdin=subprocess.DEVNULL, stdout=slave, stderr=slave)
    os.close(slave)
    chunks = []
    try:
        while True:
            try:
                chunk = os.read(master, 65536)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            chunks.append((round(time.monotonic() - start, 6), chunk))
    finally:
        os.close(master)
    status = process.wait()
    return status, chunks, round(time.monotonic() - start, 6)


def prompt(command: str) -> str:
    return "$ " + command.replace("\n", "\r\n  ") + "\r\n"


def record(destination: Path, go: str | None = None):
    source_paths = ["cmd", "internal", "go.mod", "go.sum", "examples/demo"]
    source_status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *source_paths],
        cwd=ROOT, text=True)
    if source_status:
        raise ValueError("CLI or fixture sources differ from HEAD; review before recording")
    destination.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, LC_ALL="C", LANG="C", TERM="xterm-256color",
               NO_COLOR="1", GOWORK="off", GOTOOLCHAIN="local")
    if go:
        go_path = Path(go).resolve(strict=True)
        if go_path.name != "go":
            raise ValueError("--go must point to a Go executable named go")
        env["PATH"] = str(go_path.parent) + os.pathsep + env.get("PATH", "")
    # Respect explicit cache configuration. Keep auto-selected local caches in
    # the ignored tool directory instead of depending on a writable home.
    for variable, directory in (("GOCACHE", "go-cache"), ("GOPATH", "go-path")):
        env.setdefault(variable, str(ROOT / ".tools" / directory))
    gate_report = destination / "gated-report.txt"
    gate_relative = os.path.relpath(gate_report, ROOT / "examples/demo")
    scenes = [
        {"id": "build", "cwd": ".", "commands": [
            "go version",
            "go build -trimpath -o bin/ignoreimpact ./cmd/ignoreimpact",
        ]},
        {"id": "policies", "cwd": "examples/demo", "commands": [
            "cat before.dockerignore", "cat after.dockerignore",
        ]},
        {"id": "compare", "cwd": "examples/demo", "commands": [
            "../../bin/ignoreimpact compare --context context \\\n  --before before.dockerignore --after after.dockerignore",
        ]},
    ]
    scenes.append({"id": "gate", "cwd": "examples/demo", "expected_exit": 1, "commands": [
        "../../bin/ignoreimpact compare --context context \\\n  --before before.dockerignore --after after.dockerignore \\\n  --fail-on added > " + shlex.quote(gate_relative) +
        "\nstatus=$?; printf 'exit=%s\\n' \"$status\"; exit \"$status\"",
    ]})
    events, commands, elapsed, raw_parts = [], [], 0.0, []
    for scene in scenes:
        events.append([round(elapsed, 6), "o", "\x1b[2J\x1b[H"])
        text_parts = []
        for index, command in enumerate(scene.pop("commands")):
            displayed = prompt(command)
            events.append([round(elapsed, 6), "o", displayed])
            code, chunks, duration = capture(command, ROOT / scene["cwd"], env)
            data = b"".join(chunk for _, chunk in chunks)
            name = f"{scene['id']}-{index + 1}.pty"
            (destination / name).write_bytes(data)
            for offset, chunk in chunks:
                events.append([round(elapsed + offset, 6), "o", chunk.decode("utf-8")])
            elapsed += duration + 0.01
            output = data.decode("utf-8").replace("\r\n", "\n")
            if "\x1b" in output or any(ord(c) < 32 and c not in "\n\t" for c in output):
                raise ValueError("Unexpected terminal control byte in command output")
            text_parts.append({"command": command, "output": output, "exit_code": code})
            commands.append({"scene": scene["id"], "cwd": scene["cwd"],
                             "command": command, "exit_code": code,
                             "duration_seconds": duration, "pty_file": name,
                             "pty_sha256": sha256(data)})
            raw_parts.extend([displayed, data.decode("utf-8")])
            if code != scene.get("expected_exit", 0):
                raise RuntimeError(f"Demo command exited unexpectedly ({code}): {command}")
        scene["transcript"] = text_parts
    comparison = next(scene for scene in scenes if scene["id"] == "compare")
    if gate_report.read_text() != comparison["transcript"][0]["output"]:
        raise ValueError("CI gate did not preserve the complete comparison report")
    # Independent, non-PTY JSON runs check the report and reproducibility. The
    # root-relative invocation must match the existing committed golden report.
    verify_command = [str(ROOT / "bin/ignoreimpact"), "compare", "--context", "examples/demo/context",
                      "--before", "examples/demo/before.dockerignore", "--after", "examples/demo/after.dockerignore", "--json"]
    report = subprocess.check_output(verify_command, cwd=ROOT, env=env)
    if report != subprocess.check_output(verify_command, cwd=ROOT, env=env):
        raise ValueError("Repeated JSON output differs")
    if report != (ROOT / "examples/demo/report.json").read_bytes():
        raise ValueError("JSON output differs from committed demo golden")
    value = json.loads(report)
    if (value["added"]["entries"], value["added"]["bytes"], value["removed"]["entries"],
            value["removed"]["bytes"], value["delta_bytes"]) != (1, 18, 1, 11, 7):
        raise ValueError("Unexpected demo result")
    (destination / "report.json").write_bytes(report)
    input_files = sorted((ROOT / "examples/demo").rglob("*"))
    manifest = {
        "format": 1,
        "recorder_sha256": sha256(Path(__file__).read_bytes()),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_status": source_status,
        "source_diff": subprocess.check_output(["git", "diff", "HEAD", "--", "cmd", "internal", "go.mod", "go.sum", "examples/demo"], cwd=ROOT, text=True),
        "binary_sha256": sha256((ROOT / "bin/ignoreimpact").read_bytes()),
        "inputs": {str(path.relative_to(ROOT)): sha256(path.read_bytes()) for path in input_files if path.is_file()},
        "commands": commands,
        "checks": {"all_recorded_commands_have_expected_exit": True, "added_gate_exit": 1,
                   "gate_preserves_complete_report": True, "json_repeated_identically": True,
                   "json_matches_committed_golden": True, "added_entries": 1, "added_bytes": 18,
                   "removed_entries": 1, "removed_bytes": 11, "delta_bytes": 7},
        "timing_note": "Raw PTY timings are in session.cast. The video/GIF use a 28-second illustrative reading pace, not a performance benchmark.",
    }
    if manifest["source_diff"]:
        raise ValueError("CLI or fixture sources differ from HEAD; review before recording")
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (destination / "storyboard.json").write_text(json.dumps({"format": 1, "scenes": scenes}, indent=2) + "\n")
    (destination / "transcript.txt").write_text("\n".join(raw_parts).replace("\r\n", "\n"))
    header = {"version": 2, "width": 96, "height": 30, "duration": round(elapsed, 6),
              "title": "IgnoreImpact: actual source build and bundled demo", "env": {"TERM": "xterm-256color", "SHELL": "/bin/sh"}}
    (destination / "session.cast").write_text("\n".join(json.dumps(x) for x in [header, *events]) + "\n")
    print(f"Recorded {len(commands)} commands with expected exit codes; JSON matched twice and the committed golden.")
    print(f"Source {manifest['source_commit']}; output {destination.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/demo")
    parser.add_argument("--go", help="Optional Go executable; prepended to PATH")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or not output.is_relative_to(ROOT):
        parser.error("Keep the output directory inside this checkout")
    if output.is_relative_to(ROOT / "examples/demo"):
        parser.error("Keep generated output outside the measured demo fixture")
    record(output, args.go)


if __name__ == "__main__":
    main()
