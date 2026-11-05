"""Memory each route holds on to after a parameter set, set by set, on the stress test's own wide draws.

Runs in the environment build_lal.sh made, on one process, on an access point, with the stress job's allocator setting:

    MALLOC_MMAP_THRESHOLD_=131072 OMP_NUM_THREADS=1 ~/dingo-speedups-lal/env/bin/python -I memory_scan.py --manifest RUN_DIR/stress/manifest.json --output SCAN.jsonl

It replays the wide chunks among the first --first-chunks of the stress job's plan (the ones its runs reached), one parameter set at a time. For each set, and each route (nine XLALSimInspiralFD calls, then one XLALSimInspiralFDMultiPhase call), it reads the resident memory before the route, straight after it, and after gc and malloc_trim, and the route's own peak (VmHWM, reset before it). Memory still held after malloc_trim is held by something live: A leak, in LAL's own code if the single calls hold it too, in the new function if only the multi-phase call does. Memory held only until malloc_trim is the allocator's.

Each set's record is written as it goes, one JSON line, after a line naming the set, so a crash or the time limit loses nothing and a crash shows which set it was. The summary at the end ranks the sets and groups them by their settings. --render prints the summary of such a file again, also of one cut short:

    python3 -I memory_scan.py --render SCAN.jsonl
"""
from __future__ import annotations

import argparse
import ctypes
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional
import numpy as np

try:
    import resource
except ImportError:  # not on Windows
    resource = None

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from leak_check import call_route  # noqa: E402
from stress_multiphase import CHUNK_SIZES, DRAWS, KINDS, chunk_plan, lal_arguments  # noqa: E402

ROUTES = ("fd_single", "fd_multi")
HELD_MB = 1.0
TOP = 15


