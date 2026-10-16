#!/usr/bin/env python
"""Check a set of changes against the rules in CONTRIBUTING.md.

The checks are *diff-aware*: they only look at lines that were added or
modified relative to a base commit, so that contributors are held to the
guidelines for the code they write without being blocked by pre-existing
issues elsewhere in the repository.

Three checks are implemented:

``lint``
    Run ``ruff check`` (PEP 8, pyflakes, import grouping, NumPy docstring
    style; configured in ``pyproject.toml``) and report only the findings
    that touch changed lines.
``docstrings``
    Every function, method, or class whose ``def``/``class`` line was added
    or modified must have a docstring.  Unlike ``ruff``'s ``D1xx`` rules
    this also applies to private helpers (``_name``), as CONTRIBUTING.md
    requires.
``tests``
    Every changed module ``dingo_lensing/<path>/<module>.py`` must have a
    matching ``tests/test_<module>.py`` (flat or mirroring the package
    layout), and every ``.py`` file under ``tests/`` must follow the
    ``test_<module>.py`` naming convention.

Usage::

    python .github/scripts/check_contributing.py [all|lint|docstrings|tests] \
        --base origin/main

Findings are printed as GitHub Actions workflow commands (``::error ...``)
so that they appear as inline annotations on pull requests, and as plain
text when run locally.  The exit status is non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import pathlib
import re
import subprocess
import sys
from collections.abc import Iterable

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_DIR = "dingo_lensing"
TESTS_DIR = "tests"

# Files under these directories are exempt from the docstring requirement.
DOCSTRING_EXEMPT_DIRS = (TESTS_DIR,)

# Modules that never need a matching test file.
TEST_EXEMPT_MODULES = ("__init__.py", "__main__.py")

HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

IN_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------
class Reporter:
    """Collect findings and print them in the right format for the context."""

    def __init__(self) -> None:
        self.n_errors = 0

    def error(
        self, message: str, file: str | None = None, line: int | None = None
    ) -> None:
        """Record and print an error annotation."""
        self.n_errors += 1
        self._emit("error", message, file, line)

    def notice(
        self, message: str, file: str | None = None, line: int | None = None
    ) -> None:
        """Print an informational annotation (does not fail the check)."""
        self._emit("notice", message, file, line)

    @staticmethod
    def _emit(
        level: str, message: str, file: str | None, line: int | None
    ) -> None:
        if IN_GITHUB_ACTIONS:
            props = []
            if file:
                props.append(f"file={file}")
            if line:
                props.append(f"line={line}")
            prop_str = " " + ",".join(props) if props else ""
            print(f"::{level}{prop_str}::{message}")
        else:
            loc = ""
            if file:
                loc = f"{file}:{line}: " if line else f"{file}: "
            print(f"{level.upper()}: {loc}{message}")


# ---------------------------------------------------------------------------
# Git diff parsing
# ---------------------------------------------------------------------------
def git(*args: str) -> str:
    """Run a git command in the repository root and return its stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def changed_python_files(base: str) -> tuple[list[str], list[str]]:
    """Return (added-or-modified, deleted) Python files relative to ``base``.

    Paths are relative to the repository root.  Renames are reported under
    their new name.
    """
    out = git("diff", "--name-status", "--merge-base", base, "HEAD")
    changed, deleted = [], []
    for raw in out.splitlines():
        parts = raw.split("\t")
        status, path = parts[0], parts[-1]
        if not path.endswith(".py"):
            continue
        if status.startswith("D"):
            deleted.append(path)
        else:
            changed.append(path)
    return changed, deleted


def added_lines(base: str, path: str) -> set[int]:
    """Return the line numbers in ``path`` added or modified vs ``base``."""
    out = git("diff", "--unified=0", "--merge-base", base, "HEAD", "--", path)
    lines: set[int] = set()
    for raw in out.splitlines():
        match = HUNK_HEADER.match(raw)
        if match:
            start = int(match.group(1))
            count = int(match.group(2)) if match.group(2) is not None else 1
            lines.update(range(start, start + count))
    return lines


def overlaps(lines: set[int], start: int, end: int) -> bool:
    """Return True if any line in ``[start, end]`` is in ``lines``."""
    return any(ln in lines for ln in range(start, end + 1))


# ---------------------------------------------------------------------------
# Check: ruff on changed lines
# ---------------------------------------------------------------------------
def check_lint(base: str, files: Iterable[str], reporter: Reporter) -> None:
    """Run ruff on ``files`` and report findings touching changed lines."""
    files = [f for f in files if not f.startswith("examples/")]
    if not files:
        print("lint: no changed Python files.")
        return

    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format", "json",
         "--exit-zero", *files],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        reporter.error(f"ruff failed to run:\n{proc.stderr}")
        return
    findings = json.loads(proc.stdout or "[]")

    n_total, n_reported = len(findings), 0
    for path in files:
        lines = added_lines(base, path)
        abs_path = str(REPO_ROOT / path)
        for f in findings:
            if f["filename"] != abs_path:
                continue
            start, end = f["location"]["row"], f["end_location"]["row"]
            if overlaps(lines, start, end):
                n_reported += 1
                fix = ""
                if f.get("fix"):
                    fix = " (fixable with `ruff check --fix`)"
                reporter.error(
                    f"{f['code']}: {f['message']}{fix}",
                    file=path,
                    line=start,
                )
    print(
        f"lint: {n_reported} finding(s) on changed lines "
        f"({n_total} in the changed files overall)."
    )


# ---------------------------------------------------------------------------
# Check: docstrings on new/modified definitions
# ---------------------------------------------------------------------------
def _definitions(tree: ast.AST) -> Iterable[ast.AST]:
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            yield node


