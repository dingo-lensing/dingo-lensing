"""Mutation check for guard.py and pack_dingo.py: Every mutation must make a test fail.

Each mutation is one small edit that disables or weakens one check. The script
copies the module, applies the edit, and runs that module's tests against the
copy (helpers.py loads it from DINGO_SPEEDUPS_GUARD or DINGO_SPEEDUPS_PACK). A
mutation that all tests survive is a check no test covers. The unmutated modules
must pass first.

    python tests/mutation_check.py [--module guard.py] [--module pack_dingo.py]

Standard library only. Not collected as a test (no test_ prefix).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import environment_is_clean  # noqa: E402

SPEEDUPS = Path(__file__).resolve().parent.parent
TESTS = {"guard.py": ("DINGO_SPEEDUPS_GUARD", "test_guard.py"), "pack_dingo.py": ("DINGO_SPEEDUPS_PACK", "test_pack_dingo.py")}

# (file, text to replace, replacement, what it breaks[, what catching it needs])
MUTATIONS = [
    ("guard.py", "    if already:\n", "    if False:\n", "DINGO imported before the guard"),
    ("guard.py", "    if not recorded.lower().startswith(expected):\n", "    if False:\n", "commit comparison"),
    ("guard.py", "MIN_PREFIX = 7", "MIN_PREFIX = 1", "minimum prefix length"),
    ("guard.py", ' or any(c not in "0123456789abcdef" for c in expected)', "", "hexadecimal commit"),
    ("guard.py", '    for key in ("commit", "version"):\n', "    for key in ():\n", "commit file contents"),
    ("guard.py", "    if not path.is_file():\n", "    if False:\n", "missing commit file"),
    ("guard.py", "    if not (tree / \"dingo\" / \"__init__.py\").is_file():\n", "    if False:\n", "tree without dingo"),
    ("guard.py", "    if forbidden:\n", "    if False:\n", "installed DINGO or DINGO-Lensing"),
    ("guard.py", 'FORBIDDEN_DISTRIBUTIONS = ("dingo-gw", "dingo-lensing")', 'FORBIDDEN_DISTRIBUTIONS = ("dingo-lensing",)', "installed dingo-gw"),
    ("guard.py", 'FORBIDDEN_DISTRIBUTIONS = ("dingo-gw", "dingo-lensing")', 'FORBIDDEN_DISTRIBUTIONS = ("dingo-gw",)', "installed dingo-lensing"),
    ("guard.py", 'FORBIDDEN_MODULES = ("dingo_lensing",)', "FORBIDDEN_MODULES = ()", "importable DINGO-Lensing"),
    ("guard.py", "    if spec is not None and not is_inside(Path(spec.origin).resolve(), tree):\n", "    if False:\n", "another importable DINGO"),
    ("guard.py", "    if not is_inside(origin, tree):\n", "    if False:\n", "where DINGO was imported from"),
    ("guard.py", '    if version != record["version"]:\n', "    if False:\n", "version check"),
    ("guard.py", "        return 2\n    tree = Path", "        return 0\n    tree = Path", "exit code when refusing"),
    ("guard.py", 'if module.split(".")[0] == "dingo" and not is_inside(Path(location).resolve(), tree):', "if False:", "extra imports from the tree"),
    ("guard.py", "    os.chdir(tree)\n", "", "pytest from the tree", "pytest"),
    ("guard.py", '        pytest_args.append("tests")\n', "        pass\n", "pytest defaults to tests/", "pytest"),
    ("pack_dingo.py", "    release[-1] += 1\n", "", "next patch release"),
    ("pack_dingo.py", "    if distance == 0:\n", "    if False:\n", "tagged commit version"),
    ("pack_dingo.py", 'if commit == git(repo, "rev-parse", "HEAD") and git(', "if False and git(", "uncommitted changes"),
    ("pack_dingo.py", '"--match", "v[0-9]*", ', "", "release tags only"),
    ("pack_dingo.py", "mtime=0\n", "mtime=None\n", "reproducible gzip header"),
    ("pack_dingo.py", '            add_file(archive, f"{name}/{VERSION_FILE}", version_file_text(version, version_tuple), mtime)\n', "", "version file"),
    ("pack_dingo.py", '            add_file(archive, f"{name}/{COMMIT_FILE}", json.dumps(record, indent=2) + "\\n", mtime)\n', "", "commit file"),
    ("pack_dingo.py", "            if sha256_of(target) != digest:\n", "            if False:\n", "replacing a different file"),
    ("pack_dingo.py", '        if f"{name}/dingo/__init__.py" not in members:\n', "        if False:\n", "not a DINGO tree"),
    ("pack_dingo.py", '            if f"{name}/{extra}" in members:\n', "            if False:\n", "tracked version file"),
    ("pack_dingo.py", 'f"--prefix={name}/"', 'f"--prefix=dingo/"', "folder name"),
    ("pack_dingo.py", "        return 1\n    print(json.dumps(asdict(packed)", "        return 0\n    print(json.dumps(asdict(packed)", "exit code on error"),
]


def run_tests(module: str, path: Path) -> subprocess.CompletedProcess:
    variable, pattern = TESTS[module]
    env = {**os.environ, variable: str(path)}
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern],
        cwd=SPEEDUPS, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--module", choices=sorted(TESTS), action="append",
        help="Only this module's mutations (repeatable; default both). Inside the image, which has "
        "no git, use --module guard.py",
    )
    modules = parser.parse_args(argv).module or list(TESTS)
    mutations = [mutation for mutation in MUTATIONS if mutation[0] in modules]
    for module in modules:
        baseline = run_tests(module, SPEEDUPS / module)
        if baseline.returncode != 0:
            print(baseline.stdout)
            print(f"The unmutated {module} fails its tests: Fix that first")
            return 1
    survived, unchecked = [], []
    with tempfile.TemporaryDirectory() as scratch:
        for number, (module, old, new, what, *needs) in enumerate(mutations, start=1):
            source = (SPEEDUPS / module).read_text(encoding="utf-8")
            if source.count(old) != 1:
                print(f"{number:2d} {module}: {what}: The text to replace occurs {source.count(old)} times; update the mutation")
                return 1
            if needs and not environment_is_clean():
                print(f"{number:2d} {module:13s} not here {what} (its tests need pytest and no DINGO: Run inside the image)")
                unchecked.append(what)
                continue
            mutated = Path(scratch) / f"{number}_{module}"
            mutated.write_text(source.replace(old, new), encoding="utf-8")
            caught = run_tests(module, mutated).returncode != 0
            print(f"{number:2d} {module:13s} {'caught  ' if caught else 'SURVIVED'} {what}")
            if not caught:
                survived.append(what)
    checked = len(mutations) - len(unchecked)
    note = f"; {len(unchecked)} can only be checked inside the image" if unchecked else ""
    print(f"\n{checked - len(survived)} of {checked} mutations caught{note}")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
