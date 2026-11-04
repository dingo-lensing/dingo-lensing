"""Memory growth per call of the multi-phase functions and of the single calls they stand for.

Runs in the environment build_lal.sh made, on one process, on an access point (about ten minutes):

    ~/dingo-speedups-lal/env/bin/python -I leak_check.py [--output REPORT.json]

Four routes, on parameter sets of stress_multiphase.py's two kinds (the production model's, and wide
ones), each set one that none of the routes refuses:

* fd_single: Nine XLALSimInspiralFD calls, one per phase, as DINGO makes them without the new function.
* fd_multi: One XLALSimInspiralFDMultiPhase call.
* xphm_single, xphm_multi: The same at the level of XLALSimIMRPhenomXPHM, without the conditioning.

So a leak can be told apart: In LAL's own XPHM (both single routes), in the new XPHM function
(xphm_multi, and fd_multi with it), or in the new conditioning around it (fd_multi alone).

Each route runs a warm-up, then three windows of calls; after each window the allocator gives back
what it can (malloc_trim) and the resident memory is read. A leak grows it by about the same amount
in every window, where the allocator's own growth levels off. A route leaks if both later windows
grow by more than --threshold-kb per call.

Exit code 0 if no route leaks, 3 if one does.
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from stress_multiphase import DRAWS, KINDS, lal_arguments, resident_kb  # noqa: E402

ROUTES = ("fd_single", "fd_multi", "xphm_single", "xphm_multi")
WINDOWS = 3


def phase_vector(lal, phases):
    vector = lal.CreateREAL8Vector(len(phases))
    vector.data[:] = phases
    return vector


def call_route(lal, LS, route: str, head, tail, phases) -> None:
    """One call of a route, its results let go of at once."""
    _, _, _, delta_f, f_min, f_max, f_ref, dictionary, _ = tail
    if route == "fd_single":
        for phase in phases:
            LS.SimInspiralFD(*head, phase, *tail)
    elif route == "fd_multi":
        LS.SimInspiralFDMultiPhase(*head, phase_vector(lal, phases), *tail)
    elif route == "xphm_single":
        for phase in phases:
            LS.SimIMRPhenomXPHM(*head, phase, f_min, f_max, delta_f, f_ref, dictionary)
    elif route == "xphm_multi":
        LS.SimIMRPhenomXPHMMultiPhase(*head, phase_vector(lal, phases), f_min, f_max, delta_f, f_ref, dictionary)
    else:
        raise ValueError(f"Unknown route: {route}")


def parameter_sets(lal, LS, kind: str, wanted: int, seed: int) -> List[tuple]:
    """Up to `wanted` argument sets of a kind that every route takes."""
    rng = np.random.default_rng([seed, 7, KINDS.index(kind)])
    sets = []
    for _ in range(20 * wanted):
        if len(sets) == wanted:
            break
        try:
            arguments = lal_arguments(lal, LS, DRAWS[kind](rng))
            for route in ROUTES:
                call_route(lal, LS, route, *arguments)
        except Exception:  # refused by a route: not one to measure on
            continue
        sets.append(arguments)
    return sets


def trim() -> None:
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def growth_per_call(resident: List[int], calls: int) -> List[float]:
    """kB per call of each window, from the resident memory before the first window and after each."""
    return [(after - before) / calls for before, after in zip(resident, resident[1:])]


def leaks(per_call: List[float], threshold_kb: float) -> bool:
    """Growing in both later windows: The first can be the allocator settling in."""
    return len(per_call) >= 2 and all(growth > threshold_kb for growth in per_call[1:])


def measure(call: Callable[[tuple], None], sets: List[tuple], calls: int, resident: Callable[[], Optional[int]] = resident_kb) -> dict:
    for k in range(max(1, calls // 4)):  # warm-up
        call(sets[k % len(sets)])
    trim()
    readings = [resident()]
    start = time.perf_counter()
    for window in range(WINDOWS):
        for k in range(calls):
            call(sets[(window * calls + k) % len(sets)])
        trim()
        readings.append(resident())
    seconds = time.perf_counter() - start
    if any(reading is None for reading in readings):
        return {"resident_kb": readings, "ms_per_call": 1e3 * seconds / (WINDOWS * calls)}
    return {"resident_kb": readings, "kb_per_call": growth_per_call(readings, calls), "ms_per_call": 1e3 * seconds / (WINDOWS * calls)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dingo-calls", type=int, default=400, help="Calls per window on the production model's parameters")
    parser.add_argument("--wide-calls", type=int, default=100, help="Calls per window on wide parameters")
    parser.add_argument("--sets", type=int, default=40, help="Parameter sets of each kind, used in turn")
    parser.add_argument("--threshold-kb", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    os.environ["LAL_DEBUG_LEVEL"] = "0"  # refused parameter sets are expected while choosing them
    import lal
    import lalsimulation as LS

    if not hasattr(LS, "SimInspiralFDMultiPhase"):
        print(f"LAL FAILED: {LS.__file__} has no SimInspiralFDMultiPhase: Run this with build_lal.sh's Python", file=sys.stderr)
        return 1
    report = {"lal": {"lal": lal.__version__, "lalsimulation": LS.__version__, "file": LS.__file__}, "threshold_kb": args.threshold_kb, "results": {}}
    leaking = []
    for kind, calls in (("dingo", args.dingo_calls), ("wide", args.wide_calls)):
        sets = parameter_sets(lal, LS, kind, args.sets, args.seed)
        report["results"][kind] = {"sets": len(sets), "calls_per_window": calls}
        for route in ROUTES:
            result = measure(lambda arguments: call_route(lal, LS, route, *arguments), sets, calls)
            result["leaks"] = leaks(result.get("kb_per_call", []), args.threshold_kb)
            report["results"][kind][route] = result
            if result["leaks"]:
                leaking.append(f"{kind} {route}")
            growth = ", ".join(f"{value:+.2f}" for value in result.get("kb_per_call", []))
            print(f"{kind:5s} {route:11s} {result['ms_per_call']:8.2f} ms per call   kB per call by window: {growth}   {'LEAKS' if result['leaks'] else ''}", flush=True)
    report["leaking"] = leaking
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("No route leaks" if not leaking else f"Leaking: {', '.join(leaking)}")
    return 3 if leaking else 0


if __name__ == "__main__":
    sys.exit(main())
