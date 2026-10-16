"""Can the latest DINGO use our existing inputs? Step 1.5 of test_log.md.

Runs inside the dependencies-only image, from a shipped DINGO tree (checked by
guard.py before anything imports DINGO):

    python -I compat_check.py --tree DIR --commit SHA --model MODEL --event-data EVENT \\
        [--proposal SAMPLES] [--num-samples 200] [--num-processes 4] [--seed 1] --output OUT.json

Each check is timed and, if it fails, recorded with its traceback:

1. model: Juno's model (trained with DINGO 0.9.7) loads.
2. event_data: The event data file from the earlier pipeline run loads.
3. network_sampling: The latest DINGO draws network samples from the model for
   that event, as its sampling job does.
4. old_proposal: The network samples from the earlier (0.9.x) run load as a Result.
5. importance_sampling: A subset of those samples (or of the fresh ones, if 4
   failed) goes through the importance-sampling job's steps: Event data,
   synthetic phase on dingo_pipe's default 5,001-point grid, importance sampling.

Seeds follow dingo_pipe (SeedSequence([seed, 0]) for sampling, [seed, 1] for
importance sampling). Exit code 0 if every check that ran passed, 1 otherwise,
2 if the guard refused.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Callable, Dict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import guard  # noqa: E402

# dingo_pipe's default for networks that do not infer the phase (PhaseRecoveryDefault).
SYNTHETIC_PHASE = {"n_grid_phase": 5001, "uniform_weight": 0.01}


def timed(name: str, checks: Dict[str, dict], function: Callable):
    """Run function, record whether it worked and how long it took; return its value or None."""
    start = time.perf_counter()
    try:
        value = function()
    except Exception:  # recorded, not raised: The report should cover every check
        checks[name] = {"ok": False, "seconds": round(time.perf_counter() - start, 3), "error": traceback.format_exc()}
        return None
    checks[name] = {"ok": True, "seconds": round(time.perf_counter() - start, 3)}
    return value


def exit_code(checks: Dict[str, dict]) -> int:
    return 0 if checks and all(check["ok"] for check in checks.values()) else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tree", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--event-data", required=True)
    parser.add_argument("--proposal", help="Network samples (Result file) from the earlier run")
    parser.add_argument("--num-samples", type=int, default=200)
    parser.add_argument("--num-processes", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        provenance = guard.use_dingo(args.tree, args.commit)
    except guard.GuardError as error:
        print(f"GUARD FAILED: {error}", file=sys.stderr)
        return 2

    import numpy as np
    from dingo.core.posterior_models.build_model import build_model_from_kwargs
    from dingo.core.utils.torchutils import seed_generators
    from dingo.gw.data.event_dataset import EventDataset
    from dingo.gw.inference.sampler import GWComposedSampler
    from dingo.gw.result import Result

    checks: Dict[str, dict] = {}
    report = {
        "provenance": provenance,
        "inputs": {k: getattr(args, k) for k in ("model", "event_data", "proposal", "num_samples", "num_processes", "seed")},
        "checks": checks,
    }

    model = timed("model", checks, lambda: build_model_from_kwargs(
        filename=args.model, device="cpu", load_training_info=False))
    if model is not None:
        data_settings = (getattr(model, "metadata", None) or {}).get("train_settings", {}).get("data", {})
        checks["model"]["inference_parameters"] = data_settings.get("inference_parameters")

    event = timed("event_data", checks, lambda: EventDataset(file_name=args.event_data))

    fresh = None
    if model is not None and event is not None:
        def sample():
            seed_generators(np.random.SeedSequence([args.seed, 0]), all_devices=True)
            sampler = GWComposedSampler.from_model(model, event.data, event_metadata=event.settings)
            sampler.run_sampler(args.num_samples, batch_size=args.num_samples)
            return sampler.to_result()

        fresh = timed("network_sampling", checks, sample)
        if fresh is not None:
            checks["network_sampling"].update(
                num_samples=len(fresh.samples),
                has_log_prob="log_prob" in fresh.samples.columns,
                has_phase="phase" in fresh.samples.columns,
            )

    old = None
    if args.proposal:
        old = timed("old_proposal", checks, lambda: Result(file_name=args.proposal))
        if old is not None:
            checks["old_proposal"].update(
                num_samples=len(old.samples),
                has_log_prob="log_prob" in old.samples.columns,
                has_phase="phase" in old.samples.columns,
                version=getattr(old, "version", None),
            )

    source, proposal = ("old_proposal", old) if old is not None else ("network_sampling", fresh)
    if proposal is not None and event is not None:
        def importance():
            subset = proposal.split(max(1, len(proposal.samples) // args.num_samples))[0]
            subset.reset_event(event)
            subset.use_base_domain = False  # as the job sets it for a uniform-frequency model
            seed_generators(np.random.SeedSequence([args.seed, 1]), all_devices=True)
            start = time.perf_counter()
            subset.sample_proposal_extensions(
                synthetic_parameters_kwargs={**SYNTHETIC_PHASE, "num_processes": args.num_processes}
            )
            middle = time.perf_counter()
            subset.importance_sample(num_processes=args.num_processes)
            end = time.perf_counter()
            return subset, round(middle - start, 3), round(end - middle, 3)

        outcome = timed("importance_sampling", checks, importance)
        if outcome is not None:
            subset, synthetic_seconds, weighting_seconds = outcome
            checks["importance_sampling"].update(
                source=source,
                num_samples=len(subset.samples),
                synthetic_phase_seconds=synthetic_seconds,
                importance_sample_seconds=weighting_seconds,
                log_evidence=float(subset.log_evidence),
                log_evidence_std=float(subset.log_evidence_std),
                n_eff=float(subset.n_eff),
                sample_efficiency=float(subset.sample_efficiency),
            )

    Path(args.output).write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    for name, check in checks.items():
        extra = {k: v for k, v in check.items() if k not in ("ok", "error")}
        print(f"{'PASS' if check['ok'] else 'FAIL'} {name}: {extra}")
        if not check["ok"]:
            print(check["error"])
    return exit_code(checks)


if __name__ == "__main__":
    sys.exit(main())
