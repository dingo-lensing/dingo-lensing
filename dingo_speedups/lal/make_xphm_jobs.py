"""Write the manifests and Condor submit files of the end-to-end test of the multi-phase XPHM route.

The jobs (each runs xphm_job.py on its manifest):

* ladder_forward, ladder_reverse: Five setups on the 2.1 run's network samples, one after the
  other on one node, so that their timings compare directly, in both orders to show any effect of
  the order. In LADDER and COMPARISONS below.
* full: The whole job on a fresh draw of the network, DINGO as it is against DINGO with everything
  in, for the time per injection.
* stress: stress_multiphase.py.
* suite_release, suite_patched: DINGO's own tests at the merged branch, with each LAL.

Each job has a folder in the run folder with manifest.json and job.sub. The pre-flight's manifests
go in preflight/: The same tasks, smaller, with the data files at their absolute paths.

Set up as make_submit.py is, on what the 2.1 job proved on CIT. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "baseline"))

from make_submit import ACCOUNTING_GROUP, name  # noqa: E402

SCRIPTS = (
    "xphm_job.py",
    "baseline_run.py",
    "guard.py",
    "compare_results.py",
    "stress_multiphase.py",
    "check_multiphase.py",
    "check_dingo_multiphase.py",
    "run_suite.py"
)
# Task name, DINGO, patched LAL, waveform route. On the release LAL the function does not exist.
LADDER = (
    ("upstream_release", "upstream", False, "nine"),
    ("combined_release", "combined", False, "nine"),
    ("combined_patched_nine", "combined", True, "nine"),
    ("combined_patched_one", "combined", True, "one"),
    ("branch_patched_one", "branch", True, "one")
)
FULL = (
    ("full_upstream_release", "upstream", False, "nine"),
    ("full_combined_patched_one", "combined", True, "one")
)
EXACT = (0.0, 0.0)
# Relative, and absolute for columns that pass through zero, such as the phase.
ROUND_OFF = (1e-9, 1e-7)
# First task, second task, tolerances, must it agree?
COMPARISONS = (
    # The branch changes nothing without the patched LAL, bit for bit (PR #454 did not either).
    ("upstream_release", "combined_release", EXACT, True),
    # The route itself, on one LAL, to round-off.
    ("combined_patched_nine", "combined_patched_one", ROUND_OFF, True),
    # PR #454 changes nothing on the patched LAL either.
    ("combined_patched_one", "branch_patched_one", EXACT, True),
    # For scale: The release and this build differ by more than round-off, before any new route.
    ("upstream_release", "combined_patched_nine", ROUND_OFF, False)
)
FULL_COMPARISONS = (("full_upstream_release", "full_combined_patched_one", ROUND_OFF, False),)
JOBS = ("ladder_forward", "ladder_reverse", "full", "stress", "suite_release", "suite_patched")
PREFLIGHT_JOBS = ("ladder_forward", "full", "stress", "suite_release", "suite_patched")


@dataclass(frozen=True)
class Scale:
    num_samples: int
    batch_size: int
    num_processes: int
    dingo_draws: int
    wide_draws: int
    max_minutes: float
    suite_args: Tuple[str, ...]
    suite_must_pass: bool


# The suite has two failures that upstream main has too, so its exit code decides nothing here;
# collect_xphm_tests.py compares the outcomes test by test.
JOB_SCALE = Scale(50_000, 5_000, 32, 1_000_000, 200_000, 240.0, (), False)
PREFLIGHT_SCALE = Scale(500, 500, 4, 400, 100, 5.0, ("tests/gw/waveform_generator/test_wfg_m.py",), True)


@dataclass(frozen=True)
class Resources:
    cpus: int
    memory_gb: int
    disk_gb: int
    threads: int = 1


RESOURCES = {
    "ladder_forward": Resources(32, 48, 16),
    "ladder_reverse": Resources(32, 48, 16),
    "full": Resources(32, 48, 24),
    "stress": Resources(32, 24, 10),
    "suite_release": Resources(8, 32, 12, threads=8),
    "suite_patched": Resources(8, 32, 12, threads=8)
}


@dataclass
class Inputs:
    run_dir: str
    image_url: str
    upstream_tarball: str
    upstream_commit: str
    branch_tarball: str
    branch_commit: str
    combined_tarball: str
    combined_commit: str
    lal_tarball: str
    proposal: str
    model: str
    event_data: str
    priority: int = 50
    seed: int = 1

    def check(self) -> None:
        if not self.image_url.startswith("osdf:///") or not self.image_url.endswith(".sif"):
            raise ValueError(f"Expected an osdf:///...sif image URL, got {self.image_url!r}")
        for field in ("upstream", "branch", "combined"):
            commit = getattr(self, f"{field}_commit")
            if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
                raise ValueError(f"{field}_commit must be a full 40-character hash, got {commit!r}")
        paths = ("run_dir", "upstream_tarball", "branch_tarball", "combined_tarball", "lal_tarball", "proposal", "model", "event_data")
        for field in paths:
            path = getattr(self, field)
            if not PurePosixPath(path).is_absolute():
                raise ValueError(f"{field} must be an absolute path, got {path!r}")
            if "," in path or " " in path:
                raise ValueError(f"{field} must not contain commas or spaces: {path!r}")

    def dingo(self, which: str) -> Tuple[str, str]:
        return name(getattr(self, f"{which}_tarball")), getattr(self, f"{which}_commit")


def importance_sampling_task(setup: tuple, network: str, inputs: Inputs, scale: Scale, preflight: bool) -> dict:
    """In a job the files sit next to the script; in the pre-flight the data stay where they are."""
    task_name, dingo, lal, route = setup
    tarball, commit = inputs.dingo(dingo)
    return {
        "kind": "importance_sampling",
        "name": task_name,
        "tarball": tarball,
        "commit": commit,
        "lal": lal,
        "route": route,
        network: getattr(inputs, network) if preflight else name(getattr(inputs, network)),
        "event_data": inputs.event_data if preflight else name(inputs.event_data),
        "num_samples": scale.num_samples,
        "batch_size": scale.batch_size,
        "num_processes": scale.num_processes,
        "seed": inputs.seed
    }


def compare_task(comparison: tuple) -> dict:
    first, second, (rtol, atol), must_pass = comparison
    return {
        "kind": "compare",
        "name": f"compare_{first}_vs_{second}",
        "first": first,
        "second": second,
        "rtol": rtol,
        "atol": atol,
        "must_pass": must_pass
    }


def manifest_tasks(job: str, inputs: Inputs, scale: Scale, preflight: bool) -> List[dict]:
    if job in ("ladder_forward", "ladder_reverse"):
        setups = LADDER if job == "ladder_forward" else tuple(reversed(LADDER))
        tasks = [importance_sampling_task(setup, "proposal", inputs, scale, preflight) for setup in setups]
        return tasks + [compare_task(comparison) for comparison in COMPARISONS]
    if job == "full":
        tasks = [importance_sampling_task(setup, "model", inputs, scale, preflight) for setup in FULL]
        return tasks + [compare_task(comparison) for comparison in FULL_COMPARISONS]
    if job == "stress":
        return [
            {
                "kind": "stress",
                "name": "stress",
                "lal": True,
                "dingo_draws": scale.dingo_draws,
                "wide_draws": scale.wide_draws,
                "num_processes": scale.num_processes,
                "seed": inputs.seed,
                "max_minutes": scale.max_minutes
            }
        ]
    if job in ("suite_release", "suite_patched"):
        tarball, commit = inputs.dingo("combined")
        return [
            {
                "kind": "suite",
                "name": job,
                "tarball": tarball,
                "commit": commit,
                "lal": job == "suite_patched",
                "pytest_args": list(scale.suite_args),
                "must_pass": scale.suite_must_pass
            }
        ]
    raise ValueError(f"Unknown job: {job}")


def manifest(job: str, inputs: Inputs, scale: Scale, preflight: bool = False) -> dict:
    tarball, commit = inputs.dingo("combined")
    return {
        "job": job,
        "lal_tarball": name(inputs.lal_tarball),
        "compare_dingo": {"tarball": tarball, "commit": commit},
        "tasks": manifest_tasks(job, inputs, scale, preflight)
    }


def needed_inputs(job_manifest: dict, inputs: Inputs) -> List[str]:
    """The absolute paths of the tarballs and data files this job's tasks use."""
    paths = (
        inputs.upstream_tarball,
        inputs.branch_tarball,
        inputs.combined_tarball,
        inputs.lal_tarball,
        inputs.proposal,
        inputs.model,
        inputs.event_data
    )
    by_name = {name(path): path for path in paths}
    needed = set()
    for task in job_manifest["tasks"]:
        needed.update(task[key] for key in ("tarball", "proposal", "model", "event_data") if task.get(key))
        if task.get("lal"):
            needed.add(job_manifest["lal_tarball"])
        if task["kind"] == "compare":
            needed.add(job_manifest["compare_dingo"]["tarball"])
    return [by_name[file_name] for file_name in sorted(needed)]


