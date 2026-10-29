"""Step 2.2: Where one sample's synthetic-phase work goes, on DINGO 0.10 with IMRPhenomXPHM.

Runs inside the dependencies-only image, from a shipped DINGO tree (checked by
guard.py), in one process; run_xphm_profile.sh sets OMP_NUM_THREADS=1. The
likelihood and waveform generator are built as the synthetic phase builds them.
For each of --num-samples network samples it times:

- generate_hplus_hcross: one of the nine polarisation calls, and inside it the
  parameter conversion (_convert_parameters) and the LAL call (SimInspiralFD);
- generate_hplus_hcross_m: the nine calls plus the DFT (the m-components);
- phase_grid_terms: all per-sample work of the synthetic phase (also the projection
  onto the detectors and the inner products);
- the same LAL call with IMRPhenomXHM (no precession: in-plane spins zero),
  IMRPhenomXP (precessing, (2, 2) only), IMRPhenomXAS (neither), and XPHM with
  multibanding off. Together these split XPHM's time into co-precessing modes and
  precession (speed-up 3) and show the conversion's share (speed-up 4).

For the first sample it also records how long LAL's output is against the domain
(and whether the extra bins are zero), and which of XPHM's model parameters change
with the reference phase at the nine DFT phases
(XLALSimIMRPhenomXPCalculateModelParametersFromSourceFrame). Finally it profiles
phase_grid_terms over the first --profile-samples samples.

With --dump-lal-args FILE it also writes, for lal/check_multiphase.py, the
XLALSimIMRPhenomXPHM arguments of the samples (as the generator converts them, at
phase 0) and this LAL's polarisations at the nine DFT phases for the first
--dump-reference samples.
"""
from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
for folder in (HERE, HERE.parent):
    if (folder / "guard.py").is_file():
        sys.path.insert(0, str(folder))
        break

import guard  # noqa: E402

LAL_DICT, APPROXIMANT = 18, 19  # positions in SimInspiralFD's argument tuple
IN_PLANE_SPINS = (2, 3, 5, 6)  # S1x, S1y, S2x, S2y
# SimInspiralFD positions of XLALSimIMRPhenomXPHM's arguments other than phiRef and the dictionary:
# masses, spins, distance, inclination, then f_min, f_max, deltaF, f_ref
XPHM_ARGUMENTS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 15, 16, 14, 17)


def summary_ms(seconds):
    values = [1e3 * s for s in seconds]
    return {
        "mean_ms": round(statistics.fmean(values), 4),
        "median_ms": round(statistics.median(values), 4),
        "min_ms": round(min(values), 4),
        "n": len(values),
    }


