#!/usr/bin/env python3
"""Hermetic recorder/render integrity tests using the Python standard library."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

import record_demo
import render_demo


class CaptureTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "PTY recording requires POSIX")
    def test_captures_real_pty_output_and_exit(self):
        status, chunks, duration = record_demo.capture(
            "printf 'actual output\\n'; exit 1", record_demo.ROOT, dict(os.environ))
        self.assertEqual(status, 1)
        self.assertEqual(b"".join(data for _, data in chunks), b"actual output\r\n")
        self.assertGreaterEqual(duration, 0)

    def test_multiline_prompt_resets_column(self):
        self.assertEqual(record_demo.prompt("command \\\n  --flag"),
                         "$ command \\\r\n    --flag\r\n")


class RenderTests(unittest.TestCase):
    def test_timeline_is_28_seconds(self):
        self.assertEqual(sum(scene[1] for scene in render_demo.TIMELINE), 28)

    def test_wrapping_preserves_terminal_characters(self):
        output = "a" * 120 + "  end\n"
        scene = {"transcript": [{"command": "echo actual", "output": output}]}
        lines = render_demo.terminal_lines(scene)
        self.assertEqual(lines[0], "$ echo actual")
        self.assertEqual("".join(lines[1:]), output.rstrip("\n"))
        self.assertTrue(all(len(line) <= 92 for line in lines))

    def test_non_ascii_requires_explicit_width_handling(self):
        with self.assertRaisesRegex(ValueError, "width-aware"):
            render_demo.terminal_lines({"transcript": [{"command": "echo", "output": "漢字"}]})

    def test_rejects_tampered_captured_output_before_rendering(self):
        work = record_demo.ROOT / ".tools"
        work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as temp:
            directory = Path(temp)
            data = b"real\r\n"
            (directory / "demo.pty").write_bytes(data)
            record = {"scene": "demo", "cwd": ".", "command": "echo real", "exit_code": 0,
                      "pty_file": "demo.pty", "pty_sha256": hashlib.sha256(data).hexdigest()}
            (directory / "manifest.json").write_text(json.dumps({"commands": [record]}))
            scene = {"id": "demo", "cwd": ".", "transcript": [
                {"command": "echo real", "exit_code": 0, "output": "invented\n"}]}
            (directory / "storyboard.json").write_text(json.dumps({"scenes": [scene]}))
            with self.assertRaisesRegex(ValueError, "differs from raw PTY"):
                render_demo.render(directory, Path("/unused"))
            # The raw bytes cannot be edited underneath the manifest either.
            (directory / "demo.pty").write_bytes(b"invented\r\n")
            with self.assertRaisesRegex(ValueError, "PTY file changed"):
                render_demo.render(directory, Path("/unused"))


if __name__ == "__main__":
    unittest.main()
