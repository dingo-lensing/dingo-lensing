"""Show how an xphm_job.py job went: Each task's verdict, and the end of the output of those that did not pass.

    python3 show_job.py OUT_DIR [--lines 30]

OUT_DIR is a job's out/ folder (or a pre-flight's copy of it). launch_xphm_tests.sh runs this on
every pre-flight that fails. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List


def describe(out: Path, lines: int = 30) -> List[str]:
    report_path = out / "job.json"
    if not report_path.is_file():
        return [f"{out}: No job.json, so the job did not start"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    text = [f"{report.get('job')} on {report.get('host')}: exit {report.get('exit_code')}"]
    if report.get("error"):
        text += [f"  job error: {report['error']}", *report.get("traceback", "").splitlines()[-lines:]]
    for name, record in report.get("tasks", {}).items():
        reason = record.get("error") or record.get("reason") or ""
        text.append(f"  {name}: {record.get('verdict')}, exit {record.get('exit_code')}, {record.get('seconds')} s {reason}".rstrip())
    for name, record in report.get("tasks", {}).items():
        output = out / name / "output.txt"
        if record.get("verdict") != "passed" and output.is_file():
            text.append(f"  --- the end of {name}'s output")
            text += ["    " + line for line in output.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]]
    return text


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--lines", type=int, default=30)
    args = parser.parse_args(argv)
    print("\n".join(describe(args.out, args.lines)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
