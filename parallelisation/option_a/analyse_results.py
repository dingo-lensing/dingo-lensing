#!/usr/bin/env python3
"""Analyse the option A runs: Completion, agreement between runs, and timing.

Runs on the cluster inside the image (analyse.sh) once the four workflows have
finished, and only reads the run folder. Writes summary.md (a verdict on each
pass criterion in ../test_log.md, with the numbers behind it), summary.json
(every number) and the corner plots into the output folder.

How runs are compared:
- Network samples: Every run of a test analyses identical data with the same
  network, so all its runs draw independently from one distribution. A
  two-sample KS test compares each parameter for every pair of runs, with a
  Bonferroni correction holding the chance of any false alarm in a test at 1%.
- Log evidence: Every pair of runs (and, for T2, the Exercise 3 reference)
  must agree within 3 sigma combined, using DINGO's error estimate, if every
  run has at least 100 effective samples; below that the error is too rough.
- Posteriors: The weighted median and 90% interval of every parameter, side by
  side, for reading.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from check_workflow import dag_jobs, job_kind, last_value, read_submit_file
from condor_logs import dag_outcome, dag_succeeded, job_timing, read_events
from pipe_config import read_pipe_ini

# Label, run folder, config, number of events: As in launch.sh.
WORKFLOWS = [
    ("T1a", "T1", "T1a_single.ini", 1),
    ("T1b", "T1", "T1b_twice.ini", 2),
    ("T2a", "T2", "T2a_single.ini", 1),
    ("T2b", "T2", "T2b_three.ini", 3),
]
TESTS = {"T1": ("T1a", "T1b"), "T2": ("T2a", "T2b")}
# T3: Two different events, alone (T3a, T3b) and together (T3c).
T3_WORKFLOWS = [
    ("T3a", "T3", "T3a_gw150914.ini", 1),
    ("T3b", "T3", "T3b_gw151012.ini", 1),
    ("T3c", "T3", "T3c_both.ini", 2),
]
T3_GROUPS = {"GW150914": [("T3a", 0), ("T3c", 0)], "GW151012": [("T3b", 0), ("T3c", 1)]}
# Kaili's local Exercise 3 run (tutorial_reference/ex3_dingo_lensing_application/ex3_local.log).
REFERENCES = {
    "T2": {"name": "Exercise 3", "log_evidence": -5829.945, "log_evidence_std": 0.014, "sample_efficiency": 0.0940}
}
ALPHA = 0.01
N_SIGMA = 3.0
MIN_N_EFF = 100.0
# An efficiency outside this factor of the reference's is flagged CHECK. Not a
# test: When a few weights dominate, the efficiency has no reliable error.
EFFICIENCY_FACTOR = 2.0
NOT_PARAMETERS = {"log_prob", "log_likelihood", "log_prior", "delta_log_prob_target", "weights"}
RESULT_FILE = re.compile(
    r"^(?P<label>.+)_data(?P<event>\d+)_[0-9-]+_(?P<kind>sampling|importance_sampling)\.hdf5$"
)
CORNER_PLOT = re.compile(r"^(?P<label>.+)_data(?P<event>\d+)_[0-9-]+_importance_sampling_plot_corner\.pdf$")
EVENT_DATA = re.compile(r"^(?P<label>.+)_data(?P<event>\d+)_[0-9-]+_generation_event_data\.hdf5$")
EVENT_INDEX = re.compile(r"_data(\d+)_")
EVENT_TIME = re.compile(r"_data\d+_[0-9-]+_")
PSD_FILE = re.compile(r"^(?P<label>.+)_data(?P<event>\d+)_[0-9-]+_generation_(?P<detector>[A-Z][A-Z0-9]*)_psd\.txt$")


# -- Statistics ---------------------------------------------------------------


def parameter_names(columns) -> List[str]:
    return [name for name in columns if name not in NOT_PARAMETERS]


def importance_summary(weights) -> dict:
    """Effective samples, sample efficiency and log-evidence error, as DINGO computes
    them (dingo/core/result.py: effective_sample_size, sample_efficiency,
    log_evidence_std)."""
    weights = np.asarray(weights, dtype=float)
    n = len(weights)
    n_eff = float(weights.sum() ** 2 / (weights**2).sum())
    return {
        "samples": n,
        "n_eff": n_eff,
        "sample_efficiency": n_eff / n,
        "log_evidence_std": math.sqrt(max(n - n_eff, 0.0) / (n * n_eff)),
    }


def weight_diagnostics(weights) -> dict:
    """How far the heaviest samples dominate the importance weights.

    A proposal that misses part of the posterior gives a few samples huge
    weights, which on their own drag the sample efficiency down; removing the
    heaviest sample then restores much of it. Weights are in units of their mean.
    """
    weights = np.asarray(weights, dtype=float)
    weights = weights / weights.mean()
    order = np.argsort(weights)[::-1]
    rest = weights[order[1:]]
    return {
        "largest_weight": float(weights[order[0]]),
        "top_10_share": float(weights[order[:10]].sum() / weights.sum()),
        "efficiency_without_heaviest": float(rest.sum() ** 2 / (rest**2).sum() / len(rest)),
        "zero_weights": int(np.count_nonzero(weights == 0)),
        "heaviest_index": int(order[0]),
    }


def event_data_comparison(digests: Dict[str, Dict[str, str]]) -> dict:
    """Whether every run's event data are bit-identical, and which datasets differ."""
    names = list(digests)
    first = digests[names[0]]
    differing = {
        key
        for name in names[1:]
        for key in set(first) | set(digests[name])
        if first.get(key) != digests[name].get(key)
    }
    return {"runs": names, "identical": not differing, "differing": sorted(differing)}