def timed(function, *args, **kwargs):
    start = time.perf_counter()
    value = function(*args, **kwargs)
    return time.perf_counter() - start, value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tree", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--proposal", required=True, help="Network samples (a Result file)")
    parser.add_argument("--event-data", required=True)
    parser.add_argument("--num-samples", type=int, default=100)
    parser.add_argument("--profile-samples", type=int, default=10)
    parser.add_argument("--dump-lal-args", help="Also write the samples' XLALSimIMRPhenomXPHM arguments here (.npz)")
    parser.add_argument("--dump-reference", type=int, default=5, help="Samples whose polarisations go into the dump")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        provenance = guard.use_dingo(args.tree, args.commit)
    except guard.GuardError as error:
        print(f"GUARD FAILED: {error}", file=sys.stderr)
        return 2

    import lal
    import lalsimulation as LS
    import numpy as np
    from bilby.core.prior import Constraint
    from dingo.gw.data.event_dataset import EventDataset
    from dingo.gw.prior import split_off_extrinsic_parameters
    from dingo.gw.result import Result

    result = Result(file_name=args.proposal)
    result.reset_event(EventDataset(file_name=args.event_data))
    result.use_base_domain = False
    likelihood = result.sampler_context.likelihood(use_base_domain=False)
    generator = likelihood.waveform_generator
    keys = [k for k, v in result.prior.items() if not isinstance(v, Constraint) and k in result.samples.columns]
    rows = result.samples[keys].iloc[: args.num_samples].to_dict("records")

    report = {
        "provenance": provenance,
        "inputs": {k: str(v) for k, v in vars(args).items()},
        "generator": {
            "approximant": generator.approximant_str,
            "spin_conversion_phase": generator.spin_conversion_phase,
            "uses_dft_phase_decomposition": generator.uses_dft_phase_decomposition,
            "ell_max": generator._get_ell_max(),
            "domain_bins": len(generator.domain()),
            "f_max": generator.domain.f_max,
        },
    }

    def lal_arguments(theta, phase):
        parameters, target = generator._convert_parameters(
            {**theta, "phase": phase, "f_ref": generator.f_ref}, generator.lal_params, return_target_function=True
        )
        return parameters, target

    def variant(parameters, approximant=None, in_plane_zero=False, multibanding=True):
        values = list(parameters)
        if in_plane_zero:
            for index in IN_PLANE_SPINS:
                values[index] = 0.0
        if approximant is not None:
            values[APPROXIMANT] = approximant
        if not multibanding:
            lal_dict = lal.CreateDict() if values[LAL_DICT] is None else lal.DictDuplicate(values[LAL_DICT])
            LS.SimInspiralWaveformParamsInsertPhenomXHMThresholdMband(lal_dict, 0)
            LS.SimInspiralWaveformParamsInsertPhenomXPHMThresholdMband(lal_dict, 0)
            values[LAL_DICT] = lal_dict
        return tuple(values)

    times = {name: [] for name in (
        "generate_hplus_hcross", "convert_parameters", "lal_XPHM", "generate_hplus_hcross_m", "phase_grid_terms",
        "lal_XPHM_no_multibanding", "lal_XHM", "lal_XP", "lal_XAS",
    )}
    for row in rows:
        theta = {k: float(v) for k, v in row.items()}
        intrinsic = {k: float(v) for k, v in split_off_extrinsic_parameters(theta)[0].items()}
        times["generate_hplus_hcross"].append(timed(generator.generate_hplus_hcross, {**intrinsic, "phase": 0.0})[0])
        seconds, (parameters, target) = timed(lal_arguments, intrinsic, 0.0)
        times["convert_parameters"].append(seconds)
        times["lal_XPHM"].append(timed(target, *parameters)[0])
        times["generate_hplus_hcross_m"].append(timed(generator.generate_hplus_hcross_m, {**intrinsic, "phase": 0.0})[0])
        times["phase_grid_terms"].append(timed(likelihood.phase_grid_terms, {**theta, "phase": 0.0})[0])
        times["lal_XPHM_no_multibanding"].append(timed(target, *variant(parameters, multibanding=False))[0])
        times["lal_XHM"].append(timed(target, *variant(parameters, LS.IMRPhenomXHM, in_plane_zero=True))[0])
        times["lal_XP"].append(timed(target, *variant(parameters, LS.IMRPhenomXP))[0])
        times["lal_XAS"].append(timed(target, *variant(parameters, LS.IMRPhenomXAS, in_plane_zero=True))[0])
    report["per_sample"] = {name: summary_ms(values) for name, values in times.items()}

    medians = {name: s["median_ms"] for name, s in report["per_sample"].items()}
    nine = 9 * medians["generate_hplus_hcross"]
    report["shares"] = {
        "conversion_of_one_call": medians["convert_parameters"] / medians["generate_hplus_hcross"],
        "lal_of_one_call": medians["lal_XPHM"] / medians["generate_hplus_hcross"],
        "nine_calls_of_m_components": nine / medians["generate_hplus_hcross_m"],
        "m_components_of_phase_grid_terms": medians["generate_hplus_hcross_m"] / medians["phase_grid_terms"],
        "XHM_of_XPHM": medians["lal_XHM"] / medians["lal_XPHM"],
        "XP_of_XPHM": medians["lal_XP"] / medians["lal_XPHM"],
        "XAS_of_XPHM": medians["lal_XAS"] / medians["lal_XPHM"],
        "XPHM_without_multibanding_over_with": medians["lal_XPHM_no_multibanding"] / medians["lal_XPHM"],
    }

    # One sample: LAL's output length, and which model parameters depend on the phase.
    theta = {k: float(v) for k, v in rows[0].items()}
    intrinsic = {k: float(v) for k, v in split_off_extrinsic_parameters(theta)[0].items()}
    parameters, target = lal_arguments(intrinsic, 0.0)
    hp, _ = target(*parameters)
    bins = len(generator.domain())
    report["lal_output"] = {
        "lal_bins": len(hp.data.data),
        "domain_bins": bins,
        "nonzero_bins_beyond_domain": int(np.count_nonzero(hp.data.data[bins:])),
    }
    phases = np.linspace(0, 2 * np.pi, 2 * generator._get_ell_max() + 1, endpoint=False)
    names = ("chi1L", "chi2L", "chi_p", "thetaJN", "alpha0", "phi_aligned", "zeta_polarization")
    try:
        values = []
        for phase in phases:
            p, _ = lal_arguments(intrinsic, float(phase))
            values.append(LS.SimIMRPhenomXPCalculateModelParametersFromSourceFrame(
                p[0], p[1], p[17], p[10], p[9], p[2], p[3], p[4], p[5], p[6], p[7], p[LAL_DICT]
            ))
        values = np.array(values, dtype=float)
        report["phase_dependence"] = {
            name: {"min": float(values[:, i].min()), "max": float(values[:, i].max()),
                   "changes_with_phase": bool(np.ptp(values[:, i]) > 1e-12)}
            for i, name in enumerate(names)
        }
    except Exception as error:  # recorded: LAL's binding may differ by version
        report["phase_dependence"] = {"error": f"{type(error).__name__}: {error}"}

    profiler = cProfile.Profile()
    profiler.enable()
    for row in rows[: args.profile_samples]:
        likelihood.phase_grid_terms({**{k: float(v) for k, v in row.items()}, "phase": 0.0})
    profiler.disable()
    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).sort_stats("tottime").print_stats(30)
    report["profile_phase_grid_terms"] = stream.getvalue()

    if args.dump_lal_args:
        dumped = []
        for row in rows:
            p, _ = lal_arguments({k: float(v) for k, v in split_off_extrinsic_parameters({k: float(v) for k, v in row.items()})[0].items()}, 0.0)
            if p[LAL_DICT] is not None:
                raise SystemExit("The generator passes a LAL dictionary; the dump covers lal_params = None only")
            dumped.append([float(p[i]) for i in XPHM_ARGUMENTS])
        reference_hp, reference_hc = [], []
        for a in dumped[: args.dump_reference]:
            hp_phases, hc_phases = [], []
            for phase in phases:
                hp, hc = LS.SimIMRPhenomXPHM(*a[:10], float(phase), *a[10:], None)
                hp_phases.append(hp.data.data.copy())
                hc_phases.append(hc.data.data.copy())
            reference_hp.append(hp_phases)
            reference_hc.append(hc_phases)
        np.savez(
            args.dump_lal_args,
            args=np.array(dumped),
            phases=phases,
            ref_hp=np.array(reference_hp),
            ref_hc=np.array(reference_hc),
            lal_version=lal.__version__,
            lalsimulation_version=LS.__version__,
        )
        report["dump"] = {"file": args.dump_lal_args, "samples": len(dumped), "reference_samples": len(reference_hp)}

    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("generator", "per_sample", "shares", "lal_output", "phase_dependence")}, indent=2))
    print(report["profile_phase_grid_terms"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
