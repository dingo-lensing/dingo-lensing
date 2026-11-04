"""One job of the end-to-end test of the multi-phase XPHM route.

Runs inside the dependencies-only image, from the job's scratch folder, where Condor has put this
script, the scripts it calls, the tarballs and the manifest that make_xphm_jobs.py wrote:

    python -I xphm_job.py manifest.json

The manifest lists tasks, which run one after the other, each in a process of its own, so that the
timings of different setups on one node can be compared directly. Kinds of task:

* importance_sampling: baseline_run.py with a DINGO tarball, the image's LAL or the patched one,
  and a waveform route it must take.
* compare: compare_results.py on two importance_sampling tasks of this job.
* suite: run_suite.py, DINGO's own tests.
* stress: stress_multiphase.py.

The patched LAL comes as a pack_lal.py tarball, unpacked once. Tasks that use it get its python/
folder first on sys.path and its lib/ folder as LD_LIBRARY_PATH: Execute nodes have no /home, where
the libraries' run paths point.

One task's failure does not stop the others. Everything comes back in out/: A folder per task with
its output and reports, and job.json, rewritten after each task.

Exit code 0 if every task that must pass did, 3 if all ran but a comparison or the stress test
disagrees, 1 if a task or this script broke.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
OUT = Path("out")
WORK = Path("work")
# The exit code with which a task says that it ran and the answer is no.
DISAGREES = {"compare": 1, "stress": 3}
KEPT_FILES = ("baseline.json", "importance_sampling.hdf5")


def find_script(name: str) -> Path:
    """Next to this script in a job; in its own folder of the repository otherwise."""
    for folder in (HERE, HERE.parent / "baseline", HERE.parent):
        if (folder / name).is_file():
            return folder / name
    raise FileNotFoundError(name)


def unpack(tarball: Path, destination: Path) -> Path:
    """Unpack a tarball with one top folder and return that folder."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball) as archive:
        tops = {member.name.split("/")[0] for member in archive.getmembers()}
        if len(tops) != 1:
            raise ValueError(f"{tarball} has {len(tops)} top folders")
        if hasattr(tarfile, "data_filter"):
            archive.extractall(destination, filter="data")
        else:  # Python without extraction filters
            archive.extractall(destination)
    return destination.resolve() / tops.pop()


def absolute(path: str) -> str:
    return str(Path(path).resolve())


def importance_sampling_command(task: dict, lal_root: Optional[Path]) -> List[str]:
    network = ["--proposal", absolute(task["proposal"])] if task.get("proposal") else ["--model", absolute(task["model"])]
    command = [
        sys.executable,
        "-I",
        str(find_script("baseline_run.py")),
        "--tarball",
        absolute(task["tarball"]),
        "--commit",
        task["commit"],
        *network,
        "--event-data",
        absolute(task["event_data"]),
        "--num-samples",
        str(task["num_samples"]),
        "--batch-size",
        str(task["batch_size"]),
        "--num-processes",
        str(task["num_processes"]),
        "--seed",
        str(task["seed"]),
        "--route",
        task["route"]
    ]
    if task["lal"]:
        command += ["--lal-site", str(lal_root / "python")]
    return command


def compare_command(task: dict, tree: Path, commit: str) -> List[str]:
    return [
        sys.executable,
        "-I",
        str(find_script("compare_results.py")),
        "--tree",
        str(tree),
        "--commit",
        commit,
        str((OUT / task["first"] / "importance_sampling.hdf5").resolve()),
        str((OUT / task["second"] / "importance_sampling.hdf5").resolve()),
        "--rtol",
        str(task["rtol"]),
        "--atol",
        str(task["atol"]),
        "--output",
        str((OUT / task["name"] / "compare.json").resolve())
    ]


def suite_command(task: dict, tree: Path, lal_root: Optional[Path]) -> List[str]:
    command = [sys.executable, "-I", str(find_script("run_suite.py")), "--tree", str(tree), "--commit", task["commit"]]
    if task["lal"]:
        command += ["--lal-site", str(lal_root / "python")]
    command += ["--junit", str((OUT / task["name"] / "junit.xml").resolve()), "--", *task["pytest_args"]]
    return command


