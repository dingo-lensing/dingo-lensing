"""Prior-wide test of XLALSimInspiralFDMultiPhase against one XLALSimInspiralFD call per phase.

Runs in the dependencies-only image with build_lal.sh's LAL (see xphm_job.py), on many processes:

    python -I stress_multiphase.py --lal-site DIR --dingo-draws N --wide-draws N --num-processes P --output REPORT.json

Two kinds of parameter set, both IMRPhenomXPHM:

* dingo: The ranges of the production model's prior on its own settings (20 to 448 Hz at 0.125 Hz,
  f_ref 20 Hz, no LAL dictionary). The number of these is meant to reach the rare parameters whose
  multibanded waveform is numerically unstable (about 1 in a million, says DINGO).
* wide: Beyond what DINGO uses. Total mass 5 to 1000, mass ratio down to 1/50, other frequency
  settings, f_ref 0, longAscNodes, other numbers of phases, mode arrays, and settings the function
  hands to single calls (NNLO angles, other conventions, multibanding off); with edge cases on top:
  Aligned and zero spins, equal masses, face-on, extreme spin, a tiny in-plane spin.

Spins are converted as DINGO does with spin_conversion_phase = 0. Each set ends in one outcome:

* within_rtol: The rows agree to --rtol (default 1e-10, max |dh| / max |h| over frequency, h+ and
  hx, every phase), and the first phase's series is XLALSimInspiralFD's (epoch, deltaF, f0, length,
  and the data the rows hold).
* exact: The same, with the rows exactly equal: The function fell back to single calls.
* both_raise: Both refuse the parameters. Fine, nothing to compare.
* no_spins: LAL's spin conversion refused them, so neither route ran.
* unstable: Both flagged by DINGO's check for instability (max |h| > 1e-20). DINGO then regenerates
  each phase with single calls, so the rows are not used.
* one_raises, unstable_differs, series_differs, over_rtol: Failures.

A worker that crashes loses its chunk of draws. The chunks are seeded by kind and index, so a
missing one can be replayed. Reports are written as the run goes.

Memory: Each chunk records how much its worker's resident memory grew, apart for a worker's first
chunk, where the allocator settles in, so a leak shows as growth per draw in the later chunks.
--max-tasks-per-worker replaces each worker after that many chunks, which bounds any growth, and
--memory-limit-gb stops the run, with its report, once all its processes together hold that much
(the first run was held by Condor at its memory request, and lost everything).

Exit code 0 if nothing failed, 3 if something did, 1 if this script itself broke.
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import math
import multiprocessing
import os
import socket
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

try:
    import resource
except ImportError:  # not on Windows
    resource = None

HERE = Path(__file__).resolve().parent
for folder in (HERE, HERE.parent):
    if (folder / "guard.py").is_file():
        sys.path.insert(0, str(folder))
        break
sys.path.insert(0, str(HERE))

import guard  # noqa: E402
from check_multiphase import relative_difference  # noqa: E402

MSUN_KG = 1.988409870698051e30  # LAL_MSUN_SI
MPC_M = 3.085677581491367e22  # 1e6 LAL_PC_SI
DISTANCE_MPC = 1000.0
UNSTABLE_ABOVE = 1e-20  # generate_FD_waveform's check
TWO_PI = 2 * math.pi
KINDS = ("dingo", "wide")
CHUNK_SIZES = {"dingo": 200, "wide": 50}
FAILURES = ("one_raises", "unstable_differs", "series_differs", "over_rtol")
WORST_KEPT = 10
FAILURES_KEPT = 50


def isotropic(rng) -> float:
    return float(math.acos(rng.uniform(-1.0, 1.0)))


def uniform_phase(rng) -> float:
    return float(rng.uniform(0.0, TWO_PI))


def dingo_draw(rng) -> dict:
    """The ranges of the production model's prior: Chirp mass 10 to 180 (density proportional to it,
    as uniform in the components gives), mass ratio 0.125 to 1, spins to 0.99, isotropic."""
    chirp_mass = math.sqrt(rng.uniform(10.0**2, 180.0**2))
    q = float(rng.uniform(0.125, 1.0))
    m1 = chirp_mass * (1 + q) ** 0.2 / q**0.6
    return {
        "m1": m1,
        "m2": q * m1,
        "a_1": float(rng.uniform(0.0, 0.99)),
        "a_2": float(rng.uniform(0.0, 0.99)),
        "tilt_1": isotropic(rng),
        "tilt_2": isotropic(rng),
        "phi_12": uniform_phase(rng),
        "phi_jl": uniform_phase(rng),
        "theta_jn": isotropic(rng),
        "phase": uniform_phase(rng),
        "f_min": 20.0,
        "f_max": 448.0,
        "delta_f": 0.125,
        "f_ref": 20.0,
        "long_asc_nodes": 0.0,
        "num_phases": 9,
        "dictionary": {}
    }


def wide_dictionary(rng) -> dict:
    """A plain description of a LAL dictionary (lal_dictionary builds it)."""
    kind = rng.uniform()
    if kind < 0.6:
        return {}
    if kind < 0.75:
        modes = [[2, 2], [2, 1], [3, 3], [3, 2], [4, 4]]
        kept = [mode for mode in modes if rng.uniform() < 0.6]
        return {"modes": kept or [[2, 2]]}
    if kind < 0.85:
        return {"prec_version": int(rng.choice([102, 104, 220, 223, 224, 300, 320]))}
    if kind < 0.9:
        return {"convention": int(rng.choice([0, 1, 5, 6, 7]))}
    if kind < 0.95:
        return {"prec_threshold": 0.0}
    return {"mode_threshold": 0.0}


def wide_draw(rng) -> dict:
    total = math.exp(rng.uniform(math.log(5.0), math.log(1000.0)))
    q = math.exp(rng.uniform(math.log(1 / 50), 0.0))
    draw = dingo_draw(rng)
    f_min = float(rng.choice([10.0, 20.0, 40.0]))
    draw.update(
        m1=total / (1 + q),
        m2=total * q / (1 + q),
        f_min=f_min,
        f_max=float(rng.choice([448.0, 512.0, 1024.0, 2048.0])),
        delta_f=float(rng.choice([0.0625, 0.125, 0.25, 1.0])),
        f_ref=float(rng.choice([0.0, f_min, 20.0, 50.0])),
        num_phases=int(rng.choice([9, 9, 9, 9, 9, 1, 2, 3, 5, 11])),
        dictionary=wide_dictionary(rng)
    )
    if rng.uniform() < 0.05:
        draw["long_asc_nodes"] = uniform_phase(rng)
    edge = rng.uniform()
    if edge < 0.05:  # aligned or anti-aligned
        draw.update(tilt_1=float(rng.choice([0.0, math.pi])), tilt_2=float(rng.choice([0.0, math.pi])))
    elif edge < 0.10:  # no spins
        draw.update(a_1=0.0, a_2=0.0)
    elif edge < 0.15:  # equal masses, equal spins
        mean = 0.5 * (draw["m1"] + draw["m2"])
        draw.update(m1=mean, m2=mean, a_2=draw["a_1"], tilt_2=draw["tilt_1"])
    elif edge < 0.20:  # face-on or face-off
        draw.update(theta_jn=float(rng.choice([0.0, math.pi])))
    elif edge < 0.25:  # extreme spins
        draw.update(a_1=0.998, a_2=0.998)
    elif edge < 0.30:  # almost no in-plane spin
        draw.update(tilt_1=1e-6, tilt_2=1e-6)
    return draw


DRAWS = {"dingo": dingo_draw, "wide": wide_draw}


def lal_dictionary(lal, LS, spec: dict):
    if not spec:
        return None
    dictionary = lal.CreateDict()
    if "modes" in spec:
        modes = LS.SimInspiralCreateModeArray()
        for ell, emm in spec["modes"]:
            LS.SimInspiralModeArrayActivateMode(modes, ell, emm)
        LS.SimInspiralWaveformParamsInsertModeArray(dictionary, modes)
    if "prec_version" in spec:
        LS.SimInspiralWaveformParamsInsertPhenomXPrecVersion(dictionary, spec["prec_version"])
    if "convention" in spec:
        LS.SimInspiralWaveformParamsInsertPhenomXPConvention(dictionary, spec["convention"])
    if "prec_threshold" in spec:
        LS.SimInspiralWaveformParamsInsertPhenomXPHMThresholdMband(dictionary, spec["prec_threshold"])
    if "mode_threshold" in spec:
        LS.SimInspiralWaveformParamsInsertPhenomXHMThresholdMband(dictionary, spec["mode_threshold"])
    return dictionary


def classify(single_error, multi_error, difference, same_series, unstable_single, unstable_multi, rtol) -> str:
    if single_error and multi_error:
        return "both_raise"
    if single_error or multi_error:
        return "one_raises"
    if unstable_single != unstable_multi:
        return "unstable_differs"
    if unstable_single:
        return "unstable"
    if not same_series:
        return "series_differs"
    if difference > rtol:
        return "over_rtol"
    return "exact" if difference == 0.0 else "within_rtol"


def metadata(series) -> tuple:
    epoch = series.epoch
    return (epoch.gpsSeconds, epoch.gpsNanoSeconds, series.deltaF, series.f0, series.data.length)


def lal_arguments(lal, LS, draw: dict) -> tuple:
    """XLALSimInspiralFD's arguments before and after phiRef, and the phases, for one parameter set,
    with the spins converted as DINGO converts them (spin_conversion_phase = 0)."""
    m1, m2 = draw["m1"] * MSUN_KG, draw["m2"] * MSUN_KG
    f_ref = draw["f_ref"] or draw["f_min"]
    spins = LS.SimInspiralTransformPrecessingNewInitialConditions(
        draw["theta_jn"],
        draw["phi_jl"],
        draw["tilt_1"],
        draw["tilt_2"],
        draw["phi_12"],
        draw["a_1"],
        draw["a_2"],
        m1,
        m2,
        f_ref,
        0.0
    )
    inclination, s1x, s1y, s1z, s2x, s2y, s2z = spins
    head = (m1, m2, s1x, s1y, s1z, s2x, s2y, s2z, DISTANCE_MPC * MPC_M, inclination)
    dictionary = lal_dictionary(lal, LS, draw["dictionary"])
    tail = (draw["long_asc_nodes"], 0.0, 0.0, draw["delta_f"], draw["f_min"], draw["f_max"], draw["f_ref"], dictionary, LS.IMRPhenomXPHM)
    phases = [draw["phase"] + TWO_PI * k / draw["num_phases"] for k in range(draw["num_phases"])]
    return head, tail, phases


def evaluate(lal, LS, draw: dict, rtol: float) -> dict:
    """Both routes on one parameter set: {"outcome", "difference", "single_seconds", "multi_seconds", ...}."""
    try:
        head, tail, phases = lal_arguments(lal, LS, draw)
    except Exception as error:
        return {"outcome": "no_spins", "difference": 0.0, "single_seconds": 0.0, "multi_seconds": 0.0, "single_error": str(error), "multi_error": None}

    single_error, multi_error = None, None
    hp, hc, first, rows_p, rows_c, multi_first = [], [], None, None, None, None
    start = time.perf_counter()
    try:
        for phase in phases:
            p, c = LS.SimInspiralFD(*head, phase, *tail)
            first = p if first is None else first
            hp.append(p.data.data.copy())
            hc.append(c.data.data.copy())
    except Exception as error:  # LAL's errors reach Python as several exception types
        single_error = str(error)
    middle = time.perf_counter()
    try:
        vector = lal.CreateREAL8Vector(len(phases))
        vector.data[:] = phases
        multi_first, _, sequence_p, sequence_c = LS.SimInspiralFDMultiPhase(*head, vector, *tail)
        rows_p, rows_c = np.array(sequence_p.data, copy=True), np.array(sequence_c.data, copy=True)
    except Exception as error:
        multi_error = str(error)
    end = time.perf_counter()

    difference, same_series, unstable_single, unstable_multi = 0.0, False, False, False
    if single_error is None and multi_error is None:
        hp, hc = np.array(hp), np.array(hc)
        difference = max(relative_difference(hp, rows_p), relative_difference(hc, rows_c))
        same_series = metadata(first) == metadata(multi_first) and np.array_equal(multi_first.data.data, rows_p[0])
        unstable_single = bool(max(np.abs(hp).max(), np.abs(hc).max()) > UNSTABLE_ABOVE)
        unstable_multi = bool(max(np.abs(rows_p).max(), np.abs(rows_c).max()) > UNSTABLE_ABOVE)
    outcome = classify(single_error, multi_error, difference, same_series, unstable_single, unstable_multi, rtol)
    return {
        "outcome": outcome,
        "difference": difference,
        "single_seconds": middle - start,
        "multi_seconds": end - middle,
        "single_error": single_error,
        "multi_error": multi_error
    }


def new_tally() -> dict:
    return {
        "draws": 0,
        "outcomes": {},
        "difference_decades": {},
        "max_difference": 0.0,
        "single_seconds": 0.0,
        "multi_seconds": 0.0,
        "worst": [],
        "failures": [],
        "memory_first_growth_kb": 0,
        "memory_first_draws": 0,
        "memory_later_growth_kb": 0,
        "memory_later_draws": 0,
        "worker_peak_mb": 0.0
    }


def add_to_tally(tally: dict, draw: dict, record: dict) -> None:
    outcome = record["outcome"]
    tally["draws"] += 1
    tally["outcomes"][outcome] = tally["outcomes"].get(outcome, 0) + 1
    if outcome not in ("both_raise", "one_raises", "no_spins"):  # those have no times to compare
        tally["single_seconds"] += record["single_seconds"]
        tally["multi_seconds"] += record["multi_seconds"]
    entry = {**record, "draw": draw}
    if outcome == "within_rtol" or outcome == "over_rtol":
        difference = record["difference"]
        decade = str(math.floor(math.log10(difference))) if math.isfinite(difference) else "inf"
        tally["difference_decades"][decade] = tally["difference_decades"].get(decade, 0) + 1
        tally["max_difference"] = max(tally["max_difference"], difference)
        tally["worst"] = sorted(tally["worst"] + [entry], key=lambda e: -e["difference"])[:WORST_KEPT]
    if outcome in FAILURES and len(tally["failures"]) < FAILURES_KEPT:
        tally["failures"].append(entry)


def merge_tallies(into: dict, other: dict) -> None:
    into["draws"] += other["draws"]
    for key in ("outcomes", "difference_decades"):
        for name, count in other[key].items():
            into[key][name] = into[key].get(name, 0) + count
    into["max_difference"] = max(into["max_difference"], other["max_difference"])
    into["single_seconds"] += other["single_seconds"]
    into["multi_seconds"] += other["multi_seconds"]
    into["worst"] = sorted(into["worst"] + other["worst"], key=lambda e: -e["difference"])[:WORST_KEPT]
    into["failures"] = (into["failures"] + other["failures"])[:FAILURES_KEPT]
    for key in ("memory_first_growth_kb", "memory_first_draws", "memory_later_growth_kb", "memory_later_draws"):
        into[key] += other[key]
    into["worker_peak_mb"] = max(into["worker_peak_mb"], other["worker_peak_mb"])


def resident_kb(pid="self") -> Optional[int]:
    """A process's resident memory in kB, or None where /proc does not tell."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def total_resident_gb() -> Optional[float]:
    """The resident memory of this process and its children (the workers), which counts shared
    pages once per process, so more than the job's own count."""
    sizes = [resident_kb()] + [resident_kb(child.pid) for child in multiprocessing.active_children()]
    known = [size for size in sizes if size is not None]
    return sum(known) / 1024**2 if known else None


