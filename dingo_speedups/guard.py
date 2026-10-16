"""Make sure a script runs the DINGO we shipped, and record what it ran on.

Every script for this work puts this folder on sys.path (it holds no DINGO) and
calls use_dingo() before anything imports DINGO:

    import guard
    provenance = guard.use_dingo(tree, expected_commit)
    import dingo.gw.likelihood  # now certainly from `tree`

It refuses to run (GuardError) unless all of these hold:

1. DINGO is not imported yet, so nothing can have loaded another copy first.
2. Neither DINGO (dingo-gw) nor DINGO-Lensing is installed or importable in the
   environment. The dependencies-only image has neither, and DINGO-Lensing
   would bring back dingo-gw 0.9.8, which it pins.
3. The tree's COMMIT.json (written by pack_dingo.py) names the expected commit:
   A full hash, or a prefix of at least 7 characters.
4. With the tree first on sys.path, `dingo` imports from inside the tree, and
   its __version__ is the one COMMIT.json records.

It returns the provenance a result should carry: The commit and version, where
DINGO was imported from, the Python and package versions, the host and its CPU,
and the thread settings.

Run directly, it checks a tree and prints the provenance as JSON, optionally
importing more modules; or it runs DINGO's own tests from the tree (by default
all of tests/), in the same process, after the checks:

    python -I guard.py check --tree DIR --commit SHA [--import MODULE ...]
    python -I guard.py pytest --tree DIR --commit SHA [-- PYTEST ARGUMENTS]

Exit code 2 means the guard refused. Standard library only (DINGO aside).
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import platform
import socket
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    from importlib import metadata
except ImportError:  # pragma: no cover, Python < 3.8
    import importlib_metadata as metadata

MIN_PREFIX = 7
COMMIT_FILE = "COMMIT.json"
FORBIDDEN_DISTRIBUTIONS = ("dingo-gw", "dingo-lensing")
FORBIDDEN_MODULES = ("dingo_lensing",)
PACKAGES = ("lalsuite", "numpy", "scipy", "torch", "bilby", "bilby-pipe", "pandas", "h5py", "pycbc", "pytest")
THREAD_VARIABLES = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
CPU_FLAGS = ("avx2", "avx512f", "fma")


class GuardError(RuntimeError):
    """The environment or the tree is not the one we meant to run."""


def read_commit_file(tree: Path) -> Dict[str, str]:
    path = tree / COMMIT_FILE
    if not path.is_file():
        raise GuardError(f"{path} is missing: Pack the tree with pack_dingo.py")
    record = json.loads(path.read_text(encoding="utf-8"))
    for key in ("commit", "version"):
        if not isinstance(record.get(key), str) or not record[key]:
            raise GuardError(f"{path} has no {key!r}")
    return record


def check_commit(recorded: str, expected: str) -> None:
    expected = expected.strip().lower()
    if len(expected) < MIN_PREFIX or any(c not in "0123456789abcdef" for c in expected):
        raise GuardError(
            f"Expected commit {expected!r} must be a hexadecimal hash of at least {MIN_PREFIX} characters"
        )
    if not recorded.lower().startswith(expected):
        raise GuardError(f"The tree is commit {recorded}, not the expected {expected}")


def installed_forbidden() -> List[str]:
    found = []
    for name in FORBIDDEN_DISTRIBUTIONS:
        try:
            found.append(f"{name} {metadata.version(name)}")
        except metadata.PackageNotFoundError:
            continue
    return found


def is_inside(path: Path, folder: Path) -> bool:
    return folder == path or folder in path.parents


def use_dingo(tree, expected_commit: str) -> dict:
    """Put the shipped tree first on sys.path and import DINGO from it, or refuse."""
    tree = Path(tree).expanduser().resolve()
    already = sorted(name for name in sys.modules if name == "dingo" or name.startswith("dingo."))
    if already:
        raise GuardError(f"DINGO was imported before the guard ran ({', '.join(already[:3])})")
    if not (tree / "dingo" / "__init__.py").is_file():
        raise GuardError(f"{tree} has no dingo/__init__.py: Is it an unpacked pack_dingo.py tarball?")
    record = read_commit_file(tree)
    check_commit(record["commit"], expected_commit)

    forbidden = installed_forbidden()
    if forbidden:
        raise GuardError(
            f"Installed in this environment: {', '.join(forbidden)}. "
            "Run in the dependencies-only image, which has no DINGO"
        )
    for name in FORBIDDEN_MODULES:
        spec = importlib.util.find_spec(name)
        if spec is not None:
            raise GuardError(f"{name} is importable from {spec.origin}; it must not be")
    spec = importlib.util.find_spec("dingo")
    if spec is not None and not is_inside(Path(spec.origin).resolve(), tree):
        raise GuardError(f"Another DINGO is importable from {spec.origin}")

    sys.path.insert(0, str(tree))
    importlib.invalidate_caches()
    import dingo

    origin = Path(dingo.__file__).resolve()
    if not is_inside(origin, tree):
        raise GuardError(f"dingo was imported from {origin}, outside {tree}")
    version = getattr(dingo, "__version__", None)
    if version != record["version"]:
        raise GuardError(
            f"dingo.__version__ is {version!r} but {COMMIT_FILE} records {record['version']!r}: "
            "Is dingo/_version.py from pack_dingo.py?"
        )
    return provenance(tree, record, origin)


def package_versions() -> Dict[str, Optional[str]]:
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def cpu_description() -> dict:
    model, flags = None, set()
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                key, _, value = line.partition(":")
                key = key.strip()
                if key == "model name" and model is None:
                    model = value.strip()
                elif key == "flags" and not flags:
                    flags = set(value.split())
    except OSError:
        model = platform.processor() or None
    return {"model": model, "flags": {flag: flag in flags for flag in CPU_FLAGS}}


def usable_cpus() -> Optional[int]:
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return None


def provenance(tree: Path, record: Dict[str, str], origin: Path) -> dict:
    return {
        "dingo": {
            "commit": record["commit"],
            "describe": record.get("describe"),
            "version": record["version"],
            "tree": str(tree),
            "imported_from": str(origin.parent),
        },
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
            "isolated": bool(sys.flags.isolated),
        },
        "packages": package_versions(),
        "host": {
            "name": socket.gethostname(),
            "platform": platform.platform(),
            "cpu": cpu_description(),
            "cpu_count": os.cpu_count(),
            "usable_cpus": usable_cpus(),
        },
        "threads": {name: os.environ.get(name) for name in THREAD_VARIABLES},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Check a tree and print the provenance")
    run_tests = commands.add_parser("pytest", help="Check a tree, then run its tests")
    for command in (check, run_tests):
        command.add_argument("--tree", required=True, help="An unpacked pack_dingo.py tarball")
        command.add_argument("--commit", required=True, help="The commit the tree must be")
    check.add_argument(
        "--import", dest="modules", action="append", default=[], metavar="MODULE",
        help="Also import this module once the tree checks out (repeatable)",
    )
    run_tests.add_argument("pytest_args", nargs="*", help="Arguments for pytest, after --")
    args = parser.parse_args(argv)

    try:
        record = use_dingo(args.tree, args.commit)
    except GuardError as error:
        print(f"GUARD FAILED: {error}", file=sys.stderr)
        return 2
    tree = Path(record["dingo"]["tree"])

    if args.command == "check":
        for module in args.modules:
            imported = importlib.import_module(module)
            location = getattr(imported, "__file__", None)
            if module.split(".")[0] == "dingo" and not is_inside(Path(location).resolve(), tree):
                print(f"GUARD FAILED: {module} was imported from {location}", file=sys.stderr)
                return 2
        record["imported"] = args.modules
        print(json.dumps(record, indent=2))
        return 0

    import pytest

    print(json.dumps(record, indent=2), flush=True)
    # From the tree, so DINGO's pyproject.toml settings apply and relative test paths
    # (e.g. tests/gw) work. Without a test path among the arguments, all of tests/:
    # Otherwise pytest would collect from the tree's root, examples and docs included.
    # (Give option values as --option=value, so they cannot pass for paths.)
    os.chdir(tree)
    pytest_args = list(args.pytest_args)
    if not any(not arg.startswith("-") and Path(arg.split("::")[0]).exists() for arg in pytest_args):
        pytest_args.append("tests")
    return int(pytest.main(["--rootdir", ".", "-c", "pyproject.toml", *pytest_args]))


if __name__ == "__main__":
    sys.exit(main())
