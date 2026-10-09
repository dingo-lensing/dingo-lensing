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
# Kaili's local Exercise 3 run (tutorial_reference/ex3_dingo_lensing_application/ex3_local.log).
REFERENCES = {
    "T2": {"name": "Exercise 3", "log_evidence": -5829.945, "log_evidence_std": 0.014, "sample_efficiency": 0.0940}
}
ALPHA = 0.01
N_SIGMA = 3.0
MIN_N_EFF = 100.0
NOT_PARAMETERS = {"log_prob", "log_likelihood", "log_prior", "delta_log_prob_target", "weights"}
RESULT_FILE = re.compile(
    r"^(?P<label>.+)_data(?P<event>\d+)_[0-9-]+_(?P<kind>sampling|importance_sampling)\.hdf5$"
)
CORNER_PLOT = re.compile(r"^(?P<label>.+)_data(?P<event>\d+)_[0-9-]+_importance_sampling_plot_corner\.pdf$")
EVENT_INDEX = re.compile(r"_data(\d+)_")


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
            per_event.setdefault(int(match.group(1)), set()).add(EVENT_INDEX.sub("_data<i>_", relative))
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
    comparison = {
        "network_ks": ks_comparison(network),
        "importance": importance,
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


def analyse(run_root: Path, reference_results: Optional[Path] = None) -> dict:
    report = {"run_root": str(run_root), "analysed": datetime.now().isoformat(timespec="seconds")}
    metadata = run_root / "run_metadata.txt"
    report["run_metadata"] = metadata.read_text() if metadata.is_file() else None
    workflows = {}
    runs: Dict[str, Dict[str, dict]] = {test: {} for test in TESTS}
    for label, folder, config_name, events in WORKFLOWS:
        run_dir = run_root / folder
        outdir = run_dir / read_pipe_ini(run_dir / config_name)["outdir"]
        rows = job_rows(run_dir, outdir)
        workflows[label] = {
            "events": events,
            "completion": completion(outdir, label, events),
            "shared_outputs": shared_outputs(outdir, events),
            "jobs": rows,
            "timing": workflow_timing(rows),
            "corner_plots": [
                str(paths[0])
                for kinds in result_files(outdir / "result", label).values()
                for kind, paths in kinds.items()
                if kind == "corner"
            ],
        }
        test = next(test for test, labels in TESTS.items() if label in labels)
        files = result_files(outdir / "result", label)
        for event in range(events):
            kinds = files.get(event, {})
            if len(kinds.get("sampling", [])) == 1 and len(kinds.get("importance_sampling", [])) == 1:
                runs[test][run_name(label, event, events)] = {
                    "network": load_result(kinds["sampling"][0]),
                    "posterior": load_result(kinds["importance_sampling"][0]),
                }
    report["workflows"] = workflows

    reference_samples = None
    if reference_results is not None:
        sampling = sorted(reference_results.glob("*_sampling.hdf5"))
        sampling = [path for path in sampling if not path.name.endswith("_importance_sampling.hdf5")]
        if len(sampling) == 1:
            reference_samples = load_result(sampling[0])["samples"]
            report["reference_network_samples"] = str(sampling[0])
    report["tests"] = {
        test: compare_test(
            test_runs,
            REFERENCES.get(test),
            reference_samples if test in REFERENCES else None,
        )
        for test, test_runs in runs.items()
        if len(test_runs) >= 2
    }
    report["verdicts"] = verdicts(report)
    return report


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


def agreement_verdict(comparison: Optional[dict]) -> Tuple[bool, str]:
    if comparison is None:
        return False, "Fewer than two runs have results"
    ks, evidence = comparison["network_ks"], comparison["evidence"]
    worst_z = max((row["z"] for row in evidence["rows"]), default=0.0)
    if comparison["evidence_meaningful"]:
        evidence_text = f"log evidence: largest disagreement {worst_z:.2f} sigma (limit {N_SIGMA:g})"
    else:
        evidence_text = f"log evidence not compared, since a run has fewer than {MIN_N_EFF:g} effective samples"
    passed = ks["passed"] and (evidence["passed"] or not comparison["evidence_meaningful"])
    return passed, (
        f"Network samples: smallest KS p-value {ks['worst']['p_value']:.3g} ({ks['worst']['parameter']}, "
        f"{' vs '.join(ks['worst']['pair'])}) against a threshold of {ks['threshold']:.3g} over "
        f"{ks['tests']} tests; {evidence_text}"
    )


def verdicts(report: dict) -> List[dict]:
    """A verdict on each pass criterion in test_log.md, numbered as there."""
    workflows, tests = report["workflows"], report["tests"]
    rows = []

    def add(criterion, verdict):
        rows.append({"criterion": criterion, "passed": verdict[0], "evidence": verdict[1]})

    add("T1.1 T1b builds two complete chains, and every job finishes", complete_verdict(workflows, TESTS["T1"]))
    add("T1.2 No output file is written by more than one chain", shared_verdict(workflows, "T1b"))
    add("T1.3 The T1b copies agree with each other and with T1a", agreement_verdict(tests.get("T1")))
    add("T2.1 T2b builds three complete chains, and every job finishes", complete_verdict(workflows, TESTS["T2"]))
    passed, text = agreement_verdict(tests.get("T2"))
    if tests.get("T2"):
        efficiencies = ", ".join(
            f"{name} {100 * summary['sample_efficiency']:.2f}%" for name, summary in tests["T2"]["importance"].items()
        )
        reference = tests["T2"]["reference"]
        text += (
            f", including {reference['name']}'s {reference['log_evidence']} +- {reference['log_evidence_std']}; "
            f"sample efficiencies {efficiencies} (reference {100 * reference['sample_efficiency']:.2f}%)"
        )
    add("T2.2 All four runs agree with the Exercise 3 reference", (passed, text))
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


def render_markdown(report: dict) -> str:
    lines = ["# Option A results", "", f"Analysed {report['analysed']} from `{report['run_root']}`.", ""]
    if report.get("run_metadata"):
        lines += ["```", report["run_metadata"].strip(), "```", ""]
    lines += ["## Verdicts", "", "| Criterion | Verdict | Evidence |", "|---|---|---|"]
    for row in report["verdicts"]:
        lines.append(f"| {row['criterion']} | {'PASS' if row['passed'] else 'FAIL'} | {row['evidence']} |")
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
    args = parser.parse_args(argv)
    report = analyse(args.run_root, args.reference_results)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(to_json(report), indent=2) + "\n")
    (args.output / "summary.md").write_text(render_markdown(report))
    plots = args.output / "corner_plots"
    plots.mkdir(exist_ok=True)
    for workflow in report["workflows"].values():
        for path in workflow["corner_plots"]:
            shutil.copy2(path, plots / Path(path).name)
    for row in report["verdicts"]:
        print(f"{'PASS' if row['passed'] else 'FAIL'}  {row['criterion']}: {row['evidence']}")
    print(f"Written: {args.output / 'summary.md'}, summary.json and corner_plots/")


if __name__ == "__main__":
    main()
