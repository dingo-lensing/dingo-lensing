"""Gather the end-to-end test of the multi-phase XPHM route into results/ and judge it.

    python3 collect_xphm_tests.py RUN_DIR

Copies each job's reports to results/xphm_end_to_end/<run>/ (not the HDF5 results, which stay in
RUN_DIR), writes summary.json and summary.txt, and prints the second. A job that has not finished
shows up as a problem, and running this again later picks it up.

The verdict needs: Every job finished; on both ladders, every setup ran on the route it should,
and the comparisons that must agree do; the stress test found no failures and lost no chunks to a
crash; and the DINGO suite fails only where upstream main does, with the same outcomes on both LALs
but for the one test that needs the patched LAL. Timings are reported, not judged.

The time per injection comes from the full job's script times plus the job start-up and input
transfer the 2.1 run measured, times 32 cores and two models.

Exit code 0 if the verdict is a pass, 1 otherwise. Standard library only; reads Condor logs with
../baseline/collect_baseline.py.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional
from xml.etree import ElementTree

SPEEDUPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPEEDUPS / "baseline"))

from collect_baseline import condor_record  # noqa: E402

GIGA = 1e9
OVERHEAD_SECONDS = 87 + 29  # 2.1: Job and container start-up, and input transfer
CORES = 32
MODELS_PER_INJECTION = 2
CORE_HOURS_PER_WEEK_AT_500_CORES = 500 * 168
# 2.1 (node798): The whole script and its synthetic phase, in seconds.
BASELINE_SCRIPT_SECONDS = 307.342
BASELINE_SYNTHETIC_SECONDS = 222.673
LADDERS = ("ladder_forward", "ladder_reverse")
REFERENCE_SETUPS = ("upstream_release", "full_upstream_release")
# They fail on upstream main 471de26e too, with the same errors (see the test log, 2 November).
KNOWN_FAILURES = {
    "tests.core.test_compile.TestResetGraphsOnRequiresGradChange.test_unfreeze_without_reset_gives_no_gradient",
    "tests.gw.waveform_generator.test_wfg_tidal.test_tidal_prior_defaults"
}
NEEDS_PATCHED_LAL = {
    "tests.gw.waveform_generator.test_wfg_m.test_lalsimulation_multi_phase_matches_repeated_calls[IMRPhenomXPHM]"
}


def read_json(path: Path) -> Optional[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def tail(path: Path, lines: int = 200) -> str:
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]) + "\n"


def part_seconds(parts: dict, *labels: str) -> float:
    return round(sum((parts.get(label) or {}).get("seconds", 0.0) for label in labels), 3)


def setup_row(baseline: dict) -> dict:
    """One importance-sampling task's times, memory, evidence and route, from its baseline.json."""
    stages = baseline.get("stages", {})
    parts = baseline.get("synthetic_phase_parts") or {}
    route = baseline.get("route") or {}
    calls = route.get("calls", {})
    return {
        "error": baseline.get("error"),
        "total_seconds": baseline.get("total_seconds"),
        "stage_seconds": {name: stage.get("seconds") for name, stage in stages.items()},
        "synthetic_phase_seconds": stages.get("synthetic_phase", {}).get("seconds"),
        "per_sample_seconds": part_seconds(parts, "per_sample_terms_in_workers"),
        "grid_seconds": part_seconds(parts, "grid_evaluation_in_main", "floor_in_main", "grid_and_floor_in_workers"),
        "draw_seconds": part_seconds(parts, "draws"),
        "main_peak_gb": (stages.get("synthetic_phase", {}).get("main_peak_bytes") or 0) / GIGA,
        "children_peak_gb": (baseline.get("children_peak_bytes") or 0) / GIGA,
        "evidence": baseline.get("evidence"),
        "network_sampling_seconds": stages.get("network_sampling", {}).get("seconds"),
        "torch_threads": baseline.get("torch_threads"),
        "lal_file": (baseline.get("lal") or {}).get("file"),
        "single_calls": calls.get("SimInspiralFD", 0),
        "multi_phase_calls": calls.get("SimInspiralFDMultiPhase", 0)
    }