def weighted_quantiles(values, weights, quantiles) -> np.ndarray:
    """Quantiles of weighted samples, placing each sample at the middle of its weight."""
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    keep = np.isfinite(values) & (weights > 0)
    values, weights = values[keep], weights[keep]
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    cdf = (np.cumsum(weights) - 0.5 * weights) / weights.sum()
    return np.interp(quantiles, cdf, values)


def ks_comparison(runs: Dict[str, Dict[str, np.ndarray]], alpha: float = ALPHA) -> dict:
    """Two-sample KS tests of every parameter for every pair of runs, Bonferroni-corrected."""
    from scipy.stats import ks_2samp

    names = list(runs)
    parameters = parameter_names(runs[names[0]])
    for name in names[1:]:
        if set(parameter_names(runs[name])) != set(parameters):
            raise ValueError(f"{name} has different parameters from {names[0]}")
    pairs = list(itertools.combinations(names, 2))
    tests = len(pairs) * len(parameters)
    threshold = alpha / tests
    rows = []
    for first, second in pairs:
        for parameter in parameters:
            result = ks_2samp(runs[first][parameter], runs[second][parameter])
            rows.append(
                {
                    "pair": [first, second],
                    "parameter": parameter,
                    "statistic": float(result.statistic),
                    "p_value": float(result.pvalue),
                }
            )
    worst = min(rows, key=lambda row: row["p_value"])
    identical = [
        [first, second]
        for first, second in pairs
        if all(np.array_equal(runs[first][p], runs[second][p]) for p in parameters)
    ]
    return {
        "runs": names,
        "parameters": parameters,
        "tests": tests,
        "alpha": alpha,
        "threshold": threshold,
        "worst": worst,
        "passed": worst["p_value"] >= threshold,
        "identical_pairs": identical,
        "rows": rows,
    }


def evidence_comparison(values: Dict[str, Tuple[float, float]], n_sigma: float = N_SIGMA) -> dict:
    """Whether every pair of log evidences agrees within n_sigma combined errors."""
    rows = []
    for first, second in itertools.combinations(values, 2):
        (ln_first, std_first), (ln_second, std_second) = values[first], values[second]
        combined = math.hypot(std_first, std_second)
        difference = ln_first - ln_second
        z = abs(difference) / combined if combined > 0 else (0.0 if difference == 0 else math.inf)
        rows.append(
            {
                "pair": [first, second],
                "difference": difference,
                "combined_std": combined,
                "z": z,
                "agree": z <= n_sigma,
            }
        )
    return {"n_sigma": n_sigma, "rows": rows, "passed": all(row["agree"] for row in rows)}


# -- Run folders --------------------------------------------------------------


def load_result(path: Path) -> dict:
    """Numeric sample columns and log evidence of a DINGO result file.

    DINGO stores the samples DataFrame as a record array and the log evidence
    as a scalar (dingo/core/dataset.py, recursive_hdf5_save).
    """
    import h5py

    with h5py.File(path, "r") as file:
        records = file["samples"][()]
        samples = {
            name: np.asarray(records[name], dtype=float)
            for name in records.dtype.names
            if records.dtype[name].kind in "fiub"
        }
        log_evidence = float(file["log_evidence"][()]) if "log_evidence" in file else None
    return {"samples": samples, "log_evidence": log_evidence}


def event_data_digests(path: Path) -> Dict[str, str]:
    """SHA-256 of every dataset in an event data file's 'data' group: The strain
    and ASDs that both the network and the likelihood see."""
    import hashlib

    import h5py

    digests = {}
    with h5py.File(path, "r") as file:
        group = file["data"] if "data" in file else file

        def visit(name, item):
            if isinstance(item, h5py.Dataset):
                digests[name] = hashlib.sha256(np.ascontiguousarray(item[()]).tobytes()).hexdigest()

        group.visititems(visit)
    return digests


def event_data_files(data_dir: Path, label: str) -> Dict[int, List[Path]]:
    """{event: [event data files]} for one label."""
    files: Dict[int, List[Path]] = {}
    if data_dir.is_dir():
        for path in sorted(data_dir.iterdir()):
            match = EVENT_DATA.match(path.name)
            if match and match.group("label") == label:
                files.setdefault(int(match.group("event")), []).append(path)
    return files


def psd_files(data_dir: Path, label: str) -> Dict[int, Dict[str, Path]]:
    """{event: {detector: PSD text file}}, as each data-generation job writes them
    with DINGO-Lensing's fix."""
    files: Dict[int, Dict[str, Path]] = {}
    if data_dir.is_dir():
        for path in sorted(data_dir.iterdir()):
            match = PSD_FILE.match(path.name)
            if match and match.group("label") == label:
                files.setdefault(int(match.group("event")), {})[match.group("detector")] = path
    return files