def status_kb(field: str) -> Optional[int]:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith(field + ":"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def reset_peak() -> None:
    try:
        Path("/proc/self/clear_refs").write_text("5", encoding="utf-8")
    except OSError:
        pass


def trim() -> None:
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def megabytes(after: Optional[int], before: Optional[int]) -> Optional[float]:
    if after is None or before is None:
        return None
    return (after - before) / 1024


def measure_route(run: Callable[[], None]) -> dict:
    trim()
    before = status_kb("VmRSS")
    reset_peak()
    error = None
    start = time.perf_counter()
    try:
        run()
    except Exception as exception:  # LAL's errors reach Python as several exception types
        error = str(exception)[:200]
    seconds = time.perf_counter() - start
    straight_after = status_kb("VmRSS")
    peak = status_kb("VmHWM")
    trim()
    after_trim = status_kb("VmRSS")
    return {
        "seconds": seconds,
        "error": error,
        "peak_mb": megabytes(peak, before),
        "held_mb": megabytes(straight_after, before),
        "held_after_trim_mb": megabytes(after_trim, before)
    }


def describe(draw: dict) -> dict:
    total = draw["m1"] + draw["m2"]
    return {
        "total_mass": total,
        "q": min(draw["m1"], draw["m2"]) / max(draw["m1"], draw["m2"]),
        "f_min": draw["f_min"],
        "f_ref": draw["f_ref"],
        "delta_f": draw["delta_f"],
        "f_max": draw["f_max"],
        "num_phases": draw["num_phases"],
        "dictionary": draw["dictionary"],
        "a_1": draw["a_1"],
        "a_2": draw["a_2"],
        "tilt_1": draw["tilt_1"],
        "tilt_2": draw["tilt_2"],
        "long_asc_nodes": draw["long_asc_nodes"]
    }


def setting(dictionary: dict) -> str:
    if not dictionary:
        return "default"
    key, value = next(iter(dictionary.items()))
    return key if key in ("modes", "prec_threshold", "mode_threshold") else f"{key} {value}"


def scan_plan(dingo_draws: int, wide_draws: int, seed: int, first_chunks: int) -> List[tuple]:
    """(chunk index, draw index in the chunk, draw) of the wide sets in the first chunks of the stress plan, in its order."""
    sets = []
    for kind, index, draws in chunk_plan(dingo_draws, wide_draws, seed)[:first_chunks]:
        if kind != "wide":
            continue
        rng = np.random.default_rng([seed, KINDS.index(kind), index])
        for position in range(draws):
            sets.append((index, position, DRAWS[kind](rng)))
    return sets


def held(record: dict, route: str) -> float:
    value = record[route]["held_after_trim_mb"]
    return value if value is not None else 0.0


def summarise(records: List[dict]) -> dict:
    summary = {"sets": len(records), "routes": {}, "groups": {}}
    for route in ROUTES:
        values = [held(record, route) for record in records]
        peaks = [record[route]["peak_mb"] for record in records if record[route]["peak_mb"] is not None]
        summary["routes"][route] = {
            "held_after_trim_mb": sum(value for value in values if value > 0),
            "sets_holding": sum(1 for value in values if value > HELD_MB),
            "largest_peak_mb": max(peaks) if peaks else None,
            "seconds": sum(record[route]["seconds"] for record in records),
            "errors": sum(1 for record in records if record[route]["error"])
        }
    for name, key in (("setting", lambda r: setting(r["draw"]["dictionary"])), ("f_min", lambda r: str(r["draw"]["f_min"])), ("errors", lambda r: "raised" if r["fd_single"]["error"] or r["fd_multi"]["error"] else "ran")):
        groups: Dict[str, dict] = {}
        for record in records:
            group = groups.setdefault(key(record), {"sets": 0, "seconds": 0.0, **{f"{route}_held_mb": 0.0 for route in ROUTES}, **{f"{route}_seconds": 0.0 for route in ROUTES}})
            group["sets"] += 1
            group["seconds"] += sum(record[route]["seconds"] for route in ROUTES)
            for route in ROUTES:
                group[f"{route}_held_mb"] += max(held(record, route), 0.0)
                group[f"{route}_seconds"] += record[route]["seconds"]
        summary["groups"][name] = groups
    summary["most_held"] = sorted(records, key=lambda r: -max(held(r, route) for route in ROUTES))[:TOP]
    summary["largest_peaks"] = sorted(records, key=lambda r: -max(r[route]["peak_mb"] or 0.0 for route in ROUTES))[:TOP]
    return summary


def one_line(record: dict) -> str:
    draw = record["draw"]
    routes = "  ".join(
        f"{route} held {record[route]['held_after_trim_mb'] or 0:8.1f} MB (before trim {record[route]['held_mb'] or 0:8.1f}) peak {record[route]['peak_mb'] or 0:8.1f} MB {record[route]['seconds']:7.2f} s{' raised' if record[route]['error'] else ''}"
        for route in ROUTES
    )
    settings = f"M {draw['total_mass']:7.2f} q {draw['q']:.3f} f_min {draw['f_min']:4.0f} f_ref {draw['f_ref']:4.0f} df {draw['delta_f']:.4f} f_max {draw['f_max']:4.0f} n {draw['num_phases']:2d} {setting(draw['dictionary'])}"
    return f"  chunk {record['chunk']:4d}.{record['position']:02d}  {settings}\n      {routes}"


def render(summary: dict, header: dict) -> str:
    lines = [f"LAL {header['lal']}, lalsimulation {header['lalsimulation']}, default PrecVersion {header['default_prec_version']}, MALLOC_MMAP_THRESHOLD_ {header['malloc_mmap_threshold']}"]
    seconds = header.get("seconds")
    lines.append(f"{summary['sets']} wide sets" + (f" in {seconds:.0f} s" if seconds is not None else " (cut short)") + (" (stopped at the time limit)" if header.get("stopped_at_time_limit") else ""))
    for route, totals in summary["routes"].items():
        peak = totals["largest_peak_mb"]
        lines.append(f"  {route}: held after trim {totals['held_after_trim_mb']:.1f} MB in all, {totals['sets_holding']} sets holding over {HELD_MB} MB, largest peak {peak if peak is None else round(peak)} MB, {totals['seconds']:.0f} s, {totals['errors']} raised")
    for name, groups in summary["groups"].items():
        lines.append(f"By {name}:")
        for group, values in sorted(groups.items(), key=lambda item: -item[1]["seconds"]):
            lines.append(f"  {group:22s} {values['sets']:5d} sets   seconds: single {values['fd_single_seconds']:7.1f}, multi {values['fd_multi_seconds']:7.1f}   held after trim: single {values['fd_single_held_mb']:9.1f} MB, multi {values['fd_multi_held_mb']:9.1f} MB")
    lines.append("Most held after trim:")
    lines.extend(one_line(record) for record in summary["most_held"])
    lines.append("Largest peaks:")
    lines.extend(one_line(record) for record in summary["largest_peaks"])
    return "\n".join(lines)


def render_file(path: Path) -> str:
    """The summary of a scan's JSON lines, from its records, also of a scan cut short."""
    header, records = {}, []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:  # a line cut off by a crash
            continue
        if "header" in row:
            header = {**header, **row["header"]}
        if "fd_single" in row and "draw" in row:
            records.append(row)
    return render(summarise(records), header)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--render", type=Path, help="Print the summary of an earlier scan's JSON lines, and do nothing else")
    parser.add_argument("--manifest", type=Path, help="The stress job's manifest.json, for its numbers of draws and seed")
    parser.add_argument("--dingo-draws", type=int, default=1_000_000)
    parser.add_argument("--wide-draws", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--first-chunks", type=int, default=300, help="Chunks of the stress plan to take the wide sets from")
    parser.add_argument("--max-draws", type=int, default=0, help="Stop after this many sets (0: no limit)")
    parser.add_argument("--max-minutes", type=float, default=20.0)
    parser.add_argument("--memory-cap-gb", type=float, default=24.0, help="Address-space limit for this process (0: none)")
    parser.add_argument("--lal-site", type=Path, help="A folder to import lal and lalsimulation from first")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.render:
        print(render_file(args.render))
        return 0
    if args.output is None:
        parser.error("--output is required")

    if args.manifest:
        task = next(task for task in json.loads(args.manifest.read_text(encoding="utf-8"))["tasks"] if task.get("kind") == "stress")
        args.dingo_draws, args.wide_draws, args.seed = task["dingo_draws"], task["wide_draws"], task["seed"]
    if args.memory_cap_gb and resource is not None:
        cap = int(args.memory_cap_gb * 1024**3)
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    os.environ["LAL_DEBUG_LEVEL"] = "0"  # refused parameter sets are expected
    if args.lal_site:
        sys.path.insert(0, str(args.lal_site.resolve()))
    import lal
    import lalsimulation as LS

    if not hasattr(LS, "SimInspiralFDMultiPhase"):
        print(f"LAL FAILED: {LS.__file__} has no SimInspiralFDMultiPhase: Run this with build_lal.sh's Python", file=sys.stderr)
        return 1
    try:
        default_prec_version = LS.SimInspiralWaveformParamsLookupPhenomXPrecVersion(lal.CreateDict())
    except Exception:
        default_prec_version = None
    header = {
        "lal": lal.__version__,
        "lalsimulation": LS.__version__,
        "default_prec_version": default_prec_version,
        "malloc_mmap_threshold": os.environ.get("MALLOC_MMAP_THRESHOLD_"),
        "seed": args.seed,
        "first_chunks": args.first_chunks
    }
    sets = scan_plan(args.dingo_draws, args.wide_draws, args.seed, args.first_chunks)
    if args.max_draws:
        sets = sets[:args.max_draws]
    records = []
    start = time.monotonic()
    stopped_at_time_limit = False
    with open(args.output, "w", encoding="utf-8") as output:
        output.write(json.dumps({"header": header}) + "\n")
        for chunk, position, draw in sets:
            if time.monotonic() - start > 60 * args.max_minutes:
                stopped_at_time_limit = True
                break
            output.write(json.dumps({"starting": [chunk, position], "draw": draw}) + "\n")
            output.flush()
            try:
                arguments = lal_arguments(lal, LS, draw)
            except Exception:  # LAL's spin conversion refused it: no route runs
                continue
            record = {"chunk": chunk, "position": position, "draw": describe(draw)}
            for route in ROUTES:
                record[route] = measure_route(lambda: call_route(lal, LS, route, *arguments))
            del arguments
            records.append(record)
            output.write(json.dumps(record) + "\n")
            output.flush()
        header["seconds"] = time.monotonic() - start
        header["stopped_at_time_limit"] = stopped_at_time_limit
        summary = summarise(records)
        output.write(json.dumps({"summary": summary, "header": header}) + "\n")
    print(render(summary, header))
    return 0


if __name__ == "__main__":
    sys.exit(main())