def submit_text(job: str, job_manifest: dict, inputs: Inputs) -> str:
    resources = RESOURCES[job]
    run_dir = PurePosixPath(inputs.run_dir)
    scripts = [str(run_dir / "scripts" / script) for script in SCRIPTS]
    files = [inputs.image_url, *scripts, str(run_dir / job / "manifest.json"), *needed_inputs(job_manifest, inputs)]
    lines = [
        "universe = vanilla",
        "executable = /opt/dingo_env/bin/python",
        'arguments = "-I xphm_job.py manifest.json"',
        "transfer_executable = False",
        f'MY.SingularityImage = "./{name(inputs.image_url)}"',
        "requirements = (HAS_SINGULARITY=?=True)",
        "MY.flock_local = True",
        'MY.DESIRED_Sites = "nogrid"',
        "should_transfer_files = YES",
        "when_to_transfer_output = ON_EXIT",
        f"transfer_input_files = {', '.join(files)}",
        "transfer_output_files = out",
        "use_oauth_services = scitokens",
        f'environment = "OMP_NUM_THREADS={resources.threads}"',
        f"request_cpus = {resources.cpus}",
        f"request_memory = {resources.memory_gb}GB",
        f"request_disk = {resources.disk_gb}GB",
        f"priority = {inputs.priority}",
        f"accounting_group = {ACCOUNTING_GROUP}",
        "log = job.log",
        "output = job.out",
        "error = job.err",
        "queue"
    ]
    return "\n".join(lines) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="\n", encoding="utf-8") as handle:
        handle.write(text)