def file_digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def result_files(result_dir: Path, label: str) -> Dict[int, Dict[str, List[Path]]]:
    """{event: {"sampling" | "importance_sampling" | "corner": [paths]}} for one label."""
    files: Dict[int, Dict[str, List[Path]]] = {}
    if not result_dir.is_dir():
        return files
    for path in sorted(result_dir.iterdir()):
        match = RESULT_FILE.match(path.name)
        kind = match.group("kind") if match else None
        if match is None:
            match = CORNER_PLOT.match(path.name)
            kind = "corner"
        if match and match.group("label") == label:
            files.setdefault(int(match.group("event")), {}).setdefault(kind, []).append(path)
    return files


def completion(outdir: Path, label: str, events: int) -> dict:
    """Did the DAG succeed, with one sampling result, importance-sampling result
    and corner plot per event?"""
    problems = []
    dagman_outs = sorted((outdir / "submit").glob("dag_*.submit.dagman.out"))
    outcome = dag_outcome(dagman_outs[0]) if len(dagman_outs) == 1 else None
    if outcome is None:
        problems.append(f"Expected one dagman.out in {outdir / 'submit'}, found {len(dagman_outs)}")
    elif not dag_succeeded(outcome):
        problems.append(f"The DAG did not succeed: {outcome}")
    files = result_files(outdir / "result", label)
    for event in range(events):
        for kind in ("sampling", "importance_sampling", "corner"):
            found = files.get(event, {}).get(kind, [])
            if len(found) != 1:
                problems.append(f"Event {event}: {len(found)} {kind} file(s), expected 1")
    unexpected = sorted(set(files) - set(range(events)))
    if unexpected:
        problems.append(f"Results for events {unexpected}, beyond the {events} listed")
    return {"dag": outcome, "problems": problems, "passed": not problems}


def shared_outputs(outdir: Path, events: int) -> dict:
    """Output files that every event's chain writes under the same name.

    The build writes the complete config and everything in submit/ before any
    job runs. Every other file belongs to the jobs; one whose path has no
    '_data<i>_' is written by the jobs of every event, so in a workflow of
    several events the last job to finish wins.
    """
    per_event: Dict[int, set] = {}
    unindexed = []
    for path in sorted(p for p in outdir.rglob("*") if p.is_file()):
        relative = path.relative_to(outdir).as_posix()
        if relative.startswith("submit/") or relative.endswith("_config_complete.ini"):
            continue
        match = EVENT_INDEX.search(relative)
        if match:
            # Different events also differ in the trigger time that follows the index.
            per_event.setdefault(int(match.group(1)), set()).add(EVENT_TIME.sub("_data<i>_<time>_", relative))
        else:
            unindexed.append(relative)
    outputs = list(per_event.values())
    return {
        "written_by_every_chain": unindexed if events > 1 else [],
        "events_with_outputs": sorted(per_event),
        "same_outputs_per_event": bool(outputs) and all(output == outputs[0] for output in outputs),
        "passed": (events == 1 or not unindexed)
        and sorted(per_event) == list(range(events))
        and all(output == outputs[0] for output in outputs),
    }


def job_rows(run_dir: Path, outdir: Path) -> List[dict]:
    """Timing of every job in a workflow, from its Condor event log."""
    dags = sorted((outdir / "submit").glob("dag_*.submit"))
    if len(dags) != 1:
        raise ValueError(f"Expected one DAG file in {outdir / 'submit'}, found {len(dags)}")
    rows = []
    for name, submit in dag_jobs(dags[0], run_dir):
        pairs = read_submit_file(submit)
        log = last_value(pairs, "log")
        timing = job_timing(read_events(run_dir / log))
        resources = timing.resources
        event = EVENT_INDEX.search(name)
        rows.append(
            {
                "job": name,
                "kind": job_kind(last_value(pairs, "executable") or ""),
                "event": int(event.group(1)) if event else None,
                "succeeded": timing.succeeded,
                "attempts": timing.attempts,
                "submitted": timing.submitted,
                "finished": timing.finished,
                "wait_s": timing.wait_seconds,
                "input_transfer_s": timing.input_seconds,
                "run_s": timing.run_seconds,
                "output_transfer_s": timing.output_seconds,
                "cpu_s": timing.cpu_seconds,
                "wasted_cpu_s": timing.wasted_cpu_seconds,
                "cores_requested": float(last_value(pairs, "request_cpus") or "nan"),
                "cores_used": timing.cores_used,
                "memory_used_mb": resources.get("Memory (MB)", {}).get("Usage"),
                "memory_requested_mb": resources.get("Memory (MB)", {}).get("Request"),
                "disk_used_kb": resources.get("Disk (KB)", {}).get("Usage"),
                "disk_requested_kb": resources.get("Disk (KB)", {}).get("Request"),
                "bytes_received": timing.bytes_received,
                "host": timing.host,
            }
        )
    return rows


