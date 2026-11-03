"""DINGO's own test suite from a shipped tree, with the image's LAL or with build_lal.sh's.

Runs inside the dependencies-only image (see xphm_job.py):

    python -I run_suite.py --tree DIR --commit SHA [--lal-site DIR] --junit REPORT.xml [-- PYTEST ARGUMENTS]

Without test paths among the pytest arguments it runs all of tests/. With --lal-site, that LAL is
first on sys.path, and NRSur7dq2 and NRSur7dq4 raise, as they do with the release LAL in the image
(check_dingo_multiphase.raise_for_nrsur).

Exit code: pytest's, or 2 if the LAL is not the one asked for or the guard refused.
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for folder in (HERE, HERE.parent):
    if (folder / "guard.py").is_file():
        sys.path.insert(0, str(folder))
        break
sys.path.insert(0, str(HERE))

import guard  # noqa: E402
from check_dingo_multiphase import raise_for_nrsur  # noqa: E402


def main(argv=None) -> int:
    faulthandler.enable()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tree", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--lal-site", help="A folder with the lal and lalsimulation packages")
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("pytest_args", nargs="*", help="Arguments for pytest, after --")
    args = parser.parse_args(argv)

    if args.lal_site:
        lal_site = Path(args.lal_site).resolve()
        sys.path.insert(0, str(lal_site))
        import lalsimulation as LS

        origin = Path(LS.__file__).resolve()
        if lal_site not in origin.parents or not hasattr(LS, "SimInspiralFDMultiPhase"):
            print(f"LAL FAILED: lalsimulation is {origin}, not {lal_site}'s with SimInspiralFDMultiPhase", file=sys.stderr)
            return 2
        outside = guard.lal_libraries_outside(lal_site.parent)
        if outside:
            print(f"LAL FAILED: LAL's libraries are not those shipped with {lal_site}: {outside}", file=sys.stderr)
            return 2
        print(json.dumps({"lal_libraries": guard.mapped_libraries()}), flush=True)
        raise_for_nrsur(LS)
    try:
        record = guard.use_dingo(args.tree, args.commit)
    except guard.GuardError as error:
        print(f"GUARD FAILED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(record, indent=2), flush=True)

    import pytest

    junit = args.junit.resolve()
    os.chdir(record["dingo"]["tree"])  # for DINGO's pyproject.toml, and relative test paths
    pytest_args = list(args.pytest_args)
    if not any(not arg.startswith("-") and Path(arg.split("::")[0]).exists() for arg in pytest_args):
        pytest_args.append("tests")
    return int(pytest.main(["--rootdir", ".", "-c", "pyproject.toml", "-p", "no:cacheprovider", "-rfEs", f"--junitxml={junit}", *pytest_args]))


if __name__ == "__main__":
    sys.exit(main())
