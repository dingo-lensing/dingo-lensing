"""Gather a finished step 2.1 baseline job into results/baseline/<run>/ and summarise it.

    python3 collect_baseline.py RUN_DIR

Copies the job's report (out/baseline.json), its Condor log and its stdout and
stderr, and writes summary.json, which adds Condor's view: Queue wait, input
transfer, run time, CPU time, cores used and the job's peak memory. The two HDF5
results stay in RUN_DIR/out (too big to push).

Standard library only; reads the Condor log with ../../parallelisation/option_a/condor_logs.py.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SPEEDUPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPEEDUPS.parent / "parallelisation" / "option_a"))

from condor_logs import job_timing, read_events  # noqa: E402

COPIED = ("baseline.log", "baseline.out", "baseline.err", "baseline.sub", "launch.json")


def summarise(run_dir: Path) -> dict:
    report_path = run_dir / "out" / "baseline.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else None
    log = run_dir / "baseline.log"
    timing = job_timing(read_events(log)) if log.is_file() else None
    condor = None
    if timing is not None:
        # Condor names the row "Memory (MB)".
        memory = next((row for key, row in timing.resources.items() if key.startswith("Memory")), {})
        condor = {
            "succeeded": timing.succeeded,
            "return_value": timing.return_value,
            "attempts": timing.attempts,
            "host": timing.host,
            "wait_seconds": timing.wait_seconds,
            "input_transfer_seconds": timing.input_seconds,
            "run_seconds": timing.run_seconds,
            "output_transfer_seconds": timing.output_seconds,
            "cpu_seconds": timing.cpu_seconds,
            "cores_used": timing.cores_used,
            "memory_usage_mb": memory.get("Usage"),
            "memory_request_mb": memory.get("Request"),
            "bytes_received": timing.bytes_received,
        }
    summary = {"run": run_dir.name, "condor": condor}
    if report is not None:
        summary["error"] = report.get("error")
        summary["evidence"] = report.get("evidence")
        summary["total_seconds"] = report.get("total_seconds")
        summary["stage_seconds"] = {k: v.get("seconds") for k, v in report.get("stages", {}).items()}
        summary["synthetic_phase_parts"] = report.get("synthetic_phase_parts")
        summary["job_peak_bytes"] = report.get("job_peak_bytes")
        summary["host_cpu"] = (report.get("provenance") or {}).get("host", {}).get("cpu")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--results", type=Path, default=SPEEDUPS / "results" / "baseline")
    args = parser.parse_args(argv)
    run_dir = args.run_dir.expanduser().resolve()
    if not run_dir.is_dir():
        print(f"ERROR: {run_dir} is not a folder", file=sys.stderr)
        return 1
    destination = args.results / run_dir.name
    destination.mkdir(parents=True, exist_ok=True)
    for name in COPIED:
        if (run_dir / name).is_file():
            shutil.copy2(run_dir / name, destination / f"{name}.txt" if name.endswith(".log") else destination / name)
    if (run_dir / "out" / "baseline.json").is_file():
        shutil.copy2(run_dir / "out" / "baseline.json", destination / "baseline.json")
    summary = summarise(run_dir)
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nWritten to {destination}")
    return 0 if summary.get("condor") and summary["condor"]["succeeded"] and not summary.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