def chunk_plan(dingo_draws: int, wide_draws: int, seed: int) -> List[Tuple[str, int, int]]:
    """(kind, index, draws) of every chunk, shuffled, so a run cut short has both kinds."""
    chunks = []
    for kind, draws in zip(KINDS, (dingo_draws, wide_draws)):
        size = CHUNK_SIZES[kind]
        for index, start in enumerate(range(0, draws, size)):
            chunks.append((kind, index, min(size, draws - start)))
    order = np.random.default_rng([seed, 2]).permutation(len(chunks))
    return [chunks[i] for i in order]


# Set in main, and inherited by the forked workers.
_lal = None
_LS = None
_seed = 0
_rtol = 0.0
# Chunks this worker has run, for telling its first chunk from the later ones.
_chunks_done = 0


def run_chunk(chunk: Tuple[str, int, int]) -> Tuple[str, int, dict]:
    global _chunks_done
    kind, index, draws = chunk
    rng = np.random.default_rng([_seed, KINDS.index(kind), index])
    tally = new_tally()
    before = resident_kb()
    for _ in range(draws):
        draw = DRAWS[kind](rng)
        add_to_tally(tally, draw, evaluate(_lal, _LS, draw, _rtol))
    after = resident_kb()
    if before is not None and after is not None:
        which = "first" if _chunks_done == 0 else "later"
        tally[f"memory_{which}_growth_kb"] = after - before
        tally[f"memory_{which}_draws"] = draws
    if resource is not None:
        tally["worker_peak_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    _chunks_done += 1
    return kind, index, tally


def failure_count(tally: dict) -> int:
    return sum(tally["outcomes"].get(name, 0) for name in FAILURES)


def write_report(path: Path, report: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv=None) -> int:
    global _lal, _LS, _seed, _rtol
    faulthandler.enable()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lal-site", required=True, type=Path)
    parser.add_argument("--dingo-draws", type=int, default=1_000_000)
    parser.add_argument("--wide-draws", type=int, default=200_000)
    parser.add_argument("--num-processes", type=int, default=32)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--rtol", type=float, default=1e-10)
    parser.add_argument("--max-minutes", type=float, default=240.0, help="Stop here and report what is done")
    parser.add_argument("--stall-minutes", type=float, default=30.0, help="Give up after this long with no chunk finished")
    parser.add_argument("--max-tasks-per-worker", type=int, default=0, help="Replace each worker after this many chunks (0: never)")
    parser.add_argument("--memory-limit-gb", type=float, default=0.0, help="Stop once all the processes hold this much (0: no limit)")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    os.environ["LAL_DEBUG_LEVEL"] = "0"  # refused parameters are expected, and would fill the log
    lal_site = args.lal_site.resolve()
    sys.path.insert(0, str(lal_site))
    import lal
    import lalsimulation as LS

    origin = Path(LS.__file__).resolve()
    if lal_site not in origin.parents or not hasattr(LS, "SimInspiralFDMultiPhase"):
        print(f"LAL FAILED: lalsimulation is {origin}, not {lal_site}'s with SimInspiralFDMultiPhase", file=sys.stderr)
        return 1
    outside = guard.lal_libraries_outside(lal_site.parent)
    if outside:
        print(f"LAL FAILED: LAL's libraries are not those shipped with {lal_site}: {outside}", file=sys.stderr)
        return 1
    _lal, _LS, _seed, _rtol = lal, LS, args.seed, args.rtol

    chunks = chunk_plan(args.dingo_draws, args.wide_draws, args.seed)
    tallies = {kind: new_tally() for kind in KINDS}
    report = {
        "inputs": {k: str(v) for k, v in vars(args).items()},
        "host": socket.gethostname(),
        "lal": {"lal": lal.__version__, "lalsimulation": LS.__version__, "file": str(origin), "libraries": guard.mapped_libraries()},
        "numpy": np.__version__,
        "chunks": len(chunks),
        "kinds": tallies
    }
    write_report(args.output, report)

    pending = set((kind, index) for kind, index, _ in chunks)
    start = time.monotonic()
    last_result, last_report = start, start
    stalled, stopped_for_memory = False, False
    report["peak_total_resident_gb"] = 0.0
    with multiprocessing.Pool(args.num_processes, maxtasksperchild=args.max_tasks_per_worker or None) as pool:
        results = pool.imap_unordered(run_chunk, chunks)
        while pending:
            now = time.monotonic()
            if now - start > 60 * args.max_minutes:
                break
            if now - last_result > 60 * args.stall_minutes:
                stalled = True
                break
            resident = total_resident_gb()
            if resident is not None:
                report["peak_total_resident_gb"] = max(report["peak_total_resident_gb"], resident)
                if args.memory_limit_gb and resident > args.memory_limit_gb:
                    stopped_for_memory = True
                    break
            try:
                kind, index, tally = results.next(timeout=20)
            except multiprocessing.TimeoutError:
                continue
            pending.discard((kind, index))
            merge_tallies(tallies[kind], tally)
            last_result = time.monotonic()
            if last_result - last_report > 60:
                last_report = last_result
                report["seconds"] = round(last_result - start, 1)
                write_report(args.output, report)
        pool.terminate()

    failures = sum(failure_count(tally) for tally in tallies.values())
    report["seconds"] = round(time.monotonic() - start, 1)
    report["failures"] = failures
    report["chunks_missing"] = sorted(pending)
    report["stopped_at_time_limit"] = bool(pending) and not stalled and not stopped_for_memory
    report["stalled"] = stalled
    report["stopped_for_memory"] = stopped_for_memory
    report["ok"] = failures == 0 and not stalled and not stopped_for_memory
    for kind, tally in tallies.items():
        if tally["multi_seconds"] > 0:
            tally["speedup_of_sums"] = tally["single_seconds"] / tally["multi_seconds"]
        if tally["memory_later_draws"]:
            tally["growth_kb_per_draw"] = tally["memory_later_growth_kb"] / tally["memory_later_draws"]
    write_report(args.output, report)

    for kind, tally in tallies.items():
        growth = tally.get("growth_kb_per_draw")
        memory = f", worker peak {tally['worker_peak_mb']:.0f} MB" + (f", {growth:.2f} kB per draw after the first chunk" if growth is not None else "")
        print(f"{kind}: {tally['draws']} draws, {tally['outcomes']}, largest difference {tally['max_difference']:.3e}{memory}")
    print(f"All processes together held up to {report['peak_total_resident_gb']:.1f} GB" + (" (stopped there)" if stopped_for_memory else ""))
    print(f"{'OK' if report['ok'] else 'FAILED'}: {failures} failures, {len(pending)} chunks missing; report {args.output}")
    return 0 if report["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
