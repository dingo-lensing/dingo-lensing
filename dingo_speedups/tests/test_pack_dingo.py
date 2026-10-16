"""Unit tests for pack_dingo.py, on small git repositories shaped like DINGO.

Needs git (skipped without it); otherwise standard library only.
"""
from __future__ import annotations

import io
import json
import sys
import tarfile
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import (  # noqa: E402
    PACK_PATH,
    extract,
    git,
    guard_case,
    have_git,
    load_module,
    make_repo,
    run_python,
    write,
)

pack_dingo = load_module("pack_dingo_under_test", PACK_PATH)
PackError = pack_dingo.PackError


class TestVersionFromDescribe(unittest.TestCase):
    def test_a_tagged_commit_has_the_tags_version(self):
        self.assertEqual(pack_dingo.version_from_describe("v0.10.3-0-gdd481d98"), ("0.10.3", (0, 10, 3)))

    def test_later_commits_are_development_releases_of_the_next_patch(self):
        self.assertEqual(
            pack_dingo.version_from_describe("v0.10.3-1-gdd481d98"),
            ("0.10.4.dev1+gdd481d98", (0, 10, 4, "dev1", "gdd481d98")),
        )
        self.assertEqual(
            pack_dingo.version_from_describe("v1.2-17-gabcdef0123"),
            ("1.3.dev17+gabcdef0123", (1, 3, "dev17", "gabcdef0123")),
        )

    def test_anything_else_is_an_error(self):
        for describe in ("0.10.3-1-gdd481d98", "v0.10.3rc1-1-gdd481d98", "v0.10.3", "v0.10.3-1-dd481d98", ""):
            with self.subTest(describe=describe):
                with self.assertRaisesRegex(PackError, "Cannot read a version"):
                    pack_dingo.version_from_describe(describe)


@unittest.skipUnless(have_git(), "needs git")
class PackTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)

    def head(self, repo: Path) -> str:
        return git(repo, "rev-parse", "HEAD")


