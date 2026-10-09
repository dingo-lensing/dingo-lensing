#!/usr/bin/env python3
"""Check a workflow dingo_lensing_pipe built, before launch.sh submits it.

Everything expected comes from the test's config, so a config change can't
leave a check behind. Every job must run its executable from the image's
environment, inside the image; receive the image from OSDF with the access
point's own token; end with the config's requirements override, which replaces
DINGO's remote-pool (IS_GLIDEIN) requirement so the job stays on CIT's pool;
and ask for enough disk for the files it receives. Jobs that read the model or
the data must receive them, since execute nodes no longer see /home. Standard
library only, like the rest of the launch checks.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pipe_config import data_dict_files, is_unset, parse_dict, read_pipe_ini

IMAGE_ENV = "/opt/dingo_env"
# The executable of each kind of job DINGO-Lensing builds: One of each per event.
EXECUTABLES = {
    "generation": "dingo_lensing_pipe_generation",
    "sampling": "dingo_lensing_pipe_sampling",
    "importance sampling": "dingo_lensing_pipe_importance_sampling",
    "plot": "dingo_pipe_plot",
}
# Disk beyond the files a job receives, for its outputs.
DISK_HEADROOM_GB = 2.0
GB = 1024**3  # Condor's GB


def read_submit_file(path) -> List[Tuple[str, str]]:
    """(key, value) pairs of a Condor submit file, in order.

    Keys are lower-cased, as Condor treats them case-insensitively. Comments
    and lines without '=' (such as 'queue') are skipped.
    """
    pairs = []
    for line in Path(path).read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        pairs.append((key.strip().lower(), value.strip()))
    return pairs


def last_value(pairs, key: str) -> Optional[str]:
    """The value Condor uses for a key: The last one given."""
    values = [value for name, value in pairs if name == key.lower()]
    return values[-1] if values else None


def transfer_inputs(pairs) -> List[str]:
    raw = last_value(pairs, "transfer_input_files") or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def disk_gb(value: Optional[str]) -> float:
    """A request_disk value in GB, as bilby_pipe writes it ('<n>GB')."""
    if value is None or not value.upper().endswith("GB"):
        raise ValueError(f"Expected request_disk as '<n>GB', got {value!r}")
    return float(value[:-2])


def requirements_override(config: Dict[str, str]) -> str:
    """The requirements expression the config's extra-lines give every job."""
    raw = config.get("extra-lines", "")
    if not (raw.startswith("[") and raw.endswith("]")):
        raise ValueError(f"Expected extra-lines as a [...] list, got {raw!r}")
    # bilby_pipe splits the list on commas.
    entries = [entry.strip() for entry in raw[1:-1].split(",")]
    found = [
        entry.partition("=")[2].strip()
        for entry in entries
        if entry.partition("=")[0].strip().lower() == "requirements"
    ]
    if len(found) != 1:
        raise ValueError(f"Expected one requirements line in extra-lines, got {len(found)}")
    return found[0]


def expected_settings(config: Dict[str, str], run_dir: Path) -> dict:
    """What every job of a config's workflow should have, from the config (and,
    for a data-dict glob, the frame files it matches in run_dir)."""
    image_url = config["container"]
    data_files = [
        path for value in parse_dict(config["data-dict"]).values() for path in data_dict_files(value, run_dir)
    ]
    psd_files = []
    if not is_unset(config, "psd-dict"):
        psd_files = [
            path for path in parse_dict(config["psd-dict"]).values() if path not in (None, "None")
        ]
    return {
        "image_url": image_url,
        "image_name": image_url.rsplit("/", 1)[-1],
        "requirements": requirements_override(config),
        "model": config["model"],
        "generation_inputs": [config["model"], *data_files, *psd_files],
        "gps_file": None if is_unset(config, "gps-file") else config["gps-file"],
    }


def file_sizes(expected: dict, run_dir: Path, osdf_root: str = "/osdf") -> Dict[str, int]:
    """Bytes of each file the jobs receive, keyed as the submit files name them.

    The image is sized from its staged copy, which bilby_pipe finds the same
    way (osdf:// becomes /osdf); relative data paths are relative to run_dir.
    """
    paths = {expected["image_url"]: Path(osdf_root + expected["image_url"][len("osdf://"):])}
    for name in expected["generation_inputs"]:
        paths[name] = run_dir / name
    return {name: path.stat().st_size for name, path in paths.items()}


def job_kind(executable: str) -> Optional[str]:
    name = executable.rsplit("/", 1)[-1]
    for kind, expected_name in EXECUTABLES.items():
        if name == expected_name:
            return kind
    return None