def workflow_timing(rows: List[dict]) -> dict:
    """Wall time of the whole workflow and of each event's chain of jobs."""
    finished = [row["finished"] for row in rows]
    if not rows or any(time is None for time in finished):
        return {"complete": False}
    chains = {}
    for event in sorted({row["event"] for row in rows}):
        chain = [row for row in rows if row["event"] == event]
        chains[event] = (max(r["finished"] for r in chain) - min(r["submitted"] for r in chain)).total_seconds()
    return {
        "complete": True,
        "makespan_s": (max(finished) - min(row["submitted"] for row in rows)).total_seconds(),
        "chain_s": chains,
        "cpu_hours": sum(row["cpu_s"] or 0.0 for row in rows) / 3600,
        "wasted_cpu_hours": sum(row["wasted_cpu_s"] for row in rows) / 3600,
        "wait_s": sum(row["wait_s"] or 0.0 for row in rows),
    }


# -- Analysis -----------------------------------------------------------------


def run_name(label: str, event: int, events: int) -> str:
    return label if events == 1 else f"{label}/{event}"


def compare_test(runs: Dict[str, dict], reference: Optional[dict], reference_samples: Optional[dict]) -> dict:
    """Agreement between a test's runs: {name: {"network": samples, "posterior": result}}."""
    network = {name: run["network"]["samples"] for name, run in runs.items()}
    importance = {}
    for name, run in runs.items():
        summary = importance_summary(run["posterior"]["samples"]["weights"])
        summary["log_evidence"] = run["posterior"]["log_evidence"]
        importance[name] = summary
    evidences = {name: (s["log_evidence"], s["log_evidence_std"]) for name, s in importance.items()}
    if reference is not None:
        evidences[reference["name"]] = (reference["log_evidence"], reference["log_evidence_std"])
    meaningful = all(s["n_eff"] >= MIN_N_EFF for s in importance.values())
    parameters = parameter_names(next(iter(runs.values()))["posterior"]["samples"])
    posteriors = {
        parameter: {
            name: [
                float(q)
                for q in weighted_quantiles(
                    run["posterior"]["samples"][parameter],
                    run["posterior"]["samples"]["weights"],
                    [0.05, 0.5, 0.95],
                )
            ]
            for name, run in runs.items()
            if parameter in run["posterior"]["samples"]
        }
        for parameter in parameters
    }
    weights = {}
    for name, run in runs.items():
        samples = run["posterior"]["samples"]
        diagnostics = weight_diagnostics(samples["weights"])
        heaviest = diagnostics.pop("heaviest_index")
        diagnostics["heaviest_sample"] = {key: float(values[heaviest]) for key, values in samples.items()}
        weights[name] = diagnostics
    psds = {name: run.get("psd_files") or {} for name, run in runs.items()}
    if all(psds.values()):
        psd_comparison = event_data_comparison(
            {name: {det: file_digest(p) for det, p in files.items()} for name, files in psds.items()}
        )
    else:
        psd_comparison = {"identical": None, "missing": [name for name, files in psds.items() if not files]}
    data_files = {name: run.get("event_data") for name, run in runs.items()}
    if all(path is not None for path in data_files.values()):
        event_data = event_data_comparison({name: event_data_digests(path) for name, path in data_files.items()})
    else:
        event_data = {"identical": None, "missing": [name for name, path in data_files.items() if path is None]}
    outside = []
    if reference is not None:
        low = reference["sample_efficiency"] / EFFICIENCY_FACTOR
        high = reference["sample_efficiency"] * EFFICIENCY_FACTOR
        outside = [name for name, s in importance.items() if not low <= s["sample_efficiency"] <= high]
    comparison = {
        "network_ks": ks_comparison(network),
        "importance": importance,
        "weights": weights,
        "efficiency_outside_reference_factor": outside,
        "event_data": event_data,
        "psd_files": psd_comparison,
        "evidence": evidence_comparison(evidences),
        "evidence_meaningful": meaningful,
        "posteriors": posteriors,
        "reference": reference,
    }
    if reference_samples is not None:
        try:
            comparison["network_ks_with_reference"] = ks_comparison({**network, "reference": reference_samples})
        except ValueError as error:
            comparison["network_ks_with_reference_error"] = str(error)
    return comparison


def load_workflows(run_root: Path, workflow_list) -> Tuple[dict, Dict[Tuple[str, int], dict]]:
    """Each workflow's completion, shared files and timing, and every event's run."""
    workflows = {}
    runs: Dict[Tuple[str, int], dict] = {}
    for label, folder, config_name, events in workflow_list:
        run_dir = run_root / folder
        outdir = run_dir / read_pipe_ini(run_dir / config_name)["outdir"]
        rows = job_rows(run_dir, outdir)
        files = result_files(outdir / "result", label)
        workflows[label] = {
            "events": events,
            "completion": completion(outdir, label, events),
            "shared_outputs": shared_outputs(outdir, events),
            "jobs": rows,
            "timing": workflow_timing(rows),
            "corner_plots": [
                str(paths[0]) for kinds in files.values() for kind, paths in kinds.items() if kind == "corner"
            ],
        }
        data_files = event_data_files(outdir / "data", label)
        psds = psd_files(outdir / "data", label)
        for event in range(events):
            kinds = files.get(event, {})
            if len(kinds.get("sampling", [])) == 1 and len(kinds.get("importance_sampling", [])) == 1:
                event_data = data_files.get(event, [])
                runs[(label, event)] = {
                    "name": run_name(label, event, events),
                    "network": load_result(kinds["sampling"][0]),
                    "posterior": load_result(kinds["importance_sampling"][0]),
                    "event_data": event_data[0] if len(event_data) == 1 else None,
                    "psd_files": psds.get(event, {}),
                }
    return workflows, runs