def stress_command(task: dict, lal_root: Path) -> List[str]:
    return [
        sys.executable,
        "-I",
        str(find_script("stress_multiphase.py")),
        "--lal-site",
        str(lal_root / "python"),
        "--dingo-draws",
        str(task["dingo_draws"]),
        "--wide-draws",
        str(task["wide_draws"]),
        "--num-processes",
        str(task["num_processes"]),
        "--seed",
        str(task["seed"]),
        "--max-minutes",
        str(task["max_minutes"]),
        "--max-tasks-per-worker",
        str(task.get("max_tasks_per_worker", 0)),
        "--memory-limit-gb",
        str(task.get("memory_limit_gb", 0.0)),
        "--output",
        str((OUT / task["name"] / "stress.json").resolve())
    ]


def task_environment(task: dict, lal_root: Optional[Path]) -> Dict[str, str]:
    environment = dict(os.environ)
    if task.get("lal"):
        environment["LD_LIBRARY_PATH"] = str(lal_root / "lib")
    return environment


def task_verdict(kind: str, exit_code: Optional[int]) -> str:
    if exit_code == 0:
        return "passed"
    if exit_code is not None and exit_code == DISAGREES.get(kind):
        return "disagrees"
    return "failed"


def job_exit_code(records: List[dict]) -> int:
    counted = [record for record in records if record["must_pass"]]
    if any(record["verdict"] in ("failed", "skipped") for record in counted):
        return 1
    return 3 if any(record["verdict"] == "disagrees" for record in counted) else 0


def write_report(report: dict) -> None:
    (OUT / "job.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def run_task(task: dict, manifest: dict, lal_root: Optional[Path], records: Dict[str, dict]) -> dict:
    kind, name = task["kind"], task["name"]
    directory = (WORK / name).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    (OUT / name).mkdir(parents=True, exist_ok=True)
    record = {"kind": kind, "must_pass": task.get("must_pass", True), "exit_code": None, "seconds": 0.0}

    if kind == "compare":
        waiting = [other for other in (task["first"], task["second"]) if records.get(other, {}).get("verdict") != "passed"]
        if waiting:
            record.update(verdict="skipped", reason=f"No result from {', '.join(waiting)}")
            return record
        reference = manifest["compare_dingo"]
        command = compare_command(task, unpack(Path(reference["tarball"]), directory), reference["commit"])
    elif kind == "importance_sampling":
        command = importance_sampling_command(task, lal_root)
    elif kind == "suite":
        command = suite_command(task, unpack(Path(task["tarball"]), directory), lal_root)
    elif kind == "stress":
        command = stress_command(task, lal_root)
    else:
        raise ValueError(f"Unknown kind of task: {kind}")

    start = time.perf_counter()
    with open(OUT / name / "output.txt", "w", encoding="utf-8") as output:
        finished = subprocess.run(
            command,
            cwd=directory,
            env=task_environment(task, lal_root),
            stdout=output,
            stderr=subprocess.STDOUT
        )
    record["seconds"] = round(time.perf_counter() - start, 3)
    record["exit_code"] = finished.returncode
    record["verdict"] = task_verdict(kind, finished.returncode)
    if kind == "importance_sampling":
        for file_name in KEPT_FILES:
            produced = directory / "out" / file_name
            if produced.is_file():
                shutil.copy2(produced, OUT / name / file_name)
    return record


def main(argv=None) -> int:
    OUT.mkdir(exist_ok=True)  # first, so Condor always has the folder to transfer back
    argv = sys.argv[1:] if argv is None else argv
    report = {"host": socket.gethostname(), "python": platform.python_version(), "tasks": {}}
    records = report["tasks"]
    try:
        manifest = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
        report["job"] = manifest["job"]
        report["order"] = [task["name"] for task in manifest["tasks"]]
        write_report(report)
        lal_root = None
        if any(task.get("lal") for task in manifest["tasks"]):
            lal_root = unpack(Path(manifest["lal_tarball"]), WORK / "lal")
        for task in manifest["tasks"]:
            try:
                records[task["name"]] = run_task(task, manifest, lal_root, records)
            except Exception as error:  # recorded, and the next task still runs
                records[task["name"]] = {
                    "kind": task["kind"],
                    "must_pass": task.get("must_pass", True),
                    "verdict": "failed",
                    "error": f"{type(error).__name__}: {error}",
                    "traceback": traceback.format_exc()
                }
            print(task["name"], json.dumps({k: v for k, v in records[task["name"]].items() if k != "traceback"}), flush=True)
            write_report(report)
    except Exception as error:  # recorded for the report, then a failed exit
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
        report["exit_code"] = 1
        write_report(report)
        print(report["traceback"], file=sys.stderr)
        return 1
    report["exit_code"] = job_exit_code(list(records.values()))
    write_report(report)
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
