import io
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

from build_release import archive_bytes, validate_version
from smoke_release import extract, safe_name
from verify_release import verify


class ReleaseTests(unittest.TestCase):
    def test_version_validation(self):
        for value in ("0.1.0", "0.1.0-rc.1"):
            self.assertEqual(validate_version(value), value)
        for value in ("v0.1.0", "../bad", "1.0.0;echo bad", "", "1.0", "01.0.0", "1.0.0-01"):
            with self.assertRaises(ValueError):
                validate_version(value)

    def test_deterministic_archives_and_permissions(self):
        files = {"z.txt": (b"z", 0o644), "ignoreimpact": (b"binary", 0o755)}
        for windows in (False, True):
            first = archive_bytes(files, 1791310000, windows)
            second = archive_bytes(dict(reversed(list(files.items()))), 1791310000, windows)
            self.assertEqual(first, second)
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                archive = root / ("test.zip" if windows else "test.tar.gz")
                archive.write_bytes(first)
                target = root / "out"
                target.mkdir()
                extract(archive, target)
                self.assertEqual((target / "ignoreimpact").read_bytes(), b"binary")
            if not windows:
                with tarfile.open(fileobj=io.BytesIO(first), mode="r:gz") as source:
                    self.assertEqual(source.getmember("ignoreimpact").mode, 0o755)

    def test_unsafe_members(self):
        for name in ("../escape", "/absolute", "C:/drive", "a\\b", ""):
            with self.assertRaises(ValueError):
                safe_name(name)

    def test_manifest_verification_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = b"candidate"
            sha = hashlib.sha256(data).hexdigest()
            (root / "candidate.zip").write_bytes(data)
            manifest = {"source": {"commit": "a" * 40, "dirty": False}, "version": "0.1.0-rc.1",
                        "assets": [{"name": "candidate.zip", "sha256": sha, "bytes": len(data)}]}
            (root / "release-manifest.json").write_text(json.dumps(manifest))
            manifest_sha = hashlib.sha256((root / "release-manifest.json").read_bytes()).hexdigest()
            (root / "provenance.json").write_text(json.dumps({"source_commit": "a" * 40, "signed": False,
                                                              "release_manifest_sha256": manifest_sha}))
            (root / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(root.iterdir())))
            self.assertEqual(verify(root, "a" * 40)["checksums"], "passed")
            (root / "candidate.zip").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                verify(root, "a" * 40)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as target:
                info = tarfile.TarInfo("link")
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                target.addfile(info)
            with self.assertRaises(ValueError):
                extract(archive, root / "out")


if __name__ == "__main__":
    unittest.main()