def check_job(pairs, expected: dict, sizes: Dict[str, int]) -> Tuple[Optional[str], List[str]]:
    """A job's kind and its problems, if any."""
    problems = []
    executable = last_value(pairs, "executable") or ""
    kind = job_kind(executable)
    if kind is None:
        problems.append(f"Unexpected executable {executable!r}")
    elif executable != f"{IMAGE_ENV}/bin/{EXECUTABLES[kind]}":
        problems.append(f"Executable {executable!r} is not the image's {IMAGE_ENV}/bin/{EXECUTABLES[kind]}")

    image = last_value(pairs, "my.singularityimage")
    if image != f'"./{expected["image_name"]}"':
        problems.append(f"Not run inside the image: MY.SingularityImage is {image!r}")
    if (last_value(pairs, "transfer_executable") or "").lower() != "false":
        problems.append("transfer_executable is not False, so the executable wouldn't be the image's")
    inputs = transfer_inputs(pairs)
    if expected["image_url"] not in inputs:
        problems.append(f"The image {expected['image_url']} is not among the files sent to the job")
    token = last_value(pairs, "use_oauth_services")
    if token != "scitokens":
        problems.append(f"use_oauth_services is {token!r}, not scitokens (the access point's own issuer)")
    requirements = last_value(pairs, "requirements")
    if requirements != expected["requirements"]:
        problems.append(
            f"Final requirements are {requirements!r}, not the config's override {expected['requirements']!r}"
        )
    if any("igwn+osdf://" in value for _, value in pairs):
        problems.append("A file comes through igwn+osdf://, which needs a vault token jobs don't get (finding 13)")

    received = {"generation": expected["generation_inputs"], "sampling": [expected["model"]]}.get(kind, [])
    for path in received:
        if path not in inputs:
            problems.append(f"{path} is not sent to the job, and execute nodes can't see /home")
    gps_file = expected["gps_file"]
    if kind == "generation" and gps_file is not None:
        if not any(os.path.basename(item) == os.path.basename(gps_file) for item in inputs):
            problems.append(f"The GPS file {gps_file} is not sent to the job")

    try:
        disk = disk_gb(last_value(pairs, "request_disk"))
    except ValueError as error:
        problems.append(str(error))
    else:
        files_gb = sum(sizes.get(path, 0) for path in {expected["image_url"], *received}) / GB
        if disk < files_gb + DISK_HEADROOM_GB:
            problems.append(
                f"Requests {disk:g} GB of disk but receives {files_gb:.2f} GB of files; set "
                f"request-disk to at least {files_gb + DISK_HEADROOM_GB:.1f}"
            )
    return kind, problems


def dag_jobs(dag_path: Path, run_dir: Path) -> List[Tuple[str, Path]]:
    """(job name, submit file) for each JOB line of a DAG file.

    bilby_pipe keeps outdir relative to the folder the workflow is built in,
    so the JOB lines name submit files relative to run_dir, which is also
    where condor_submit_dag runs.
    """
    jobs = []
    for line in dag_path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "JOB":
            submit = Path(parts[2])
            jobs.append((parts[1], submit if submit.is_absolute() else run_dir / submit))
    return jobs


def check_workflow(
    run_dir: Path, config_name: str, events: int, osdf_root: str = "/osdf"
) -> Tuple[List[str], Dict[str, int]]:
    """Problems with the workflow a config built in run_dir, and its jobs of each kind."""
    config = read_pipe_ini(run_dir / config_name)
    try:
        expected = expected_settings(config, run_dir)
        sizes = file_sizes(expected, run_dir, osdf_root)
    except (OSError, ValueError, KeyError) as error:
        return [f"Cannot work out what to expect: {type(error).__name__}: {error}"], {}
    submit_dir = run_dir / config["outdir"] / "submit"
    dags = sorted(submit_dir.glob("dag_*.submit"))
    if len(dags) != 1:
        return [f"Expected exactly one DAG file in {submit_dir}, found {len(dags)}"], {}

    problems = []
    counts = dict.fromkeys(EXECUTABLES, 0)
    for name, submit in dag_jobs(dags[0], run_dir):
        if "_merge" in name:
            problems.append(f"{name}: A merge job, though n-parallel is 1")
        if not submit.is_file():
            problems.append(f"{name}: Missing submit file {submit}")
            continue
        kind, job_problems = check_job(read_submit_file(submit), expected, sizes)
        problems.extend(f"{submit.name}: {problem}" for problem in job_problems)
        if kind is not None:
            counts[kind] += 1
    for kind, count in counts.items():
        if count != events:
            problems.append(f"{count} {kind} job(s), expected {events} (one per event)")
    return problems, counts


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path, help="Folder the workflow was built in.")
    parser.add_argument("config", help="The config's file name, in run_dir.")
    parser.add_argument("events", type=int, help="How many events the config lists.")
    args = parser.parse_args(argv)
    label = read_pipe_ini(args.run_dir / args.config)["label"]
    problems, counts = check_workflow(args.run_dir, args.config, args.events)
    for problem in problems:
        print(f"FAILED  {label}: {problem}")
    if problems:
        sys.exit(1)
    print(
        f"{label}: {sum(counts.values())} jobs for {args.events} event(s). Every job runs inside "
        f"the image, receives it from OSDF with the access point's token, stays on CIT's pool "
        f"and asks for enough disk; the jobs that read the model or the data receive them."
    )


if __name__ == "__main__":
    main()
