"""Check XLALSimIMRPhenomXPHMMultiPhase against one XLALSimIMRPhenomXPHM call per phase, and time both.

Runs in the environment build_lal.sh makes (its LAL and LALSimulation, with the patch), on one
thread (run_multiphase_check.sh sets OMP_NUM_THREADS=1):

    python -I check_multiphase.py [--samples ARGS.npz] [--random 200] --output REPORT.json

Parameter sets: the LAL arguments of DINGO network samples (--samples, written by
bench/xphm_profile.py --dump-lal-args), --random draws from a broad precessing prior, and
special cases for the configurations the function shares and those it hands to single calls.
At DINGO's nine DFT phases it records, per set, the largest relative difference between the
two (max |dh| / max |h| over frequency, for h+ and hx), and the time of nine single calls
against one call of the new function. A shared case must agree to --rtol (default 1e-10) and
not exactly; a case handed to single calls must agree exactly.

Also, for scale: the release LAL's polarisations in the dump against this build's, and, on the
DINGO samples, the mismatch of the default multibanded Euler angles, and of the same with
complex steps between coarse frequencies (MultiPhaseComplexQ), against angles evaluated at
every frequency (PrecThresholdMband = 0).

Exit code 0 if every case agrees as required, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path

NUM_PHASES = 9  # 2 ell_max + 1 for ell_max = 4, as in DINGO's DFT
ARG_NAMES = ("m1", "m2", "s1x", "s1y", "s1z", "s2x", "s2y", "s2z", "distance", "inclination", "f_min", "f_max", "delta_f", "f_ref")


def dft_phases(n: int = NUM_PHASES) -> list:
    return [2 * math.pi * k / n for k in range(n)]


def relative_difference(reference, other) -> float:
    """Largest max |other - reference| / max |reference| over the rows; inf for a shape or NaN mismatch."""
    import numpy as np

    reference, other = np.atleast_2d(np.asarray(reference)), np.atleast_2d(np.asarray(other))
    if reference.shape != other.shape:
        return math.inf
    peak = np.abs(reference).max(axis=-1)
    difference = np.abs(other - reference).max(axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(peak > 0, difference / peak, np.where(difference > 0, np.inf, 0.0))
    ratio = np.where(np.isnan(ratio), np.inf, ratio)
    return float(ratio.max())


def mismatch(a, b, weights) -> float:
    """1 - <a, b> / sqrt(<a, a> <b, b>), <x, y> = sum Re(conj(x) y) weights over frequency, not maximised."""
    import numpy as np

    def inner(x, y):
        return float(np.sum((np.conj(x) * y).real * weights))

    aa, bb = inner(a, a), inner(b, b)
    if aa <= 0 or bb <= 0:
        return math.nan
    return 1.0 - inner(a, b) / math.sqrt(aa * bb)


def verdict(expected: str, difference: float, rtol: float) -> bool:
    """A shared case agrees to rtol but not exactly (exactly would mean it fell back); a fallback case
    agrees exactly; either kind is fine for 'either'."""
    if expected == "fallback":
        return difference == 0.0
    if expected == "shared":
        return 0.0 < difference <= rtol
    return difference <= rtol


def summarise(values) -> dict:
    values = [v for v in values if v is not None and not math.isnan(v)]
    if not values:
        return {"n": 0}
    return {"n": len(values), "median": statistics.median(values), "max": max(values), "min": min(values)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--samples", help="LAL arguments of DINGO network samples (.npz from xphm_profile.py)")
    parser.add_argument("--random", type=int, default=200, help="Number of random parameter sets")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--rtol", type=float, default=1e-10)
    parser.add_argument("--repeats", type=int, default=3, help="Timing repeats per DINGO sample (best kept)")
    parser.add_argument("--angle-samples", type=int, default=20, help="DINGO samples for the angle multibanding check")
    parser.add_argument("--built", help="BUILT.txt of build_lal.sh, recorded in the report")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    import lal
    import lalsimulation as LS
    import numpy as np

    phases = dft_phases()

    def lal_dict(**entries):
        if not entries:
            return None
        d = lal.CreateDict()
        for key, value in entries.items():
            if key == "modes":
                modes = LS.SimInspiralCreateModeArray()
                for ell, emm in value:
                    LS.SimInspiralModeArrayActivateMode(modes, ell, emm)
                LS.SimInspiralWaveformParamsInsertModeArray(d, modes)
            elif key == "convention":
                LS.SimInspiralWaveformParamsInsertPhenomXPConvention(d, value)
            elif key == "prec_version":
                LS.SimInspiralWaveformParamsInsertPhenomXPrecVersion(d, value)
            elif key == "prec_threshold":
                LS.SimInspiralWaveformParamsInsertPhenomXPHMThresholdMband(d, value)
            elif key == "mode_threshold":
                LS.SimInspiralWaveformParamsInsertPhenomXHMThresholdMband(d, value)
            elif key == "complex_q":
                lal.DictInsertINT4Value(d, "MultiPhaseComplexQ", value)
            else:
                raise KeyError(key)
        return d

    def single(a, phase_list, d):
        m1, m2, s1x, s1y, s1z, s2x, s2y, s2z, dist, incl, f_min, f_max, delta_f, f_ref = a
        hp, hc = [], []
        for phase in phase_list:
            p, c = LS.SimIMRPhenomXPHM(m1, m2, s1x, s1y, s1z, s2x, s2y, s2z, dist, incl, float(phase), f_min, f_max, delta_f, f_ref, d)
            hp.append(p.data.data.copy())
            hc.append(c.data.data.copy())
        return np.array(hp), np.array(hc)

    def multi(a, phase_list, d):
        m1, m2, s1x, s1y, s1z, s2x, s2y, s2z, dist, incl, f_min, f_max, delta_f, f_ref = a
        vector = lal.CreateREAL8Vector(len(phase_list))
        vector.data[:] = np.asarray(phase_list, dtype=float)
        p, c = LS.SimIMRPhenomXPHMMultiPhase(m1, m2, s1x, s1y, s1z, s2x, s2y, s2z, dist, incl, vector, f_min, f_max, delta_f, f_ref, d)
        return np.array(p.data, copy=True), np.array(c.data, copy=True)

    def best_time(function, repeats):
        best = math.inf
        for _ in range(repeats):
            start = time.perf_counter()
            function()
            best = min(best, time.perf_counter() - start)
        return best

    def compare(name, a, expected, phase_list=phases, d=None):
        hp1, hc1 = single(a, phase_list, d)
        hp9, hc9 = multi(a, phase_list, d)
        difference = max(relative_difference(hp1, hp9), relative_difference(hc1, hc9))
        return {"name": name, "expected": expected, "difference": difference, "ok": verdict(expected, difference, args.rtol)}

    report = {
        "versions": {"lal": lal.__version__, "lalsimulation": LS.__version__, "numpy": np.__version__, "python": platform.python_version()},
        "host": {"node": platform.node(), "machine": platform.machine(), "processor": platform.processor()},
        "built": Path(args.built).read_text(encoding="utf-8").splitlines() if args.built else None,
        "rtol": args.rtol,
        "phases": phases,
    }
    failures = []

    # Special cases: what the function shares, and what it must hand to single calls.
    msun, mpc = lal.MSUN_SI, 1e6 * lal.PC_SI
    base = [36 * msun, 29 * msun, 0.3, -0.2, 0.25, -0.1, 0.4, -0.3, 800 * mpc, 1.1, 20.0, 448.0, 0.125, 20.0]
    equal = [30 * msun, 30 * msun, 0.4, 0.0, 0.3, 0.0, 0.4, 0.3, 800 * mpc, 0.7, 20.0, 448.0, 0.125, 20.0]
    heavy = [330 * msun, 280 * msun, 0.3, -0.2, 0.25, -0.1, 0.4, -0.3, 800 * mpc, 1.1, 20.0, 448.0, 0.125, 20.0]
    nearly_aligned = [36 * msun, 29 * msun, 1e-5, 0.0, 0.25, 0.0, 1e-5, -0.3, 800 * mpc, 1.1, 20.0, 448.0, 0.125, 20.0]
    cases = [
        ("default", base, "shared", phases, None),
        ("one phase", base, "shared", [1.3], None),
        ("three phases off the DFT grid", base, "shared", [0.1, 2.0, 5.5], None),
        ("equal masses and aligned spins (odd modes skipped)", equal, "shared", phases, None),
        ("only the (2, 2) mode", base, "shared", phases, lal_dict(modes=[(2, 2), (2, -2)])),
        ("(2, 2) and (3, 3) modes", base, "shared", phases, lal_dict(modes=[(2, 2), (2, -2), (3, 3), (3, -3)])),
        ("mode multibanding off", base, "shared", phases, lal_dict(mode_threshold=0.0)),
        ("convention 0", base, "shared", phases, lal_dict(convention=0)),
        ("PrecVersion 223 explicitly", base, "shared", phases, lal_dict(prec_version=223)),
        ("convention 6 (phi0 follows the phase)", base, "fallback", phases, lal_dict(convention=6)),
        ("convention 7 (phi0 follows the phase)", base, "fallback", phases, lal_dict(convention=7)),
        ("angle multibanding off", base, "fallback", phases, lal_dict(prec_threshold=0.0)),
        ("NNLO angles (PrecVersion 102)", base, "fallback", phases, lal_dict(prec_version=102)),
        ("total mass above 500 (multibanding off)", heavy, "fallback", phases, None),
        ("nearly aligned spins", nearly_aligned, "either", phases, None),
    ]
    special = [compare(name, a, expected, phase_list, d) for name, a, expected, phase_list, d in cases]
    report["special_cases"] = special
    failures += [c for c in special if not c["ok"]]

    # Random parameter sets from a broad precessing prior.
    rng = np.random.default_rng(args.seed)
    random_results = []
    for k in range(args.random):
        total, q = rng.uniform(20, 200), rng.uniform(0.125, 1)
        m1, m2 = total / (1 + q) * msun, total * q / (1 + q) * msun
        a1, a2 = rng.uniform(0, 0.99, 2)
        tilt1, tilt2 = np.arccos(rng.uniform(-1, 1, 2))
        phi12, phi_jl = rng.uniform(0, 2 * np.pi, 2)
        theta_jn = float(np.arccos(rng.uniform(-1, 1)))
        incl, s1x, s1y, s1z, s2x, s2y, s2z = LS.SimInspiralTransformPrecessingNewInitialConditions(theta_jn, phi_jl, tilt1, tilt2, phi12, a1, a2, m1, m2, 20.0, 0.0)
        a = [m1, m2, s1x, s1y, s1z, s2x, s2y, s2z, rng.uniform(100, 3000) * mpc, incl, 20.0, 448.0, 0.125, 20.0]
        result = compare(f"random {k}", a, "either")
        result["arguments"] = dict(zip(ARG_NAMES, map(float, a)))
        random_results.append(result)
    report["random"] = {
        "n": len(random_results),
        "max_difference": max((r["difference"] for r in random_results), default=0.0),
        "exact": sum(r["difference"] == 0.0 for r in random_results),
        "failures": [r for r in random_results if not r["ok"]][:10],
    }
    failures += [r for r in random_results if not r["ok"]]

    # DINGO network samples: agreement, timing, the release LAL for scale, the angle multibanding.
    if args.samples:
        data = np.load(args.samples)
        sample_args = [list(map(float, row)) for row in data["args"]]
        results, single_times, multi_times, one_times = [], [], [], []
        for k, a in enumerate(sample_args):
            result = compare(f"sample {k}", a, "either")
            results.append(result)
            single_times.append(best_time(lambda: single(a, phases, None), args.repeats))
            multi_times.append(best_time(lambda: multi(a, phases, None), args.repeats))
            one_times.append(best_time(lambda: multi(a, phases[:1], None), args.repeats))
        failures += [r for r in results if not r["ok"]]
        speedups = [s / m for s, m in zip(single_times, multi_times)]
        report["dingo_samples"] = {
            "file": args.samples,
            "n": len(results),
            "max_difference": max((r["difference"] for r in results), default=0.0),
            "exact": sum(r["difference"] == 0.0 for r in results),
            "failures": [r for r in results if not r["ok"]][:10],
            "time_nine_single_calls_ms": summarise([1e3 * t for t in single_times]),
            "time_multi_phase_call_ms": summarise([1e3 * t for t in multi_times]),
            "time_multi_phase_call_one_phase_ms": summarise([1e3 * t for t in one_times]),
            "speedup_nine_phases": summarise(speedups),
        }

        if "ref_hp" in data.files and len(data["ref_hp"]):
            reference = []
            for k in range(len(data["ref_hp"])):
                hp1, hc1 = single(sample_args[k], data["phases"], None)
                reference.append(max(relative_difference(data["ref_hp"][k], hp1), relative_difference(data["ref_hc"][k], hc1)))
            report["release_vs_this_build"] = {
                "n": len(reference),
                "max_difference": max(reference),
                "release": {"lal": str(data["lal_version"]), "lalsimulation": str(data["lalsimulation_version"])},
            }

        angle = {"default_vs_exact": [], "complex_q_vs_exact": [], "default_vs_complex_q": [], "complex_q_used": []}
        for a in sample_args[: args.angle_samples]:
            f = np.arange(int(round(a[11] / a[12])) + 1) * a[12]
            hp_default, hc_default = multi(a, phases[:1], None)
            hp_exact, hc_exact = single(a, phases[:1], lal_dict(prec_threshold=0.0))
            hp_cq, hc_cq = multi(a, phases[:1], lal_dict(complex_q=1))
            n = min(hp_default.shape[-1], f.size)
            weights = np.zeros(n)
            band = (f[:n] >= a[10]) & (f[:n] <= a[11]) & (f[:n] > 0)
            weights[band] = [1.0 / LS.SimNoisePSDaLIGOZeroDetHighPower(float(x)) for x in f[:n][band]]

            def worst(x, y):
                return max(mismatch(x[0][0, :n], y[0][0, :n], weights), mismatch(x[1][0, :n], y[1][0, :n], weights))

            default, exact, cq = (hp_default, hc_default), (hp_exact, hc_exact), (hp_cq, hc_cq)
            angle["default_vs_exact"].append(worst(default, exact))
            angle["complex_q_vs_exact"].append(worst(cq, exact))
            angle["default_vs_complex_q"].append(worst(default, cq))
            angle["complex_q_used"].append(relative_difference(hp_default, hp_cq) > 0)
        report["angle_multibanding"] = {
            "weighting": "aLIGO zero-detuned high-power PSD, f_min to f_max, h+ and hx (worse of the two), phase 0, no maximisation",
            "n": len(angle["default_vs_exact"]),
            "complex_q_took_effect": sum(angle["complex_q_used"]),
            "mismatch_default_vs_exact": summarise(angle["default_vs_exact"]),
            "mismatch_complex_q_vs_exact": summarise(angle["complex_q_vs_exact"]),
            "mismatch_default_vs_complex_q": summarise(angle["default_vs_complex_q"]),
        }

    report["failures"] = len(failures)
    report["ok"] = not failures
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report["versions"]))
    for c in special:
        print(f"{'ok  ' if c['ok'] else 'FAIL'} {c['name']:52s} expected {c['expected']:8s} max rel. difference {c['difference']:.2e}")
    print(f"random: {report['random']['n']} sets, max rel. difference {report['random']['max_difference']:.2e}, {report['random']['exact']} exact, {len(report['random']['failures'])} failed")
    for key in ("dingo_samples", "release_vs_this_build", "angle_multibanding"):
        if key in report:
            print(key, json.dumps({k: v for k, v in report[key].items() if k not in ("failures", "file")}, indent=1))
    print(f"{'OK' if report['ok'] else 'FAILED'}: {report['failures']} failures; report {args.output}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
