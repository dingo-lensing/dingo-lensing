"""Shared helpers for the dingo_speedups tests. Standard library only.

The modules under test are loaded by path, and the paths can be overridden with
DINGO_SPEEDUPS_GUARD and DINGO_SPEEDUPS_PACK, so mutation_check.py can run these
tests against mutated copies.

Code that exercises the guard runs in a fresh `python -I -S` process: Isolated,
and without site-packages. So the result does not depend on what the machine
running the tests has installed (dingo_env, for instance, has DINGO 0.9.8), and
each case starts with no DINGO imported. A case adds the fake packages and
distributions it needs to sys.path itself.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import textwrap
from pathlib import Path
from typing import Iterable, Optional

SPEEDUPS = Path(__file__).resolve().parent.parent
GUARD_PATH = Path(os.environ.get("DINGO_SPEEDUPS_GUARD", SPEEDUPS / "guard.py"))
PACK_PATH = Path(os.environ.get("DINGO_SPEEDUPS_PACK", SPEEDUPS / "pack_dingo.py"))

COMMIT = "0123456789abcdef0123456789abcdef01234567"
VERSION = "0.10.4.dev1+g0123456"

# What DINGO's own dingo/__init__.py does about its version.
DINGO_INIT = """\
try:
    from ._version import __version__, __version_tuple__
except ImportError:
    pass
"""


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses needs the module registered
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_tree(
    base: Path,
    commit: str = COMMIT,
    version: str = VERSION,
    record_version: Optional[str] = None,
    with_version_file: bool = True,
    with_commit_file: bool = True,
    with_dingo: bool = True,
    init: str = DINGO_INIT,
) -> Path:
    """A folder shaped like an unpacked pack_dingo.py tarball, with a fake DINGO."""
    tree = base / f"dingo_{commit[:10]}"
    tree.mkdir(parents=True)
    if with_dingo:
        write(tree / "dingo" / "__init__.py", init)
        write(tree / "dingo" / "sub.py", "VALUE = 1\n")
        if with_version_file:
            write(
                tree / "dingo" / "_version.py",
                f"__version__ = version = {version!r}\n__version_tuple__ = version_tuple = (0, 10, 4)\n",
            )
    if with_commit_file:
        record = {"commit": commit, "describe": "v0.10.3-1-g0123456", "version": record_version or version}
        write(tree / "COMMIT.json", json.dumps(record))
    return tree


def fake_distribution(folder: Path, name: str, version: str) -> Path:
    """An installed-looking distribution that importlib.metadata finds on sys.path."""
    folder.mkdir(parents=True, exist_ok=True)
    info = folder / f"{name.replace('-', '_')}-{version}.dist-info"
    write(info / "METADATA", f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
    return folder


def run_python(code: str, args: Iterable[str] = (), site: bool = False, cwd=None):
    """Run code in a fresh isolated interpreter; without site-packages unless site=True."""
    flags = ["-I"] if site else ["-I", "-S"]
    return subprocess.run(
        [sys.executable, *flags, "-c", code, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        cwd=cwd,
    )


def run_script(path: Path, args: Iterable[str] = (), site: bool = False, cwd=None):
    """Run a script file in a fresh isolated interpreter; without site-packages unless site=True."""
    flags = ["-I"] if site else ["-I", "-S"]
    return subprocess.run(
        [sys.executable, *flags, str(path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        cwd=cwd,
    )


def guard_case(tree: Path, commit: str, prepend: Iterable[Path] = (), before: str = "") -> dict:
    """use_dingo() in a fresh process: Either {"error": message} or the provenance."""
    code = textwrap.dedent(
        f"""
        import importlib.util, json, sys
        sys.path[:0] = {[str(p) for p in prepend]!r}
        {before}
        spec = importlib.util.spec_from_file_location("guard", {str(GUARD_PATH)!r})
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        try:
            result = guard.use_dingo({str(tree)!r}, {commit!r})
        except guard.GuardError as error:
            print(json.dumps({{"error": str(error)}}))
            sys.exit(0)
        import dingo
        print(json.dumps({{"provenance": result, "dingo_file": dingo.__file__}}))
        """
    )
    result = run_python(code)
    if result.returncode != 0:
        raise AssertionError(f"guard case crashed:\n{result.stderr}")
    return json.loads(result.stdout)


def have_git() -> bool:
    return shutil.which("git") is not None


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def make_repo(base: Path, tag: bool = True, extra_commit: bool = True, dingo: bool = True) -> Path:
    """A small git repository shaped like DINGO: Tagged v0.10.3, optionally one commit later."""
    repo = base / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "core.autocrlf", "false")
    if dingo:
        write(repo / "dingo" / "__init__.py", DINGO_INIT)
        write(repo / "dingo" / "sub.py", "VALUE = 1\n")
    write(repo / "pyproject.toml", "[project]\nname = 'dingo-gw'\n")
    write(repo / "tests" / "test_nothing.py", "def test_nothing():\n    pass\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "First")
    if tag:
        git(repo, "tag", "v0.10.3")
    if extra_commit:
        write(repo / "dingo" / "more.py", "MORE = 2\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "Second")
    return repo


def extract(tarball: Path, destination: Path) -> None:
    with tarfile.open(tarball) as archive:
        if hasattr(tarfile, "data_filter"):
            archive.extractall(destination, filter="data")
        else:  # Python without extraction filters (before 3.9.17)
            archive.extractall(destination)


def environment_is_clean() -> bool:
    """Whether this interpreter has pytest and no DINGO, as inside the image."""
    if importlib.util.find_spec("pytest") is None:
        return False
    from importlib import metadata

    for name in ("dingo-gw", "dingo-lensing"):
        try:
            metadata.version(name)
            return False
        except metadata.PackageNotFoundError:
            pass
    return importlib.util.find_spec("dingo") is None and importlib.util.find_spec("dingo_lensing") is None
