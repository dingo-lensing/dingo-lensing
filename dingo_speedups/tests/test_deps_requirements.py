"""Unit tests for the dependencies-only image's pins (container/make_deps_requirements.py).

The image must have exactly the DINGO-Lensing image's packages (themselves
dingo_env's) apart from dingo-gw, and every dependency of the DINGO commit we
test. Standard library only; the check against DINGO's pyproject.toml needs git
and a clone of the fork next to this checkout, and is skipped otherwise.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

SPEEDUPS = Path(__file__).resolve().parent.parent
CONTAINER = SPEEDUPS / "container"
sys.path.insert(0, str(CONTAINER))

import make_deps_requirements as deps  # noqa: E402
from make_requirements import normalise, read_pip_list  # noqa: E402

CPU_REQUIREMENTS = deps.PARALLELISATION_CONTAINER / "requirements-cpu.txt"
BASELINE = (SPEEDUPS / "BASELINE_COMMIT").read_text().strip()
# The fork's clone sits next to the sync checkout, e.g. ~/dingo-effeciency on the cluster.
FORK = SPEEDUPS.parents[1] / "dingo-effeciency"


def pins(path: Path) -> dict:
    lines = [line for line in path.read_text().splitlines() if "==" in line and not line.startswith("#")]
    return dict(line.split("==", 1) for line in lines)


class TestDepsRequirements(unittest.TestCase):
    def test_committed_file_is_up_to_date(self):
        deps.main(["--check", str(deps.REQUIREMENTS)])

    def test_same_pins_as_the_cpu_image_without_dingo_gw(self):
        cpu, deps_only = pins(CPU_REQUIREMENTS), pins(deps.REQUIREMENTS)
        self.assertEqual(cpu.pop("dingo-gw"), "0.9.8")
        self.assertEqual(deps_only, cpu)

    def test_same_options_as_the_cpu_image(self):
        options = lambda path: [line for line in path.read_text().splitlines() if line.startswith("--")]
        self.assertEqual(options(deps.REQUIREMENTS), options(CPU_REQUIREMENTS))

    def test_nothing_that_brings_in_dingo(self):
        for name in pins(deps.REQUIREMENTS):
            self.assertNotIn(name, ("dingo-gw", "dingo-lensing", "modwaveforms"))

    def test_a_package_list_without_dingo_gw_is_an_error(self):
        packages = read_pip_list(deps.PIP_LIST)
        del packages["dingo-gw"]
        with self.assertRaisesRegex(ValueError, "Expected to exclude"):
            deps.make_deps_requirements(packages)


def baseline_pyproject():
    if shutil.which("git") is None or not (FORK / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(FORK), "show", f"{BASELINE}:pyproject.toml"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    return result.stdout if result.returncode == 0 else None


@unittest.skipUnless(baseline_pyproject(), f"needs the fork's clone at {FORK} with {BASELINE[:10]}")
class TestBaselineDependencies(unittest.TestCase):
    def test_every_dependency_of_the_baseline_commit_is_pinned(self):
        block = re.search(r"^dependencies = \[(.*?)^\]", baseline_pyproject(), re.S | re.M).group(1)
        items = re.findall(r'"([^"]+)"', block)
        names = [normalise(re.split(r"[<>=!~ ;\[]", item, maxsplit=1)[0]) for item in items]
        self.assertGreater(len(names), 10)
        pinned = pins(deps.REQUIREMENTS)
        self.assertEqual([name for name in names if name not in pinned], [])


if __name__ == "__main__":
    unittest.main()