def group_runs(runs: Dict[Tuple[str, int], dict], members, workflows: dict) -> Dict[str, dict]:
    """The runs of one comparison group; an event of None means all of a workflow's events."""
    group = {}
    for label, event in members:
        indices = range(workflows[label]["events"]) if event is None else [event]
        for index in indices:
            if (label, index) in runs:
                run = runs[(label, index)]
                group[run["name"]] = run
    return group


def analyse(
    run_root: Path,
    reference_results: Optional[Path] = None,
    suite: str = "T1T2",
    earlier_run_root: Optional[Path] = None,
) -> dict:
    report = {"run_root": str(run_root), "suite": suite, "analysed": datetime.now().isoformat(timespec="seconds")}
    metadata = run_root / "run_metadata.txt"
    report["run_metadata"] = metadata.read_text() if metadata.is_file() else None
    if suite == "T1T2":
        workflow_list = WORKFLOWS
        groups = {test: [(label, None) for label in labels] for test, labels in TESTS.items()}
    elif suite == "T3":
        workflow_list, groups = T3_WORKFLOWS, T3_GROUPS
    else:
        raise ValueError(f"Unknown suite {suite!r}")
    workflows, runs = load_workflows(run_root, workflow_list)
    report["workflows"] = workflows

    reference_samples = None
    if reference_results is not None:
        sampling = sorted(reference_results.glob("*_sampling.hdf5"))
        sampling = [path for path in sampling if not path.name.endswith("_importance_sampling.hdf5")]
        if len(sampling) == 1:
            reference_samples = load_result(sampling[0])["samples"]
            report["reference_network_samples"] = str(sampling[0])
    tests = {}
    for test, members in groups.items():
        test_runs = group_runs(runs, members, workflows)
        if len(test_runs) >= 2:
            tests[test] = compare_test(
                test_runs, REFERENCES.get(test), reference_samples if test in REFERENCES else None
            )
    report["tests"] = tests
    if suite == "T3":
        both = ("T3c", 0) in runs and ("T3c", 1) in runs
        report["different_events"] = different_events(runs[("T3c", 0)], runs[("T3c", 1)]) if both else None
        report["earlier_gw150914"] = earlier_event_data(runs.get(("T3a", 0)), earlier_run_root)
        report["verdicts"] = verdicts_t3(report)
    else:
        report["verdicts"] = verdicts(report)
    return report


def different_events(first: dict, second: dict) -> dict:
    """Whether two events' event data and PSD files really differ."""
    data_differ = None
    if first["event_data"] is not None and second["event_data"] is not None:
        data_differ = event_data_digests(first["event_data"]) != event_data_digests(second["event_data"])
    psds_differ = None
    if first["psd_files"] and second["psd_files"]:
        psds_differ = {det: file_digest(p) for det, p in first["psd_files"].items()} != {
            det: file_digest(p) for det, p in second["psd_files"].items()
        }
    return {"runs": [first["name"], second["name"]], "event_data_differ": data_differ, "psd_files_differ": psds_differ}


def earlier_event_data(run: Optional[dict], earlier_run_root: Optional[Path]) -> Optional[dict]:
    """GW150914's event data against T1a's from the first launch, before the fixes."""
    if run is None or earlier_run_root is None or run["event_data"] is None:
        return None
    earlier = event_data_files(earlier_run_root / "T1" / "T1a" / "data", "T1a").get(0, [])
    if len(earlier) != 1:
        return {"identical": None, "earlier": str(earlier_run_root)}
    comparison = event_data_comparison(
        {run["name"]: event_data_digests(run["event_data"]), "T1a (first launch)": event_data_digests(earlier[0])}
    )
    comparison["earlier"] = str(earlier[0])
    return comparison


def complete_verdict(workflows: dict, labels) -> Tuple[bool, str]:
    counts = []
    problems = []
    for label in labels:
        completion = workflows[label]["completion"]
        nodes = (completion["dag"] or {}).get("nodes") or {}
        counts.append(f"{label} {nodes.get('done')} of {nodes.get('total')} nodes done")
        problems += [f"{label}: {problem}" for problem in completion["problems"]]
    passed = not problems
    detail = "; ".join(problems) if problems else "every event has its sampling and importance-sampling results and corner plot"
    return passed, ", ".join(counts) + "; " + detail


def shared_verdict(workflows: dict, label: str) -> Tuple[bool, str]:
    shared = workflows[label]["shared_outputs"]
    if shared["written_by_every_chain"]:
        return False, (
            f"{label}: Every event's jobs write {', '.join(shared['written_by_every_chain'])} under the "
            "same name, so the last to finish wins"
        )
    if not shared["passed"]:
        return False, f"{label}: Events with outputs {shared['events_with_outputs']}, or their outputs differ"
    return True, f"{label}: Every output names its event"