def comparison_row(compare: dict) -> dict:
    """The largest differences of a compare_results.py report."""
    columns = compare.get("columns", {})
    worst_rel = max(columns, key=lambda name: columns[name]["max_rel"], default=None)
    worst_abs = max(columns, key=lambda name: columns[name]["max_abs"], default=None)
    evidence = compare.get("summary", {}).get("log_evidence", [0.0, 0.0])
    return {
        "agrees": compare.get("identical_to_rtol"),
        "rtol": compare.get("rtol"),
        "atol": compare.get("atol"),
        "max_rel": columns[worst_rel]["max_rel"] if columns else None,
        "max_rel_column": worst_rel,
        "max_abs": columns[worst_abs]["max_abs"] if columns else None,
        "max_abs_column": worst_abs,
        "nonfinite_mismatch": sum(column["nonfinite_mismatch"] for column in columns.values()),
        "log_evidence_difference": abs(evidence[0] - evidence[1])
    }


def junit_outcomes(path: Path) -> Dict[str, str]:
    outcomes = {}
    for case in ElementTree.parse(path).getroot().iter("testcase"):
        test = f"{case.get('classname')}.{case.get('name')}"
        if case.find("failure") is not None:
            outcomes[test] = "failed"
        elif case.find("error") is not None:
            outcomes[test] = "error"
        elif case.find("skipped") is not None:
            outcomes[test] = "skipped"
        else:
            outcomes[test] = "passed"
    return outcomes


