"""Unit tests for the container's pinned requirements (make_requirements.py).

The image must run the same software as dingo_env apart from the documented
changes, so these check the generated requirements against dingo_env's
recorded package list, package by package. Standard library only.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

CONTAINER = Path(__file__).resolve().parent.parent / "container"
sys.path.insert(0, str(CONTAINER))

from make_requirements import (  # noqa: E402
    CPU_INDEX,
    HEADER,
    main,
    make_requirements,
    normalise,
    read_pip_list,
)

PIP_LIST = CONTAINER / "dingo_env_pip_list.txt"
REQUIREMENTS = CONTAINER / "requirements-cpu.txt"


def requirement_versions(lines) -> dict:
    return dict(
        line.split("==", 1) for line in lines if "==" in line and not line.startswith("#")
    )


class TestNormalise(unittest.TestCase):
    def test_matches_pip_name_normalisation(self):
        self.assertEqual(normalise("dingo_lensing"), "dingo-lensing")
        self.assertEqual(normalise("Bilby_Pipe"), "bilby-pipe")
        self.assertEqual(normalise("ruamel.yaml"), "ruamel-yaml")
        self.assertEqual(normalise("zope__interface"), "zope-interface")


class TestReadPipList(unittest.TestCase):
    def write(self, text: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "pip_list.txt"
        path.write_text(text)
        return path

    def test_reads_names_and_versions_skipping_comments_and_blanks(self):
        path = self.write("# comment\nTorch==2.13.0\n\ndingo_lensing==0.0.1\r\n")
        self.assertEqual(read_pip_list(path), {"torch": "2.13.0", "dingo-lensing": "0.0.1"})

    def test_duplicate_package_is_an_error(self):
        path = self.write("dingo_lensing==0.0.1\ndingo-lensing==0.0.2\n")
        with self.assertRaisesRegex(ValueError, "Duplicate package"):
            read_pip_list(path)

    def test_line_without_a_pinned_version_is_an_error(self):
        for text in ("numpy\n", "numpy==\n", "numpy>=2\n"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "Expected 'name==version'"):
                    read_pip_list(self.write(text))


class TestMakeRequirements(unittest.TestCase):
    PACKAGES = {
        "torch": "2.13.0",
        "torchvision": "0.28.0+cu130",
        "nvidia-cublas": "13.1.1.3",
        "cuda-toolkit": "13.0.3.0",
        "triton": "3.7.1",
        "dingo-lensing": "0.0.1",
        "modwaveforms": "0.1.0",
        "dingo-gw": "0.9.8",
        "numpy": "2.3.5",
    }

    def test_header_and_cpu_index_come_first(self):
        lines = make_requirements(self.PACKAGES)
        self.assertEqual(lines[:2], [HEADER, f"--extra-index-url {CPU_INDEX}"])

    def test_keeps_other_packages_drops_cuda_and_git_installs_and_uses_cpu_torch(self):
        lines = make_requirements(self.PACKAGES)
        self.assertEqual(
            lines[2:],
            [
                "dingo-gw==0.9.8",
                "numpy==2.3.5",
                "torch==2.13.0+cpu",
                "torchvision==0.28.0+cpu",
            ],
        )

    def test_output_does_not_depend_on_input_order(self):
        reordered = dict(reversed(list(self.PACKAGES.items())))
        self.assertEqual(make_requirements(reordered), make_requirements(self.PACKAGES))


class TestRealDingoEnv(unittest.TestCase):
    """Checks against the package list recorded from dingo_env on the cluster."""

    def setUp(self):
        self.recorded = read_pip_list(PIP_LIST)
        self.pinned = requirement_versions(REQUIREMENTS.read_text().splitlines())

    def test_every_kept_package_has_dingo_envs_exact_version(self):
        excluded = {
            name
            for name in self.recorded
            if name.startswith(("nvidia-", "cuda-"))
            or name in ("triton", "dingo-lensing", "modwaveforms", "torch", "torchvision")
        }
        kept = {name: version for name, version in self.recorded.items() if name not in excluded}
        self.assertEqual(
            {name: version for name, version in self.pinned.items() if name in kept}, kept
        )
        self.assertEqual(set(self.pinned) - set(kept), {"torch", "torchvision"})

    def test_pytorch_is_the_same_release_as_a_cpu_build(self):
        for name in ("torch", "torchvision"):
            with self.subTest(package=name):
                release = self.recorded[name].split("+", 1)[0]
                self.assertEqual(self.pinned[name], f"{release}+cpu")

    def test_no_cuda_or_git_installed_package_is_pinned(self):
        for name in self.pinned:
            with self.subTest(package=name):
                self.assertFalse(name.startswith(("nvidia-", "cuda-")))
                self.assertNotIn(name, ("triton", "dingo-lensing", "modwaveforms"))

    def test_committed_requirements_file_is_up_to_date(self):
        main([str(PIP_LIST), "--check", str(REQUIREMENTS)])


if __name__ == "__main__":
    unittest.main()
