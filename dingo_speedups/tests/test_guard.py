"""Unit tests for guard.py: It must refuse every way of running the wrong DINGO.

Each case runs the guard in a fresh `python -I -S` process (see helpers.py), so
the results do not depend on the machine's installed packages. Standard library
only.
"""
from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import (  # noqa: E402
    COMMIT,
    DINGO_INIT,
    GUARD_PATH,
    VERSION,
    environment_is_clean,
    fake_distribution,
    guard_case,
    make_tree,
    run_script,
    write
)


class GuardTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)

    def assertRefuses(self, outcome: dict, fragment: str):
        self.assertIn("error", outcome, f"the guard accepted: {outcome}")
        self.assertIn(fragment, outcome["error"])


class TestAccepts(GuardTestCase):
    def test_a_packed_tree_with_the_right_commit(self):
        tree = make_tree(self.base)
        outcome = guard_case(tree, COMMIT)
        self.assertNotIn("error", outcome)
        provenance = outcome["provenance"]
        self.assertEqual(provenance["dingo"]["commit"], COMMIT)
        self.assertEqual(provenance["dingo"]["version"], VERSION)
        self.assertEqual(Path(outcome["dingo_file"]).resolve(), (tree / "dingo" / "__init__.py").resolve())
        self.assertEqual(Path(provenance["dingo"]["imported_from"]), (tree / "dingo").resolve())

    def test_a_commit_prefix_of_seven_characters_any_case(self):
        tree = make_tree(self.base)
        for expected in (COMMIT[:7], COMMIT[:12].upper(), f"  {COMMIT}\n"):
            with self.subTest(expected=expected):
                self.assertNotIn("error", guard_case(tree, expected))

    def test_provenance_records_python_packages_host_and_threads(self):
        provenance = guard_case(make_tree(self.base), COMMIT)["provenance"]
        self.assertTrue(provenance["python"]["isolated"])
        self.assertEqual(
            set(provenance["packages"]),
            {"lalsuite", "numpy", "scipy", "torch", "bilby", "bilby-pipe", "pandas", "h5py", "pycbc", "pytest"}
        )
        self.assertEqual(set(provenance["host"]), {"name", "platform", "cpu", "cpu_count", "usable_cpus"})
        self.assertEqual(set(provenance["host"]["cpu"]["flags"]), {"avx2", "avx512f", "fma"})
        self.assertEqual(
            set(provenance["threads"]),
            {"OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"}
        )

    def test_records_installed_package_versions(self):
        env = fake_distribution(self.base / "env", "numpy", "2.3.5")
        provenance = guard_case(make_tree(self.base), COMMIT, prepend=[env])["provenance"]
        self.assertEqual(provenance["packages"]["numpy"], "2.3.5")
        self.assertIsNone(provenance["packages"]["torch"])


class TestRefusesTheWrongTree(GuardTestCase):
    def test_another_commit(self):
        tree = make_tree(self.base)
        self.assertRefuses(guard_case(tree, "fedcba9876543210"), "not the expected")

    def test_an_expected_commit_that_is_too_short_or_not_a_hash(self):
        tree = make_tree(self.base)
        for expected in (COMMIT[:6], "", "main", "0123456z"):
            with self.subTest(expected=expected):
                self.assertRefuses(guard_case(tree, expected), "at least 7 characters")

    def test_a_tree_without_commit_file(self):
        tree = make_tree(self.base, with_commit_file=False)
        self.assertRefuses(guard_case(tree, COMMIT), "COMMIT.json is missing")

    def test_a_commit_file_without_a_version(self):
        tree = make_tree(self.base)
        write(tree / "COMMIT.json", json.dumps({"commit": COMMIT}))
        self.assertRefuses(guard_case(tree, COMMIT), "has no 'version'")

    def test_a_tree_without_dingo(self):
        tree = make_tree(self.base, with_dingo=False)
        self.assertRefuses(guard_case(tree, COMMIT), "has no dingo/__init__.py")

    def test_a_version_that_differs_from_the_commit_file(self):
        tree = make_tree(self.base, record_version="0.10.3")
        self.assertRefuses(guard_case(tree, COMMIT), "dingo.__version__ is")

    def test_a_tree_without_version_file(self):
        tree = make_tree(self.base, with_version_file=False)
        self.assertRefuses(guard_case(tree, COMMIT), "dingo.__version__ is None")


