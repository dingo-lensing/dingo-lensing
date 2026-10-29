"""Step 5.6: DINGO with one LS.SimInspiralFDMultiPhase call per sample against nine LS.SimInspiralFD calls.

Runs inside the dependencies-only image, from a shipped DINGO tree (checked by guard.py), with
the LAL and LALSimulation of build_lal.sh first on sys.path (--lal-site), on one thread
(run_check_dingo_multiphase.sh sets OMP_NUM_THREADS=1):

    python -I check_dingo_multiphase.py --lal-site DIR --tree DIR --commit SHA \\
        --proposal SAMPLES.hdf5 --event-data EVENT.hdf5 --output REPORT.json

For --num-samples network samples it compares the m-components (generate_hplus_hcross_m)
and the per-sample terms of the synthetic phase (likelihood.phase_grid_terms) from the
one-call route with those of the repeated calls (LS.SimInspiralFDMultiPhase hidden), checks
that the one-call route was taken, and times both. Then it runs the IMRPhenomXPHM DFT
tests of the tree's tests/gw/waveform_generator/test_wfg_m.py with this LAL.

Exit code 0 if the two routes agree to --rtol and the tests pass, 1 otherwise, 2 if the
LAL is not build_lal.sh's or the guard refused.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
for folder in (HERE, HERE.parent):
    if (folder / "guard.py").is_file():
        sys.path.insert(0, str(folder))
        break

import guard  # noqa: E402

DINGO_TESTS = "tests/gw/waveform_generator/test_wfg_m.py"
DINGO_TEST_SELECTION = "IMRPhenomXPHM and (dft or multi_phase or one_call)"


def summarise(values) -> dict:
    if not values:
        return {"n": 0}
    return {"n": len(values), "median": statistics.median(values), "max": max(values), "min": min(values)}


def best_time(function, repeats):
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        function()
        best = min(best, time.perf_counter() - start)
    return best


def largest_difference(arrays, references) -> float:
    """Largest |a - b| over matching arrays, relative to the largest |b| among them."""
    scale = max(float(np.abs(b).max()) for b in references)
    differences = [float(np.abs(np.asarray(a) - np.asarray(b)).max()) for a, b in zip(arrays, references)]
    difference = max(differences)
    return difference / scale if scale > 0 else (0.0 if difference == 0 else float("inf"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lal-site", required=True, help="site-packages of build_lal.sh's environment")
    parser.add_argument("--tree", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--proposal", required=True, help="Network samples (a Result file)")
    parser.add_argument("--event-data", required=True)
    parser.add_argument("--num-samples", type=int, default=50)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--rtol", type=float, default=1e-10)
    parser.add_argument("--skip-tests", action="store_true", help="Do not run the tree's DFT tests")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    # The patched LAL first, before anything imports the image's.
    lal_site = Path(args.lal_site).resolve()
    sys.path.insert(0, str(lal_site))
    import lal
    import lalsimulation as LS

    origin = Path(LS.__file__).resolve()
    if lal_site not in origin.parents or not hasattr(LS, "SimInspiralFDMultiPhase"):
        message = f"LAL FAILED: lalsimulation is {origin}, not build_lal.sh's with SimInspiralFDMultiPhase"
        print(message, file=sys.stderr)
        return 2
    try:
        provenance = guard.use_dingo(args.tree, args.commit)
    except guard.GuardError as error:
        print(f"GUARD FAILED: {error}", file=sys.stderr)
        return 2

    from bilby.core.prior import Constraint
    from dingo.gw.data.event_dataset import EventDataset
    from dingo.gw.prior import split_off_extrinsic_parameters
    from dingo.gw.result import Result

    result = Result(file_name=args.proposal)
    result.reset_event(EventDataset(file_name=args.event_data))
    result.use_base_domain = False
    likelihood = result.sampler_context.likelihood(use_base_domain=False)
    generator = likelihood.waveform_generator
    prior_keys = [k for k, v in result.prior.items() if not isinstance(v, Constraint)]
    keys = [k for k in prior_keys if k in result.samples.columns]
    rows = result.samples[keys].iloc[: args.num_samples].to_dict("records")

    multi_phase = LS.SimInspiralFDMultiPhase
    calls = {"multi_phase": 0}

    def counted(*a):
        calls["multi_phase"] += 1
        return multi_phase(*a)

    def repeated(function, *a):
        """function(*a) with LS.SimInspiralFDMultiPhase hidden, i.e. by the repeated calls."""
        current = LS.SimInspiralFDMultiPhase
        del LS.SimInspiralFDMultiPhase
        try:
            return function(*a)
        finally:
            LS.SimInspiralFDMultiPhase = current

    term_keys = ("kappa2_modes", "rho2opt_const", "rho2opt_crossterms")
    m_differences, term_differences = [], []
    m_times, m_times_repeated, term_times, term_times_repeated = [], [], [], []
    LS.SimInspiralFDMultiPhase = counted
    for row in rows:
        theta = {k: float(v) for k, v in row.items()}
        intrinsic = {k: float(v) for k, v in split_off_extrinsic_parameters(theta)[0].items()}
        at_zero = {**intrinsic, "phase": 0.0}
        full = {**theta, "phase": 0.0}

        pol_m = generator.generate_hplus_hcross_m(at_zero)
        pol_m_repeated = repeated(generator.generate_hplus_hcross_m, at_zero)
        names = [(m, name) for m in pol_m_repeated for name in pol_m_repeated[m]]
        arrays = [pol_m[m][name] for m, name in names]
        references = [pol_m_repeated[m][name] for m, name in names]
        m_differences.append(largest_difference(arrays, references))
        terms = likelihood.phase_grid_terms(full)
        terms_repeated = repeated(likelihood.phase_grid_terms, full)
        term_differences.append(max(largest_difference([terms[k]], [terms_repeated[k]]) for k in term_keys))

        def m_components_repeated():
            return repeated(generator.generate_hplus_hcross_m, at_zero)

        def terms_by_repeated_calls():
            return repeated(likelihood.phase_grid_terms, full)

        m_times.append(best_time(lambda: generator.generate_hplus_hcross_m(at_zero), args.repeats))
        m_times_repeated.append(best_time(m_components_repeated, args.repeats))
        term_times.append(best_time(lambda: likelihood.phase_grid_terms(full), args.repeats))
        term_times_repeated.append(best_time(terms_by_repeated_calls, args.repeats))
    LS.SimInspiralFDMultiPhase = multi_phase

    report = {
        "provenance": provenance,
        "lal": {
            "lal": lal.__version__,
            "lal_file": lal.__file__,
            "lalsimulation": LS.__version__,
            "lalsimulation_file": str(origin)
        },
        "inputs": {k: str(v) for k, v in vars(args).items()},
        "n": len(rows),
        "one_call_route_taken": calls["multi_phase"] >= 2 * len(rows),
        "multi_phase_calls": calls["multi_phase"],
        "m_components_max_difference": max(m_differences),
        "phase_grid_terms_max_difference": max(term_differences),
        "time_m_components_one_call_ms": summarise([1e3 * t for t in m_times]),
        "time_m_components_repeated_ms": summarise([1e3 * t for t in m_times_repeated]),
        "time_phase_grid_terms_one_call_ms": summarise([1e3 * t for t in term_times]),
        "time_phase_grid_terms_repeated_ms": summarise([1e3 * t for t in term_times_repeated]),
        "speedup_phase_grid_terms": summarise([r / o for r, o in zip(term_times_repeated, term_times)])
    }
    within = max(m_differences) <= args.rtol and max(term_differences) <= args.rtol
    agree = within and report["one_call_route_taken"]

    tests_passed = True
    if not args.skip_tests:
        import pytest

        os.chdir(args.tree)
        code = pytest.main([DINGO_TESTS, "-q", "-p", "no:cacheprovider", "-k", DINGO_TEST_SELECTION])
        report["dingo_tests"] = {
            "file": DINGO_TESTS,
            "selection": DINGO_TEST_SELECTION,
            "exit_code": int(code)
        }
        tests_passed = int(code) == 0

    report["ok"] = bool(agree and tests_passed)
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    shown = {k: v for k, v in report.items() if k not in ("provenance", "inputs")}
    print(json.dumps(shown, indent=1))
    print(f"{'OK' if report['ok'] else 'FAILED'}; report {args.output}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