def agreement_verdict(comparison: Optional[dict]) -> Tuple[bool, str, bool]:
    """(passed, evidence, needs a check) for a test's agreement criterion."""
    if comparison is None:
        return False, "Fewer than two runs have results", False
    ks, evidence, data = comparison["network_ks"], comparison["evidence"], comparison["event_data"]
    worst_z = max((row["z"] for row in evidence["rows"]), default=0.0)
    if comparison["evidence_meaningful"]:
        evidence_text = f"log evidence: largest disagreement {worst_z:.2f} sigma (limit {N_SIGMA:g})"
    else:
        evidence_text = f"log evidence not compared, since a run has fewer than {MIN_N_EFF:g} effective samples"
    if data["identical"]:
        data_text = "event data bit-identical across runs"
    elif data["identical"] is None:
        data_text = f"event data not compared: No single event data file for {', '.join(data['missing'])}"
    else:
        data_text = f"event data DIFFER between runs in {', '.join(data['differing'])}"
    passed = (
        ks["passed"]
        and (evidence["passed"] or not comparison["evidence_meaningful"])
        and data["identical"] is not False
    )
    check = data["identical"] is None or bool(comparison["efficiency_outside_reference_factor"])
    return passed, (
        f"Network samples: smallest KS p-value {ks['worst']['p_value']:.3g} ({ks['worst']['parameter']}, "
        f"{' vs '.join(ks['worst']['pair'])}) against a threshold of {ks['threshold']:.3g} over "
        f"{ks['tests']} tests; {evidence_text}; {data_text}"
    ), check


def verdicts(report: dict) -> List[dict]:
    """A verdict on each pass criterion in test_log.md, numbered as there."""
    workflows, tests = report["workflows"], report["tests"]
    rows = []

    def add(criterion, verdict):
        passed, evidence = verdict[0], verdict[1]
        check = verdict[2] if len(verdict) > 2 else False
        rows.append({"criterion": criterion, "passed": passed, "check": check, "evidence": evidence})

    add("T1.1 T1b builds two complete chains, and every job finishes", complete_verdict(workflows, TESTS["T1"]))
    add("T1.2 No output file is written by more than one chain", shared_verdict(workflows, "T1b"))
    add("T1.3 The T1b copies agree with each other and with T1a", agreement_verdict(tests.get("T1")))
    add("T2.1 T2b builds three complete chains, and every job finishes", complete_verdict(workflows, TESTS["T2"]))
    passed, text, check = agreement_verdict(tests.get("T2"))
    if tests.get("T2"):
        efficiencies = ", ".join(
            f"{name} {100 * summary['sample_efficiency']:.2f}%" for name, summary in tests["T2"]["importance"].items()
        )
        reference = tests["T2"]["reference"]
        text += (
            f"; log evidence compared with {reference['name']}'s {reference['log_evidence']} +- "
            f"{reference['log_evidence_std']} too; sample efficiencies {efficiencies} (reference "
            f"{100 * reference['sample_efficiency']:.2f}%)"
        )
        outside = tests["T2"]["efficiency_outside_reference_factor"]
        if outside:
            text += (
                f"; CHECK: {', '.join(outside)} outside a factor of {EFFICIENCY_FACTOR:g} of the reference's "
                "efficiency (see Weights)"
            )
    add("T2.2 All four runs agree with the Exercise 3 reference", (passed, text, check))
    timing_complete = all(workflows[label]["timing"]["complete"] for labels in TESTS.values() for label in labels)
    add(
        "T2.3 Timing recorded for every job",
        (
            timing_complete,
            "Every job's queue wait, transfers, run time and CPU read from its Condor log"
            if timing_complete
            else "Some job has no successful run in its Condor log",
        ),
    )
    add("Also: No output file is written by more than one chain (T1.2's check on T2b)", shared_verdict(workflows, "T2b"))
    return rows


