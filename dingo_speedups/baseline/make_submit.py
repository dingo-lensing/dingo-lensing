"""Write the Condor submit file for the step 2.1 baseline job (baseline_run.py).

Set up as the container smoke test proved on CIT
(../../parallelisation/container/smoke_test.sh): The image comes from OSDF with
the access point's token and is named in MY.SingularityImage, the executable is
the image's Python, and the job stays on CIT's own pool. Like bilby_pipe's jobs,
it runs with OMP_NUM_THREADS=1.

Every input is transferred from an absolute path and arrives in the job's scratch
folder under its own name; the job writes everything into out/, which comes back.

Standard library only.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import List, Optional

ACCOUNTING_GROUP = "ligo.dev.o4.cbc.explore.test"


@dataclass
class BaselineJob:
    image_url: str  # osdf:///igwn/cit/staging/<user>/containers/<image>.sif
    run_script: str  # absolute paths on the access point
    guard: str
    tarball: str
    model: Optional[str]  # the network, or None with a proposal
    event_data: str
    commit: str
    proposal: Optional[str] = None  # network samples to importance-sample instead
    num_samples: int = 50_000
    batch_size: int = 5_000
    cpus: int = 32
    memory_gb: int = 48
    disk_gb: int = 12
    priority: int = 50
    seed: int = 1

    def check(self) -> None:
        if not self.image_url.startswith("osdf:///") or not self.image_url.endswith(".sif"):
            raise ValueError(f"Expected an osdf:///...sif image URL, got {self.image_url!r}")
        if (self.model is None) == (self.proposal is None):
            raise ValueError("Give exactly one of model and proposal")
        for name in ("run_script", "guard", "tarball", "model", "event_data", "proposal"):
            path = getattr(self, name)
            if path is None:
                continue
            if not PurePosixPath(path).is_absolute():
                raise ValueError(f"{name} must be an absolute path, got {path!r}")
            if "," in path or " " in path:
                raise ValueError(f"{name} must not contain commas or spaces: {path!r}")
        if len(self.commit) != 40 or any(c not in "0123456789abcdef" for c in self.commit):
            raise ValueError(f"commit must be a full 40-character hash, got {self.commit!r}")
        for name in ("num_samples", "batch_size", "cpus", "memory_gb", "disk_gb"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")


def name(path: str) -> str:
    return PurePosixPath(path).name


def submit_text(job: BaselineJob) -> str:
    job.check()
    network = ("--model", name(job.model)) if job.model else ("--proposal", name(job.proposal))
    options = [
        ("--tarball", name(job.tarball)),
        ("--commit", job.commit),
        network,
        ("--event-data", name(job.event_data)),
        ("--num-samples", str(job.num_samples)),
        ("--batch-size", str(job.batch_size)),
        ("--num-processes", str(job.cpus)),
        ("--seed", str(job.seed))
    ]
    arguments = ["-I", name(job.run_script), *(item for option in options for item in option)]
    inputs: List[str] = [
        job.image_url,
        job.run_script,
        job.guard,
        job.tarball,
        job.model or job.proposal,
        job.event_data
    ]
    lines = [
        "universe = vanilla",
        "executable = /opt/dingo_env/bin/python",
        f'arguments = "{" ".join(arguments)}"',
        "transfer_executable = False",
        f'MY.SingularityImage = "./{name(job.image_url)}"',
        "requirements = (HAS_SINGULARITY=?=True)",
        "MY.flock_local = True",
        'MY.DESIRED_Sites = "nogrid"',
        "should_transfer_files = YES",
        "when_to_transfer_output = ON_EXIT",
        f"transfer_input_files = {', '.join(inputs)}",
        "transfer_output_files = out",
        "use_oauth_services = scitokens",
        'environment = "OMP_NUM_THREADS=1"',
        f"request_cpus = {job.cpus}",
        f"request_memory = {job.memory_gb}GB",
        f"request_disk = {job.disk_gb}GB",
        f"priority = {job.priority}",
        f"accounting_group = {ACCOUNTING_GROUP}",
        "log = baseline.log",
        "output = baseline.out",
        "error = baseline.err",
        "queue"
    ]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for field in ("image_url", "run_script", "guard", "tarball", "event_data", "commit"):
        parser.add_argument(f"--{field.replace('_', '-')}", required=True)
    network = parser.add_mutually_exclusive_group(required=True)
    network.add_argument("--model")
    network.add_argument("--proposal")
    defaults = (
        ("num_samples", 50_000),
        ("batch_size", 5_000),
        ("cpus", 32),
        ("memory_gb", 48),
        ("disk_gb", 12),
        ("priority", 50),
        ("seed", 1)
    )
    for field, default in defaults:
        parser.add_argument(f"--{field.replace('_', '-')}", type=int, default=default)
    parser.add_argument("--output", required=True, help="Where to write the submit file")
    args = vars(parser.parse_args(argv))
    output = args.pop("output")
    text = submit_text(BaselineJob(**args))
    with open(output, "w", newline="\n") as handle:
        handle.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
