"""Synthetic, offline regression checks for the copyable CI workflow scripts."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = (ROOT / "examples/github-actions.yml", ROOT / "examples/github-actions-binary.yml")


def run_block(path, name):
    """Extract our fixed-indentation literal run blocks without a YAML dependency."""
    lines = path.read_text().splitlines()
    start = lines.index("      - name: " + name)
    begin = next(i for i in range(start, len(lines)) if lines[i] == "        run: |") + 1
    end = begin
    while end < len(lines) and (not lines[end] or lines[end].startswith("          ")):
        end += 1
    return "\n".join(line[10:] for line in lines[begin:end]) + "\n"


class CIExamplesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.runner = self.root / "runner"
        self.runner.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Synthetic Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.repo / ".keep").write_text("fixture\n")
        self.envfile = self.root / "github-env"

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo).decode().strip()

    def commit(self, policy, kind="file", specific=False):
        path = self.repo / ".dockerignore"
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        if kind == "symlink":
            path.symlink_to(policy)
        elif kind == "directory":
            path.mkdir()
            (path / "child").write_text("not a policy")
        elif policy is not None:
            path.write_bytes(policy)
        if specific:
            (self.repo / "Dockerfile.dockerignore").write_bytes(b"")
        self.git("add", "-A")
        self.git("commit", "--quiet", "--allow-empty", "-m", "Synthetic fixture")
        return self.git("rev-parse", "HEAD")

    def extract(self, base, head, success=True):
        env = dict(os.environ, BASE_SHA=base, HEAD_SHA=head,
                   RUNNER_TEMP=str(self.runner), GITHUB_ENV=str(self.envfile))
        result = subprocess.run(["bash", "-e", "-c", run_block(EXAMPLES[0], "Extract regular policy blobs")],
                                cwd=self.repo, env=env, capture_output=True)
        self.assertEqual(result.returncode == 0, success, result.stderr.decode())
        if not success:
            self.assertFalse(self.envfile.exists(), "Failed extraction must not publish outputs")
            return None
        return Path(self.envfile.read_text().strip().removeprefix("POLICY_DIR="))

    def test_workflow_scripts_match_and_parse(self):
        for name in ("Extract regular policy blobs", "Compare both policies on the PR head tree"):
            first, second = (run_block(p, name) for p in EXAMPLES)
            self.assertEqual(first, second)
            subprocess.run(["bash", "-n"], input=first.encode(), check=True)

    def test_regular_blobs_ignore_worktree_symlink(self):
        before = self.commit(b"old\n")
        after = self.commit(b"new\n")
        (self.repo / ".dockerignore").unlink()
        (self.repo / ".dockerignore").symlink_to("/dev/null")
        directory = self.extract(before, after)
        self.assertEqual((directory / "before.dockerignore").read_bytes(), b"old\n")
        self.assertEqual((directory / "after.dockerignore").read_bytes(), b"new\n")
        self.assertFalse(directory.is_relative_to(self.repo))

    def test_verified_missing_policy_is_empty(self):
        before = self.commit(None)
        after = self.commit(b"new\n")
        directory = self.extract(before, after)
        self.assertEqual((directory / "before.dockerignore").read_bytes(), b"")

    def test_deleted_policy_is_empty(self):
        before = self.commit(b"old\n")
        after = self.commit(None)
        directory = self.extract(before, after)
        self.assertEqual((directory / "after.dockerignore").read_bytes(), b"")

    def test_missing_commit_is_not_empty_policy(self):
        head = self.commit(None)
        self.extract("0" * 40, head, success=False)

    def test_malformed_revision_is_rejected(self):
        head = self.commit(None)
        self.extract("HEAD", head, success=False)

    def test_checkout_must_match_head(self):
        before = self.commit(b"old")
        self.commit(b"new")
        self.extract(before, before, success=False)

    def test_candidate_symlink_is_rejected(self):
        before = self.commit(b"old")
        after = self.commit("/etc/passwd", kind="symlink")
        self.extract(before, after, success=False)

    def test_base_symlink_is_rejected(self):
        before = self.commit("/etc/passwd", kind="symlink")
        after = self.commit(b"new")
        self.extract(before, after, success=False)

    def test_directory_is_rejected(self):
        before = self.commit(b"old")
        after = self.commit(None, kind="directory")
        self.extract(before, after, success=False)

    def test_dockerfile_specific_policy_is_not_silently_ignored(self):
        before = self.commit(b"old")
        after = self.commit(b"new", specific=True)
        self.extract(before, after, success=False)

    def test_oversized_policy_is_rejected(self):
        before = self.commit(b"old")
        after = self.commit(b"x" * (1048576 + 1))
        self.extract(before, after, success=False)

    def test_gate_status_and_untrusted_output_wrapping(self):
        # Test the shell boundary independently of CLI semantics, which Go tests cover.
        executables = self.root / "bin"
        executables.mkdir()
        tool = executables / "ignoreimpact"
        tool.write_text('#!/bin/bash\nprintf \'{"path":"##[warning]untrusted"}\\n\'\nexit "$TEST_STATUS"\n')
        tool.chmod(0o755)
        env = dict(os.environ, POLICY_DIR=str(self.runner), PATH=str(executables) + os.pathsep + os.environ["PATH"])
        for status in (0, 1, 2):
            with self.subTest(status=status):
                env["TEST_STATUS"] = str(status)
                result = subprocess.run(["bash", "-c", run_block(EXAMPLES[0], "Compare both policies on the PR head tree")],
                                        cwd=self.repo, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, status)
                lines = result.stdout.splitlines()
                self.assertRegex(lines[0], r"^::stop-commands::[0-9a-f]{64}$")
                token = lines[0].split("::")[-1]
                self.assertEqual(lines[-1], "::" + token + "::")
                self.assertEqual("##[warning]untrusted" in result.stdout, status < 2)


if __name__ == "__main__":
    unittest.main()