def verdicts_t3(report: dict) -> List[dict]:
    """A verdict on each T3 criterion in test_log.md."""
    workflows, tests = report["workflows"], report["tests"]
    rows = []

    def add(criterion, passed, evidence, check=False):
        rows.append({"criterion": criterion, "passed": passed, "check": check, "evidence": evidence})

    add("T3.1 Every chain completes", *complete_verdict(workflows, ("T3a", "T3b", "T3c")))
    add("T3.2 No output file is written by more than one chain", *shared_verdict(workflows, "T3c"))
    for test in T3_GROUPS:
        comparison = tests.get(test)
        passed, text, check = agreement_verdict(comparison)
        if comparison is not None:
            psd = comparison["psd_files"]
            if psd["identical"]:
                text += "; PSD files byte-identical"
            elif psd["identical"] is None:
                text += f"; PSD files not compared: None found for {', '.join(psd['missing'])}"
                check = True
            else:
                text += f"; PSD files DIFFER for {', '.join(psd['differing'])}"
                passed = False
        add(f"T3.3 {test} in T3c matches its single-event run", passed, text, check)
    different = report.get("different_events")
    if different is None:
        add("T3.4 The two events' data really differ", False, "T3c lacks a run for one of its events")
    else:
        add(
            "T3.4 The two events' data really differ",
            different["event_data_differ"] is True and different["psd_files_differ"] is True,
            f"{' vs '.join(different['runs'])}: event data differ: {different['event_data_differ']}, "
            f"PSD files differ: {different['psd_files_differ']}",
        )
    timing_complete = all(workflows[label]["timing"]["complete"] for label in ("T3a", "T3b", "T3c"))
    add(
        "T3.5 Timing recorded for every job",
        timing_complete,
        "From each job's Condor log" if timing_complete else "Some job has no successful run in its Condor log",
    )
    earlier = report.get("earlier_gw150914")
    if earlier is not None:
        criterion = "Also: GW150914's event data match T1a's from the first launch"
        if earlier["identical"] is None:
            add(criterion, True, f"Not compared: No T1a event data under {earlier['earlier']}", check=True)
        elif earlier["identical"]:
            add(criterion, True, "Bit-identical, so the fixes leave data handling unchanged")
        else:
            add(criterion, False, f"DIFFER in {', '.join(earlier['differing'])}")
    return rows


# -- Report -------------------------------------------------------------------


def duration(seconds: Optional[float]) -> str:
    if seconds is None or (isinstance(seconds, float) and math.isnan(seconds)):
        return "n/a"
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def number(value, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:.{digits}g}"


def verdict_word(row: dict) -> str:
    if not row["passed"]:
        return "FAIL"
    return "CHECK" if row.get("check") else "PASS"