def write_jobs(inputs: Inputs) -> Dict[str, List[str]]:
    inputs.check()
    run_dir = Path(inputs.run_dir)
    for job in JOBS:
        job_manifest = manifest(job, inputs, JOB_SCALE)
        write_text(run_dir / job / "manifest.json", json.dumps(job_manifest, indent=2) + "\n")
        write_text(run_dir / job / "job.sub", submit_text(job, job_manifest, inputs))
    for job in PREFLIGHT_JOBS:
        job_manifest = manifest(job, inputs, PREFLIGHT_SCALE, preflight=True)
        write_text(run_dir / "preflight" / f"{job}.json", json.dumps(job_manifest, indent=2) + "\n")
    write_text(run_dir / "jobs.txt", "\n".join(JOBS) + "\n")
    write_text(run_dir / "preflight_jobs.txt", "\n".join(PREFLIGHT_JOBS) + "\n")
    return {"jobs": list(JOBS), "preflight": list(PREFLIGHT_JOBS)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    fields = (
        "run_dir",
        "image_url",
        "upstream_tarball",
        "upstream_commit",
        "branch_tarball",
        "branch_commit",
        "combined_tarball",
        "combined_commit",
        "lal_tarball",
        "proposal",
        "model",
        "event_data"
    )
    for field in fields:
        parser.add_argument(f"--{field.replace('_', '-')}", required=True)
    parser.add_argument("--priority", type=int, default=50)
    parser.add_argument("--seed", type=int, default=1)
    print(json.dumps(write_jobs(Inputs(**vars(parser.parse_args(argv)))), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