class TestPack(PackTestCase):
    def setUp(self):
        super().setUp()
        self.repo = make_repo(self.base)
        self.commit = self.head(self.repo)
        self.short = git(self.repo, "rev-parse", "--short", "HEAD")
        self.packed = pack_dingo.pack(self.repo, "HEAD", self.base / "out")
        self.name = f"dingo_{self.commit[:10]}"

    def test_names_the_tarball_after_the_commit(self):
        self.assertEqual(Path(self.packed.path), (self.base / "out" / f"{self.name}.tar.gz").resolve())
        self.assertEqual(self.packed.commit, self.commit)
        self.assertFalse(self.packed.reused)

    def test_holds_the_commits_files_and_the_two_extra_files_under_one_folder(self):
        with tarfile.open(self.packed.path) as archive:
            names = set(archive.getnames())  # folders are listed without a trailing slash
        outside = [name for name in names if name != self.name and not name.startswith(f"{self.name}/")]
        self.assertEqual(outside, [])
        for relative in ("dingo/__init__.py", "dingo/sub.py", "dingo/more.py", "pyproject.toml",
                         "tests/test_nothing.py", "COMMIT.json", "dingo/_version.py"):
            self.assertIn(f"{self.name}/{relative}", names)

    def test_commit_file_records_commit_describe_and_version(self):
        extract(Path(self.packed.path), self.base / "x")
        record = json.loads((self.base / "x" / self.name / "COMMIT.json").read_text())
        self.assertEqual(record["commit"], self.commit)
        self.assertEqual(record["describe"], f"v0.10.3-1-g{self.short}")
        self.assertEqual(record["version"], f"0.10.4.dev1+g{self.short}")
        self.assertEqual(self.packed.version, record["version"])

    def test_unpacked_dingo_imports_with_that_version(self):
        extract(Path(self.packed.path), self.base / "x")
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); import dingo; "
            "print(repr((dingo.__version__, dingo.__version_tuple__)))"
        )
        result = run_python(code, [str(self.base / "x" / self.name)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(), repr((f"0.10.4.dev1+g{self.short}", (0, 10, 4, "dev1", f"g{self.short}")))
        )

    def test_the_guard_accepts_the_unpacked_tree(self):
        extract(Path(self.packed.path), self.base / "x")
        outcome = guard_case(self.base / "x" / self.name, self.commit[:7])
        self.assertNotIn("error", outcome)
        self.assertEqual(outcome["provenance"]["dingo"]["version"], self.packed.version)

    def test_writes_a_sha256_file_next_to_the_tarball(self):
        line = Path(f"{self.packed.path}.sha256").read_text()
        self.assertEqual(line, f"{self.packed.sha256}  {self.name}.tar.gz\n")

    def test_the_same_commit_gives_the_same_bytes_later(self):
        time.sleep(1.1)  # so a time stamp anywhere in the output would differ
        again = pack_dingo.pack(self.repo, self.commit, self.base / "again")
        self.assertEqual(again.sha256, self.packed.sha256)
        self.assertEqual(Path(again.path).read_bytes(), Path(self.packed.path).read_bytes())

    def test_packing_again_into_the_same_folder_reuses_the_tarball(self):
        again = pack_dingo.pack(self.repo, "HEAD", self.base / "out")
        self.assertTrue(again.reused)
        self.assertEqual(again.sha256, self.packed.sha256)

    def test_refuses_to_replace_a_different_file_of_the_same_name(self):
        Path(self.packed.path).write_bytes(b"not the tarball")
        with self.assertRaisesRegex(PackError, "differs from a fresh pack"):
            pack_dingo.pack(self.repo, "HEAD", self.base / "out")

    def test_ignores_tags_that_are_not_releases(self):
        git(self.repo, "tag", "nightly")
        again = pack_dingo.pack(self.repo, "HEAD", self.base / "nightly")
        self.assertEqual(again.version, self.packed.version)

    def test_a_tagged_commit_gets_the_tags_version(self):
        tagged = pack_dingo.pack(self.repo, "v0.10.3", self.base / "tagged")
        self.assertEqual(tagged.version, "0.10.3")
        self.assertEqual(tagged.describe, f"v0.10.3-0-g{git(self.repo, 'rev-parse', '--short', 'v0.10.3')}")


class TestRefusals(PackTestCase):
    def test_uncommitted_changes_when_packing_the_checked_out_commit(self):
        repo = make_repo(self.base)
        write(repo / "dingo" / "sub.py", "VALUE = 2\n")
        with self.assertRaisesRegex(PackError, "uncommitted changes"):
            pack_dingo.pack(repo, "HEAD", self.base / "out")

    def test_uncommitted_changes_do_not_matter_for_another_commit(self):
        repo = make_repo(self.base)
        write(repo / "dingo" / "sub.py", "VALUE = 2\n")
        self.assertEqual(pack_dingo.pack(repo, "v0.10.3", self.base / "out").version, "0.10.3")

    def test_a_repository_without_release_tags(self):
        repo = make_repo(self.base, tag=False)
        with self.assertRaisesRegex(PackError, "fetch upstream --tags"):
            pack_dingo.pack(repo, "HEAD", self.base / "out")

    def test_an_unknown_commit(self):
        repo = make_repo(self.base)
        with self.assertRaisesRegex(PackError, "rev-parse"):
            pack_dingo.pack(repo, "no-such-branch", self.base / "out")

    def test_a_repository_that_is_not_dingo(self):
        repo = make_repo(self.base, dingo=False)
        with self.assertRaisesRegex(PackError, "no dingo/__init__.py"):
            pack_dingo.pack(repo, "HEAD", self.base / "out")

    def test_a_commit_that_tracks_the_version_file(self):
        repo = make_repo(self.base)
        write(repo / "dingo" / "_version.py", "__version__ = '9'\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "Track the version file")
        with self.assertRaisesRegex(PackError, "already tracks dingo/_version.py"):
            pack_dingo.pack(repo, "HEAD", self.base / "out")


@unittest.skipUnless(have_git(), "needs git")
class TestCommandLine(PackTestCase):
    def run_main(self, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = pack_dingo.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_prints_the_result_as_json(self):
        repo = make_repo(self.base)
        code, out, _ = self.run_main("--repo", str(repo), "--output-dir", str(self.base / "out"))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["commit"], self.head(repo))

    def test_an_error_exits_1_with_the_reason(self):
        repo = make_repo(self.base, tag=False)
        code, out, err = self.run_main("--repo", str(repo), "--output-dir", str(self.base / "out"))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("ERROR:", err)


if __name__ == "__main__":
    unittest.main()