def render_markdown(report: dict) -> str:
    lines = ["# Option A results", "", f"Analysed {report['analysed']} from `{report['run_root']}`.", ""]
    if report.get("run_metadata"):
        lines += ["```", report["run_metadata"].strip(), "```", ""]
    lines += [
        "## Verdicts",
        "",
        "CHECK means the test passed but something needs a look before calling it a pass.",
        "",
        "| Criterion | Verdict | Evidence |",
        "|---|---|---|",
    ]
    for row in report["verdicts"]:
        lines.append(f"| {row['criterion']} | {verdict_word(row)} | {row['evidence']} |")
    for test, comparison in report["tests"].items():
        ks = comparison["network_ks"]
        lines += [
            "",
            f"## {test}: Agreement between runs",
            "",
            f"Network samples, two-sample KS per parameter: {ks['tests']} tests over "
            f"{len(ks['runs'])} runs, Bonferroni threshold {ks['threshold']:.3g} "
            f"({ks['alpha']:g} family-wise). Smallest p-value per pair:",
            "",
            "| Pair | Smallest p | Parameter | KS statistic |",
            "|---|---|---|---|",
        ]
        for pair in itertools.combinations(ks["runs"], 2):
            pair_rows = [row for row in ks["rows"] if row["pair"] == list(pair)]
            worst = min(pair_rows, key=lambda row: row["p_value"])
            lines.append(
                f"| {' vs '.join(pair)} | {worst['p_value']:.3g} | {worst['parameter']} | {worst['statistic']:.4f} |"
            )
        if ks["identical_pairs"]:
            lines += ["", f"Identical network samples (a fixed seed?): {ks['identical_pairs']}"]
        if "network_ks_with_reference_error" in comparison:
            lines += ["", f"{comparison['reference']['name']}'s own network samples could not be compared: "
                      f"{comparison['network_ks_with_reference_error']}"]
        if "network_ks_with_reference" in comparison:
            reference_ks = comparison["network_ks_with_reference"]
            lines += [
                "",
                f"Including {comparison['reference']['name']}'s own network samples: smallest p-value "
                f"{reference_ks['worst']['p_value']:.3g} ({reference_ks['worst']['parameter']}, "
                f"{' vs '.join(reference_ks['worst']['pair'])}), threshold {reference_ks['threshold']:.3g}.",
            ]
        lines += ["", "| Run | ln Z | sigma | Effective samples | Efficiency |", "|---|---|---|---|---|"]
        for name, summary in comparison["importance"].items():
            lines.append(
                f"| {name} | {summary['log_evidence']:.3f} | {summary['log_evidence_std']:.3f} | "
                f"{summary['n_eff']:.1f} of {summary['samples']} | {100 * summary['sample_efficiency']:.2f}% |"
            )
        reference = comparison["reference"]
        if reference:
            lines.append(
                f"| {reference['name']} (reference) | {reference['log_evidence']:.3f} | "
                f"{reference['log_evidence_std']:.3f} | | {100 * reference['sample_efficiency']:.2f}% |"
            )
        lines += ["", "| Pair | Difference in ln Z | Combined sigma | Disagreement (sigma) |", "|---|---|---|---|"]
        for row in comparison["evidence"]["rows"]:
            lines.append(
                f"| {' vs '.join(row['pair'])} | {row['difference']:+.3f} | {row['combined_std']:.3f} | {row['z']:.2f} |"
            )
        data = comparison["event_data"]
        if data["identical"]:
            data_text = "bit-identical across " + ", ".join(data["runs"])
        elif data["identical"] is None:
            data_text = "not compared, as there's no single event data file for " + ", ".join(data["missing"])
        else:
            data_text = "DIFFERENT between runs, in " + ", ".join(data["differing"])
        lines += [
            "",
            f"Event data (SHA-256 of every dataset in each event data file's data group): {data_text}.",
            "",
            "### Weights",
            "",
            "In units of each run's mean weight. A few heavy samples (a proposal missing part of the "
            "posterior) drag the efficiency down on their own; removing the heaviest then restores much of it.",
            "",
            "| Run | Efficiency | Largest weight | Share of the 10 largest | Efficiency without the heaviest | Zero weights |",
            "|---|---|---|---|---|---|",
        ]
        for name, diagnostics in comparison["weights"].items():
            lines.append(
                f"| {name} | {100 * comparison['importance'][name]['sample_efficiency']:.2f}% | "
                f"{diagnostics['largest_weight']:.4g} | {100 * diagnostics['top_10_share']:.2f}% | "
                f"{100 * diagnostics['efficiency_without_heaviest']:.2f}% | {diagnostics['zero_weights']} |"
            )
        names = list(comparison["weights"])
        columns = list(next(iter(comparison["weights"].values()))["heaviest_sample"])
        lines += [
            "",
            "The heaviest sample of each run:",
            "",
            "| Column | " + " | ".join(names) + " |",
            "|---" * (len(names) + 1) + "|",
        ]
        for column in columns:
            cells = [number(comparison["weights"][name]["heaviest_sample"].get(column), 6) for name in names]
            lines.append(f"| {column} | " + " | ".join(cells) + " |")
        names = list(comparison["importance"])
        lines += [
            "",
            "Weighted median [5%, 95%] of every parameter after importance sampling:",
            "",
            "| Parameter | " + " | ".join(names) + " |",
            "|---" * (len(names) + 1) + "|",
        ]
        for parameter, values in comparison["posteriors"].items():
            cells = [
                f"{number(values[name][1], 4)} [{number(values[name][0], 4)}, {number(values[name][2], 4)}]"
                if name in values
                else "n/a"
                for name in names
            ]
            lines.append(f"| {parameter} | " + " | ".join(cells) + " |")
    lines += ["", "## Timing", ""]
    for label, workflow in report["workflows"].items():
        timing = workflow["timing"]
        if timing["complete"]:
            chains = ", ".join(f"event {event} {duration(s)}" for event, s in timing["chain_s"].items())
            lines += [
                f"**{label}** ({workflow['events']} event(s)): Wall time {duration(timing['makespan_s'])} "
                f"from first submission to last job; per event: {chains}. CPU {timing['cpu_hours']:.2f} h, "
                f"wasted on failed attempts {timing['wasted_cpu_hours']:.2f} h.",
                "",
            ]
        lines += [
            "| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | "
            "Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for row in workflow["jobs"]:
            disk_used = row["disk_used_kb"] / 1024**2 if row["disk_used_kb"] is not None else None
            disk_requested = row["disk_requested_kb"] / 1024**2 if row["disk_requested_kb"] is not None else None
            received = row["bytes_received"] / 1e9 if row["bytes_received"] is not None else None
            lines.append(
                f"| {row['job']} | {duration(row['wait_s'])} | {duration(row['input_transfer_s'])} | "
                f"{duration(row['run_s'])} | {duration(row['output_transfer_s'])} | {duration(row['cpu_s'])} | "
                f"{number(row['cores_used'], 2)} / {number(row['cores_requested'], 3)} | "
                f"{number(row['memory_used_mb'], 4)} / {number(row['memory_requested_mb'], 5)} | "
                f"{number(disk_used, 2)} / {number(disk_requested, 3)} | {number(received, 3)} | {row['attempts']} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def to_json(value):
    """Make the report JSON-serialisable."""
    if isinstance(value, dict):
        return {str(key): to_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_root", type=Path, help="The option A run folder (with T1/ and T2/).")
    parser.add_argument("output", type=Path, help="Folder to write the summary and corner plots to.")
    parser.add_argument(
        "--reference-results",
        type=Path,
        help="Exercise 3's result folder, to compare its network samples with T2's as well.",
    )
    parser.add_argument("--suite", default="T1T2", choices=["T1T2", "T3"], help="Which tests the run folder holds.")
    parser.add_argument(
        "--earlier-run-root",
        type=Path,
        help="For T3: The first launch's run folder, to compare GW150914's event data with T1a's.",
    )
    args = parser.parse_args(argv)
    report = analyse(args.run_root, args.reference_results, args.suite, args.earlier_run_root)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(to_json(report), indent=2) + "\n")
    (args.output / "summary.md").write_text(render_markdown(report))
    plots = args.output / "corner_plots"
    plots.mkdir(exist_ok=True)
    for workflow in report["workflows"].values():
        for path in workflow["corner_plots"]:
            shutil.copy2(path, plots / Path(path).name)
    for row in report["verdicts"]:
        print(f"{verdict_word(row)}  {row['criterion']}: {row['evidence']}")
    print(f"Written: {args.output / 'summary.md'}, summary.json and corner_plots/")


if __name__ == "__main__":
    main()