def outcome_counts(outcomes: Dict[str, str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for outcome in outcomes.values():
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def suite_comparison(release: Dict[str, str], patched: Dict[str, str]) -> dict:
    """Which tests fail beyond the known ones, and which tests differ between the two LALs."""
    def unexpected(outcomes):
        return sorted(test for test, outcome in outcomes.items() if outcome in ("failed", "error") and test not in KNOWN_FAILURES)

    differing = {
        test: [release.get(test), patched.get(test)]
        for test in sorted(set(release) | set(patched))
        if release.get(test) != patched.get(test) and test not in NEEDS_PATCHED_LAL
    }
    return {
        "release": outcome_counts(release),
        "patched": outcome_counts(patched),
        "unexpected_failures_release": unexpected(release),
        "unexpected_failures_patched": unexpected(patched),
        "differing": differing,
        "patched_lal_test": {test: patched.get(test) for test in NEEDS_PATCHED_LAL}
    }


def injection_cost(reference_seconds: float, new_seconds: float) -> dict:
    """Core-hours per injection and injections a week, from two full jobs' script times."""
    def core_hours(seconds):
        return (seconds + OVERHEAD_SECONDS) * CORES * MODELS_PER_INJECTION / 3600

    before, after = core_hours(reference_seconds), core_hours(new_seconds)
    return {
        "core_hours_before": before,
        "core_hours_after": after,
        "speedup": before / after,
        "injections_per_week_before": CORE_HOURS_PER_WEEK_AT_500_CORES / before,
        "injections_per_week_after": CORE_HOURS_PER_WEEK_AT_500_CORES / after
    }


def injection_cost_on_baseline(speedup: float) -> dict:
    """injection_cost on 2.1's stages, with its synthetic phase sped up by a measured factor. The full
    job's own other stages depend on more than this work: Its network sampling took 845 to 945 s
    with torch on 32 threads on a busy node, against 64 s on 24 in 2.1."""
    return injection_cost(BASELINE_SCRIPT_SECONDS, BASELINE_SCRIPT_SECONDS - BASELINE_SYNTHETIC_SECONDS * (1 - 1 / speedup))


def collect_job(run_dir: Path, destination: Path, job: str) -> dict:
    """Copy one job's reports and summarise them."""
    job_dir = run_dir / job
    out = job_dir / "out"
    target = destination / job
    target.mkdir(parents=True, exist_ok=True)
    for file_name, copy_name in (("job.sub", "job.sub"), ("job.log", "job.log.txt"), ("manifest.json", "manifest.json")):
        if (job_dir / file_name).is_file():
            shutil.copy2(job_dir / file_name, target / copy_name)
    report = read_json(out / "job.json")
    summary = {"condor": condor_record(job_dir / "job.log"), "finished": report is not None and "exit_code" in report, "tasks": {}}
    if report is None:
        return summary
    shutil.copy2(out / "job.json", target / "job.json")
    summary["host"] = report.get("host")
    summary["order"] = report.get("order")
    summary["error"] = report.get("error")
    for task, record in report.get("tasks", {}).items():
        task_out, task_target = out / task, target / task
        task_target.mkdir(exist_ok=True)
        task_summary = {key: record.get(key) for key in ("kind", "verdict", "must_pass", "exit_code", "seconds", "error", "reason")}
        for file_name in ("baseline.json", "compare.json", "stress.json", "junit.xml"):
            if (task_out / file_name).is_file():
                shutil.copy2(task_out / file_name, task_target / file_name)
        if record.get("verdict") != "passed" and (task_out / "output.txt").is_file():
            (task_target / "output_tail.txt").write_text(tail(task_out / "output.txt"), encoding="utf-8")
        baseline = read_json(task_out / "baseline.json")
        if baseline is not None:
            task_summary["setup"] = setup_row(baseline)
            cpu = ((baseline.get("provenance") or {}).get("host") or {}).get("cpu") or {}
            summary["cpu"] = cpu.get("model")
        compare = read_json(task_out / "compare.json")
        if compare is not None:
            task_summary["comparison"] = comparison_row(compare)
        stress = read_json(task_out / "stress.json")
        if stress is not None:
            task_summary["stress"] = stress
        summary["tasks"][task] = task_summary
    return summary


def add_speedups(job: dict) -> None:
    """Each setup's speed-up on one node, against the reference setup."""
    setups = {name: task["setup"] for name, task in job["tasks"].items() if "setup" in task}
    reference = next((setups[name] for name in REFERENCE_SETUPS if name in setups), None)
    if not reference or not reference.get("synthetic_phase_seconds"):
        return
    for setup in setups.values():
        if setup.get("synthetic_phase_seconds"):
            setup["synthetic_phase_speedup"] = reference["synthetic_phase_seconds"] / setup["synthetic_phase_seconds"]
        if setup.get("per_sample_seconds"):
            setup["per_sample_speedup"] = reference["per_sample_seconds"] / setup["per_sample_seconds"]


def judge(jobs: Dict[str, dict], suites: Optional[dict]) -> List[str]:
    """Everything that keeps the test from passing."""
    problems = []
    for name, job in jobs.items():
        if not job.get("finished"):
            problems.append(f"{name}: Not finished")
        if job.get("error"):
            problems.append(f"{name}: {job['error']}")
        for task, record in job.get("tasks", {}).items():
            if record.get("must_pass", True) and record.get("verdict") != "passed":
                problems.append(f"{name}: {task} {record.get('verdict')}: {record.get('error') or record.get('reason') or 'exit ' + str(record.get('exit_code'))}")
    stress = jobs.get("stress", {}).get("tasks", {}).get("stress", {}).get("stress")
    if stress is not None:
        if stress.get("failures"):
            problems.append(f"stress: {stress['failures']} failures")
        if stress.get("stalled"):
            problems.append(f"stress: Chunks lost, probably to a crash: {stress.get('chunks_missing')}")
        if stress.get("stopped_for_memory"):
            problems.append(f"stress: Stopped at its memory limit, with {stress.get('peak_total_resident_gb', 0):.1f} GB held")
    if suites is None:
        problems.append("suite: No junit report from both LALs")
    else:
        for key in ("unexpected_failures_release", "unexpected_failures_patched"):
            if suites[key]:
                problems.append(f"suite: {key}: {suites[key]}")
        if suites["differing"]:
            problems.append(f"suite: Outcomes differ between the LALs: {suites['differing']}")
        for test, outcome in suites["patched_lal_test"].items():
            if outcome != "passed":
                problems.append(f"suite: {test} is {outcome} on the patched LAL")
    return problems


def render_ladder(name: str, job: dict) -> List[str]:
    lines = [f"{name} on {job.get('host')}, {job.get('cpu')}"]
    lines.append(f"  {'setup':24s} {'synthetic':>10s} {'per-sample':>11s} {'grid':>7s} {'draws':>7s} {'main peak':>10s} {'worker peak':>12s} {'log evidence':>14s} {'single calls':>13s} {'one calls':>10s} {'speed-up':>9s}")
    for task in job.get("order") or []:
        record = job["tasks"].get(task, {})
        setup = record.get("setup")
        if setup is None:
            continue
        evidence = (setup.get("evidence") or {}).get("log_evidence")
        evidence_text = f"{evidence:.6f}" if evidence is not None else "n/a"
        speedup = setup.get("synthetic_phase_speedup")
        speedup_text = f"{speedup:.2f}x" if speedup else ""
        lines.append(
            f"  {task:24s} {setup.get('synthetic_phase_seconds') or 0:9.1f}s {setup['per_sample_seconds']:10.1f}s "
            f"{setup['grid_seconds']:6.1f}s {setup['draw_seconds']:6.1f}s {setup['main_peak_gb']:7.1f} GB {setup['children_peak_gb']:9.1f} GB "
            f"{evidence_text:>14s} {setup['single_calls']:13d} {setup['multi_phase_calls']:10d} {speedup_text:>9s}"
        )
    for task, record in job.get("tasks", {}).items():
        row = record.get("comparison")
        if row is None:
            continue
        label = "must agree" if record.get("must_pass") else "for scale"
        lines.append(
            f"  {task} ({label}): agrees {row['agrees']}, largest relative {row['max_rel']:.2e} ({row['max_rel_column']}), "
            f"absolute {row['max_abs']:.2e} ({row['max_abs_column']}), log evidence {row['log_evidence_difference']:.2e}"
        )
    return lines


def render(summary: dict) -> str:
    jobs = summary["jobs"]
    lines = [f"End-to-end test of the multi-phase XPHM route, run {summary['run']}", ""]
    for name in LADDERS:
        if name in jobs:
            lines += render_ladder(name, jobs[name]) + [""]
    full = jobs.get("full", {})
    if full.get("tasks"):
        lines += render_ladder("full", full)
    for task, record in full.get("tasks", {}).items():
        setup = record.get("setup") or {}
        if setup.get("network_sampling_seconds") is not None:
            lines.append(f"  {task}: network sampling {setup['network_sampling_seconds']:.0f} s on {setup.get('torch_threads')} torch threads (2.1: 64 s on 24)")
    cost = summary.get("injection_cost")
    if cost:
        lines.append(
            f"  Per injection (both models, 2.1's job overhead): {cost['core_hours_before']:.2f} to {cost['core_hours_after']:.2f} core-hours, "
            f"{cost['speedup']:.2f}x, {cost['injections_per_week_before']:.0f} to {cost['injections_per_week_after']:.0f} a week at 500 cores"
        )
    for name, cost in (summary.get("injection_cost_on_2_1") or {}).items():
        lines.append(
            f"  Per injection on 2.1's other stages, with {name}'s synthetic-phase speed-up: {cost['core_hours_before']:.2f} to {cost['core_hours_after']:.2f} core-hours, "
            f"{cost['speedup']:.2f}x, {cost['injections_per_week_before']:.0f} to {cost['injections_per_week_after']:.0f} a week at 500 cores"
        )
    lines.append("")
    stress = jobs.get("stress", {}).get("tasks", {}).get("stress", {}).get("stress")
    if stress:
        lines.append(f"stress on {jobs['stress'].get('host')}: {stress.get('seconds')} s, {stress.get('failures')} failures, {len(stress.get('chunks_missing') or [])} of {stress.get('chunks')} chunks missing")
        for kind, tally in stress.get("kinds", {}).items():
            lines.append(f"  {kind}: {tally['draws']} draws, {tally['outcomes']}, largest difference {tally['max_difference']:.2e}, speed-up of the sums {tally.get('speedup_of_sums', 0):.2f}x")
            if "worker_peak_mb" in tally:
                growth = tally.get("growth_kb_per_draw")
                growth_text = f", memory growth {growth:.2f} kB per draw after a worker's first chunk" if growth is not None else ""
                lines.append(f"    worker peak {tally['worker_peak_mb']:.0f} MB{growth_text}")
        if "peak_total_resident_gb" in stress:
            lines.append(f"  all processes together up to {stress['peak_total_resident_gb']:.1f} GB (shared pages counted per process)")
        lines.append("")
    suites = summary.get("suites")
    if suites:
        lines.append(f"DINGO suite: Release {suites['release']}; patched {suites['patched']}; differing {len(suites['differing'])}")
        lines.append("")
    problems = summary["problems"]
    lines.append("PASS" if not problems else f"NOT PASSED, {len(problems)} problems:")
    lines += [f"  {problem}" for problem in problems]
    return "\n".join(lines) + "\n"


def summarise(run_dir: Path, destination: Path, job_names: List[str]) -> dict:
    jobs = {job: collect_job(run_dir, destination, job) for job in job_names}
    for job in jobs.values():
        add_speedups(job)
    junits = [run_dir / job / "out" / job / "junit.xml" for job in ("suite_release", "suite_patched")]
    suites = None
    if all(path.is_file() for path in junits):
        suites = suite_comparison(junit_outcomes(junits[0]), junit_outcomes(junits[1]))
    full_tasks = jobs.get("full", {}).get("tasks", {})
    totals = [full_tasks.get(task, {}).get("setup", {}).get("total_seconds") for task in ("full_upstream_release", "full_combined_patched_one")]
    summary = {"run": run_dir.name, "jobs": jobs, "suites": suites}
    if all(totals):
        summary["injection_cost"] = injection_cost(*totals)
    speedups = {}
    for name in ("full", *LADDERS):
        for task, record in jobs.get(name, {}).get("tasks", {}).items():
            speedup = (record.get("setup") or {}).get("synthetic_phase_speedup")
            if task.endswith("combined_patched_one") and speedup:
                speedups[name] = speedup
    if speedups:
        summary["injection_cost_on_2_1"] = {name: injection_cost_on_baseline(speedup) for name, speedup in speedups.items()}
    summary["problems"] = judge(jobs, suites)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--results", type=Path, default=SPEEDUPS / "results" / "xphm_end_to_end")
    args = parser.parse_args(argv)
    run_dir = args.run_dir.expanduser().resolve()
    jobs_file = run_dir / "jobs.txt"
    if not jobs_file.is_file():
        print(f"ERROR: {jobs_file} is missing", file=sys.stderr)
        return 1
    destination = args.results / run_dir.name
    destination.mkdir(parents=True, exist_ok=True)
    for file_name in ("launch.json", "lal_pack.json"):
        if (run_dir / file_name).is_file():
            shutil.copy2(run_dir / file_name, destination / file_name)
    summary = summarise(run_dir, destination, jobs_file.read_text(encoding="utf-8").split())
    text = render(summary)
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (destination / "summary.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"Written to {destination}")
    return 0 if not summary["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())
