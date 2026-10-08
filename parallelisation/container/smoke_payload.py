"""Runs inside the image on an execute node (see smoke_test.sh).

Prints what the job sees and exits non-zero if anything the pipeline needs is
missing, so the job's exit status alone says whether the image works there.
"""
import importlib.metadata as metadata
import os
import platform
import subprocess
import sys

failures = []


def check(description: str, passed: bool) -> None:
    print(("ok    " if passed else "FAIL  ") + description)
    if not passed:
        failures.append(description)


print(f"Execute node: {platform.node()}")
check("Running the image's Python", sys.executable.startswith("/opt/dingo_env/"))
check("Inside an Apptainer container", os.path.isdir("/.singularity.d"))
try:
    import dingo  # noqa: F401
    import dingo_lensing
    import dingo_lensing.pipe.main  # noqa: F401
    import dingo_lensing.pipe.sampling  # noqa: F401
    import lalsimulation  # noqa: F401
    import modwaveforms  # noqa: F401
    import torch

    check("Imports DINGO, DINGO-Lensing and its pipeline, LAL, modwaveforms, PyTorch", True)
    check("DINGO-Lensing comes from the image", dingo_lensing.__file__.startswith("/opt/dingo-lensing/"))
    print(f"PyTorch {torch.__version__}, threads: {torch.get_num_threads()}")
except Exception as error:
    check(f"Imports ({type(error).__name__}: {error})", False)
command = subprocess.run(
    ["/opt/dingo_env/bin/dingo_lensing_pipe", "--help"], capture_output=True, text=True
)
check("dingo_lensing_pipe --help runs", command.returncode == 0)

for name in ("dingo-gw", "dingo_lensing", "bilby_pipe", "torch"):
    print(f"{name}: {metadata.version(name)}")
with open("/opt/dingo-lensing.commit") as commit:
    print(f"DINGO-Lensing commit: {commit.read().strip()}")
print(f"/home/kailibryan.doney visible here: {os.path.isdir('/home/kailibryan.doney')}")
sys.exit(1 if failures else 0)