class TestRefusesTheWrongEnvironment(GuardTestCase):
    def fake_package(self, name: str) -> Path:
        env = self.base / f"env_{name}"
        write(env / name / "__init__.py", "")
        return env

    def test_dingo_imported_before_the_guard(self):
        env = self.fake_package("dingo")
        outcome = guard_case(make_tree(self.base), COMMIT, prepend=[env], before="import dingo")
        self.assertRefuses(outcome, "imported before the guard")

    def test_a_submodule_of_dingo_imported_before_the_guard(self):
        env = self.fake_package("dingo")
        write(env / "dingo" / "core.py", "")
        outcome = guard_case(make_tree(self.base), COMMIT, prepend=[env], before="import dingo.core")
        self.assertRefuses(outcome, "imported before the guard")

    def test_another_dingo_importable(self):
        env = self.fake_package("dingo")
        self.assertRefuses(guard_case(make_tree(self.base), COMMIT, prepend=[env]), "Another DINGO")

    def test_dingo_lensing_importable(self):
        env = self.fake_package("dingo_lensing")
        case = guard_case(make_tree(self.base), COMMIT, prepend=[env])
        self.assertRefuses(case, "dingo_lensing is importable")

    def test_dingo_gw_installed(self):
        env = fake_distribution(self.base / "env", "dingo-gw", "0.9.8")
        case = guard_case(make_tree(self.base), COMMIT, prepend=[env])
        self.assertRefuses(case, "dingo-gw 0.9.8")

    def test_dingo_lensing_installed(self):
        env = fake_distribution(self.base / "env", "dingo-lensing", "0.0.1")
        case = guard_case(make_tree(self.base), COMMIT, prepend=[env])
        self.assertRefuses(case, "dingo-lensing 0.0.1")

    def test_dingo_loaded_from_outside_the_tree(self):
        # A tree whose dingo/__init__.py swaps in another copy: The import must
        # be checked where it actually came from, not only where it was looked for.
        other = self.base / "other"
        write(other / "dingo" / "__init__.py", "__version__ = " + repr(VERSION) + "\n")
        swap = textwrap.dedent(
            f"""
            import importlib.util, sys
            spec = importlib.util.spec_from_file_location("dingo", {str(other / "dingo" / "__init__.py")!r})
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sys.modules["dingo"] = module
            """
        )
        tree = make_tree(self.base, init=swap)
        self.assertRefuses(guard_case(tree, COMMIT), "outside")


def run_guard(*args: str, site: bool = False):
    """guard.py's command line in a fresh isolated process."""
    return run_script(GUARD_PATH, args, site=site)


class TestCommandLine(GuardTestCase):
    def test_check_prints_the_provenance_and_exits_0(self):
        tree = make_tree(self.base)
        result = run_guard("check", "--tree", str(tree), "--commit", COMMIT[:10])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["dingo"]["commit"], COMMIT)

    def test_check_imports_extra_modules_from_the_tree(self):
        tree = make_tree(self.base)
        result = run_guard("check", "--tree", str(tree), "--commit", COMMIT, "--import", "dingo.sub")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["imported"], ["dingo.sub"])

    def test_refusal_exits_2_with_the_reason(self):
        tree = make_tree(self.base)
        result = run_guard("check", "--tree", str(tree), "--commit", "fedcba9876543210")
        self.assertEqual(result.returncode, 2)
        self.assertIn("GUARD FAILED", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_an_extra_dingo_module_from_outside_the_tree_is_refused(self):
        # A dingo package whose __path__ reaches outside the tree.
        elsewhere = self.base / "elsewhere"
        write(elsewhere / "stray.py", "")
        init = f"__path__.append({str(elsewhere)!r})\n" + DINGO_INIT
        tree = make_tree(self.base, init=init)
        result = run_guard("check", "--tree", str(tree), "--commit", COMMIT, "--import", "dingo.stray")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("dingo.stray was imported from", result.stderr)

    def test_an_extra_module_that_fails_to_import_is_an_error(self):
        tree = make_tree(self.base)
        result = run_guard("check", "--tree", str(tree), "--commit", COMMIT, "--import", "dingo.missing")
        self.assertNotEqual(result.returncode, 0)


@unittest.skipUnless(environment_is_clean(), "needs pytest and no DINGO installed (runs inside the image)")
class TestPytestMode(GuardTestCase):
    def tree_with_tests(self, body: str) -> Path:
        tree = make_tree(self.base)
        write(tree / "pyproject.toml", "[tool.pytest.ini_options]\naddopts = \"-p no:cacheprovider\"\n")
        write(tree / "tests" / "test_fake.py", body)
        return tree

    def test_runs_the_trees_tests_with_its_dingo(self):
        tree = self.tree_with_tests(
            "import dingo, dingo.sub\n"
            "def test_imports_the_tree():\n"
            f"    assert dingo.__version__ == {VERSION!r}\n"
        )
        result = run_guard("pytest", "--tree", str(tree), "--commit", COMMIT, site=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 passed", result.stdout)

    def test_options_without_a_test_path_still_run_only_tests(self):
        tree = self.tree_with_tests("def test_ok():\n    pass\n")
        write(tree / "examples" / "test_not_a_test.py", "def test_example():\n    assert False\n")
        result = run_guard("pytest", "--tree", str(tree), "--commit", COMMIT, "--", "-q", site=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 passed", result.stdout)

    def test_a_given_test_path_is_used_instead(self):
        tree = self.tree_with_tests("def test_ok():\n    pass\n")
        two_tests = "def test_example():\n    pass\ndef test_two():\n    pass\n"
        write(tree / "examples" / "test_example.py", two_tests)
        options = ["--tree", str(tree), "--commit", COMMIT, "--", "-q", "examples"]
        result = run_guard("pytest", *options, site=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("2 passed", result.stdout)

    def test_a_failing_test_fails_the_run(self):
        tree = self.tree_with_tests("def test_fails():\n    assert False\n")
        result = run_guard("pytest", "--tree", str(tree), "--commit", COMMIT, site=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