def check_docstrings(
    base: str, files: Iterable[str], reporter: Reporter
) -> None:
    """Require a docstring on every definition whose header changed."""
    n_checked = 0
    for path in files:
        exempt = DOCSTRING_EXEMPT_DIRS + ("examples/",)
        if path.startswith(exempt):
            continue
        source = (REPO_ROOT / path).read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            reporter.error(
                f"cannot parse file: {exc}", file=path, line=exc.lineno
            )
            continue
        lines = added_lines(base, path)
        for node in _definitions(tree):
            # The "header" runs from the first decorator to the line holding
            # the colon; a definition counts as new/modified if any of it
            # changed.  The docstring itself is deliberately excluded so that
            # editing an existing docstring does not re-trigger the check.
            header_start = min(
                [node.lineno] + [d.lineno for d in node.decorator_list]
            )
            header_end = node.body[0].lineno - 1 if node.body else node.lineno
            header_end = max(header_end, node.lineno)
            if not overlaps(lines, header_start, header_end):
                continue
            n_checked += 1
            if ast.get_docstring(node, clean=False) is None:
                is_class = isinstance(node, ast.ClassDef)
                kind = "class" if is_class else "function"
                reporter.error(
                    f"new or modified {kind} `{node.name}` has no docstring "
                    "(CONTRIBUTING.md: every newly implemented function, "
                    "method and class must include a docstring).",
                    file=path,
                    line=node.lineno,
                )
    print(f"docstrings: checked {n_checked} new/modified definition(s).")


# ---------------------------------------------------------------------------
# Check: unit tests accompany changed modules
# ---------------------------------------------------------------------------
def expected_test_files(module_path: str) -> list[pathlib.Path]:
    """Candidate test-file locations for a module in ``dingo_lensing/``."""
    rel = pathlib.Path(module_path).relative_to(PACKAGE_DIR)
    name = f"test_{rel.stem}.py"
    candidates = [
        # tests/test_<module>.py
        REPO_ROOT / TESTS_DIR / name,
        # tests/<subpackage>/test_<module>.py
        REPO_ROOT / TESTS_DIR / rel.parent / name,
    ]
    return list(dict.fromkeys(candidates))  # de-duplicate, keep order


def check_tests(
    files: Iterable[str], deleted: Iterable[str], reporter: Reporter
) -> None:
    """Check test-file presence and naming conventions."""
    files = list(files)
    n_modules = 0
    for path in files:
        if not path.startswith(PACKAGE_DIR + "/"):
            continue
        if pathlib.Path(path).name in TEST_EXEMPT_MODULES:
            continue
        n_modules += 1
        candidates = expected_test_files(path)
        if not any(c.is_file() for c in candidates):
            shown = " or ".join(
                str(c.relative_to(REPO_ROOT)) for c in candidates
            )
            reporter.error(
                f"`{path}` was changed but no unit-test file was found "
                f"(expected {shown}). CONTRIBUTING.md: new functionality "
                "must be accompanied by unit tests.",
                file=path,
                line=1,
            )

    # Naming conventions inside tests/ (checked for every test file present,
    # not only the changed ones; cheap and keeps the suite collectable).
    tests_root = REPO_ROOT / TESTS_DIR
    n_test_files = 0
    if tests_root.is_dir():
        for test_file in sorted(tests_root.rglob("*.py")):
            rel = str(test_file.relative_to(REPO_ROOT))
            if test_file.name in ("conftest.py", "__init__.py"):
                continue
            n_test_files += 1
            if not test_file.name.startswith("test_"):
                reporter.error(
                    "test files must be named `test_<module>.py` so that "
                    "pytest collects them.",
                    file=rel,
                    line=1,
                )
                continue
            try:
                tree = ast.parse(test_file.read_text(encoding="utf-8"))
            except SyntaxError:
                continue  # reported by ruff / pytest instead
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and _looks_like_test(
                    node
                ) and not node.name.startswith("test_"):
                    reporter.error(
                        f"`{node.name}` looks like a test but does not start "
                        "with `test_`, so pytest will not run it.",
                        file=rel,
                        line=node.lineno,
                    )
    print(
        f"tests: {n_modules} changed package module(s) checked, "
        f"{n_test_files} test file(s) present."
    )


def _looks_like_test(node: ast.FunctionDef) -> bool:
    """Heuristic: a top-level function with ``assert`` or ``pytest.raises``.

    Fixtures (decorated with ``pytest.fixture``) and private helpers
    (``_name``) are never treated as tests.
    """
    if node.name.startswith("_"):
        return False
    for dec in node.decorator_list:
        text = ast.unparse(dec)
        if "fixture" in text:
            return False
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assert):
            return True
        if isinstance(sub, ast.Call) and "raises" in ast.unparse(sub.func):
            return True
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the requested checks, and return an exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "check",
        nargs="?",
        default="all",
        choices=["all", "lint", "docstrings", "tests"],
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        help="commit/branch to diff against (default: origin/main)",
    )
    args = parser.parse_args(argv)

    reporter = Reporter()
    changed, deleted = changed_python_files(args.base)
    print(f"Comparing HEAD against {args.base}: "
          f"{len(changed)} changed, {len(deleted)} deleted Python file(s).")

    if args.check in ("all", "lint"):
        check_lint(args.base, changed, reporter)
    if args.check in ("all", "docstrings"):
        check_docstrings(args.base, changed, reporter)
    if args.check in ("all", "tests"):
        check_tests(changed, deleted, reporter)

    if reporter.n_errors:
        print(f"\n{reporter.n_errors} problem(s) found. See CONTRIBUTING.md.")
        return 1
    print("\nAll CONTRIBUTING.md checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
