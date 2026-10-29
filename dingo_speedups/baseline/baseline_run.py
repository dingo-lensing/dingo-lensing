"""Step 2.1: One full unlensed run on the latest DINGO, timed and measured, as a Condor job.

Runs inside the dependencies-only image, from the job's scratch folder, where
Condor has put this script, guard.py, the DINGO tarball (pack_dingo.py), the model
and the event data file. It:

1. unpacks the tarball and checks it with guard.py;
2. loads the model and draws the network samples for the event, as dingo_pipe's
   sampling job does (50,000 by default), and saves them as that job does; or,
   with --proposal, takes the network samples from that file instead (e.g. an
   earlier run's), so two DINGO commits can be compared on identical samples;
3. frees the model, reloads the samples and importance-samples them as
   dingo_pipe's importance-sampling job does: Synthetic phase on the default
   5,001-point grid, then importance sampling from the cached likelihoods;
4. writes out/baseline.json: Each step's wall time and peak memory, the time
   spent in the parts of the synthetic phase (the per-sample terms in the
   workers, the grid evaluation and floor in the main process, the draws), the
   evidence and effective samples, and the provenance from guard.py. Both
   results are saved in out/ for later comparisons on the same samples.

Timing the parts wraps four DINGO functions with timers that call the originals
unchanged. Seeds follow dingo_pipe: SeedSequence([seed, 0]) for sampling, [seed, 1]
for importance sampling.

Exit code 0 on success, 1 on any failure (the traceback is in baseline.json),
2 if the guard refused or the tarball could not be unpacked.
"""
from __future__ import annotations

import argparse
import functools
import gc
import json
import os
import sys
import tarfile
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional

HERE = Path(__file__).resolve().parent
# guard.py sits next to this script in the job, and one folder up in the repository.
for folder in (HERE, HERE.parent):
    if (folder / "guard.py").is_file():
        sys.path.insert(0, str(folder))
        break

import guard  # noqa: E402

OUT = Path("out")
SYNTHETIC_PHASE = {"n_grid_phase": 5001, "uniform_weight": 0.01}  # dingo_pipe's PhaseRecoveryDefault


def parse_status(text: str, field: str) -> Optional[int]:
    """A /proc/<pid>/status memory field (e.g. VmHWM, in kB) in bytes, or None."""
    for line in text.splitlines():
        name, _, value = line.partition(":")
        if name.strip() == field:
            parts = value.split()
            if len(parts) == 2 and parts[1] == "kB" and parts[0].isdigit():
                return int(parts[0]) * 1024
    return None


def main_peak_bytes() -> Optional[int]:
    """This process's peak resident memory since the last reset (VmHWM)."""
    try:
        return parse_status(Path("/proc/self/status").read_text(), "VmHWM")
    except OSError:
        return None


def reset_main_peak() -> bool:
    """Reset VmHWM to the current resident size (Linux 4.0 and later)."""
    try:
        Path("/proc/self/clear_refs").write_text("5")
        return True
    except OSError:
        return False


def children_peak_bytes() -> Optional[int]:
    """The largest peak resident memory of any finished child (e.g. a Pool worker) so far."""
    try:
        import resource
    except ImportError:
        return None
    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024  # kB on Linux


def job_peak_bytes() -> Optional[int]:
    """The job's peak memory as its cgroup counts it (all processes), where visible."""
    for path in ("/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory/memory.max_usage_in_bytes"):
        try:
            return int(Path(path).read_text().split()[0])
        except (OSError, ValueError, IndexError):
            continue
    return None


class Stages:
    """Wall time and peak memory of each step."""

    def __init__(self):
        self.records: Dict[str, dict] = {}

    @contextmanager
    def stage(self, name: str):
        reset = reset_main_peak()
        start = time.perf_counter()
        try:
            yield
        finally:
            self.records[name] = {
                "seconds": round(time.perf_counter() - start, 3),
                "main_peak_bytes": main_peak_bytes(),
                "main_peak_is_for_this_step": reset,
                "children_peak_bytes_so_far": children_peak_bytes(),
                "job_peak_bytes_so_far": job_peak_bytes(),
            }


def wrap_timed(owner, name: str, records: Dict[str, dict], label: str) -> None:
    """Replace owner.name by a wrapper that calls it unchanged and adds up its time."""
    original = getattr(owner, name, None)
    if original is None:
        records[label] = {"found": False}
        return
    record = records[label] = {"found": True, "calls": 0, "seconds": 0.0, "main_peak_bytes": None}

    @functools.wraps(original)
    def timed(*args, **kwargs):
        start = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            record["calls"] += 1
            record["seconds"] = round(record["seconds"] + time.perf_counter() - start, 3)
            record["main_peak_bytes"] = main_peak_bytes()

    setattr(owner, name, timed)


def unpack(tarball: Path, destination: Path) -> Path:
    """Unpack a pack_dingo.py tarball; refuse members that would land outside destination."""
    destination = destination.resolve()
    with tarfile.open(tarball) as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if destination != target and destination not in target.parents:
                raise ValueError(f"{tarball} has a member outside the folder: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"{tarball} has a link, which pack_dingo.py never writes: {member.name}")
        if hasattr(tarfile, "data_filter"):
            archive.extractall(destination, filter="data")
        else:  # Python without extraction filters
            archive.extractall(destination)
    tree = destination / Path(tarball.name).name.replace(".tar.gz", "")
    if not (tree / "COMMIT.json").is_file():
        raise ValueError(f"Unpacking {tarball} did not give {tree}/COMMIT.json")
    return tree


def write_report(report: dict) -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "baseline.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tarball", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--model", help="The trained network (not needed with --proposal)")
    parser.add_argument("--proposal", help="Network samples to importance-sample instead of drawing new ones")
    parser.add_argument("--event-data", required=True)
    parser.add_argument("--num-samples", type=int, default=50_000)
    parser.add_argument("--batch-size", type=int, default=5_000)
    parser.add_argument("--num-processes", type=int, default=32)
    parser.add_argument("--seed", type=int, default=1)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    started = time.perf_counter()
    OUT.mkdir(exist_ok=True)  # first, so Condor always has the folder to transfer back
    args = parse_args(argv)
    stages = Stages()
    report = {
        "inputs": {k: str(v) for k, v in vars(args).items()},
        "environment": {name: os.environ.get(name) for name in guard.THREAD_VARIABLES},
        "stages": stages.records,
    }
    write_report(report)

    try:
        with stages.stage("unpack"):
            tree = unpack(args.tarball, Path("."))
        if (args.model is None) == (args.proposal is None):
            raise ValueError("Give exactly one of --model and --proposal")
        report["provenance"] = guard.use_dingo(tree, args.commit)
    except (guard.GuardError, ValueError, OSError, tarfile.TarError) as error:
        prefix = "GUARD FAILED" if isinstance(error, guard.GuardError) else "SETUP FAILED"
        report["error"] = f"{prefix}: {error}"
        report["traceback"] = traceback.format_exc()
        write_report(report)
        print(report["error"], file=sys.stderr)
        return 2

    try:
        with stages.stage("imports"):
            import numpy as np
            import torch
            from dingo.core.posterior_models.build_model import build_model_from_kwargs
            from dingo.core.utils.torchutils import seed_generators
            from dingo.gw.data.event_dataset import EventDataset
            from dingo.gw.inference import steps
            from dingo.gw.inference.sampler import GWComposedSampler
            from dingo.gw.likelihood import StationaryGaussianGWLikelihood
            from dingo.gw.result import Result
        report["torch_threads"] = torch.get_num_threads()

        with stages.stage("event_data"):
            event = EventDataset(file_name=args.event_data)
        if args.proposal is None:
            with stages.stage("model_load"):
                model = build_model_from_kwargs(filename=args.model, device="cpu", load_training_info=False)
            with stages.stage("network_sampling"):
                seed_generators(np.random.SeedSequence([args.seed, 0]), all_devices=True)
                sampler = GWComposedSampler.from_model(
                    model,
                    event.data,
                    event_metadata=event.settings
                )
                sampler.run_sampler(args.num_samples, batch_size=args.batch_size)
            with stages.stage("save_network_samples"):
                sampler.to_hdf5(label="network_samples", outdir=str(OUT))
            del sampler, model
            gc.collect()
            proposal = OUT / "network_samples.hdf5"
        else:
            proposal = Path(args.proposal)

        # The importance-sampling job starts from the saved samples, without the network.
        with stages.stage("importance_sampling_setup"):
            result = Result(file_name=str(proposal))
            if args.proposal is not None and args.num_samples < len(result.samples):
                # The first num_samples rows (a pre-flight), split off as dingo_pipe's n-parallel does.
                result = result.split(-(-len(result.samples) // args.num_samples))[0]
            result.reset_event(event)
            result.use_base_domain = False  # as the job sets it for a uniform-frequency model
        parts: Dict[str, dict] = {}
        report["synthetic_phase_parts"] = parts
        wrap_timed(steps, "_stacked_phase_grid_terms", parts, "per_sample_terms_in_workers")
        wrap_timed(
            StationaryGaussianGWLikelihood,
            "log_likelihood_from_phase_grid_terms",
            parts,
            "grid_evaluation_in_main"
        )
        wrap_timed(steps, "_floored_density", parts, "floor_in_main")
        wrap_timed(steps, "interpolated_sample_and_log_prob_multi", parts, "draws")
        # DINGO PR #454 evaluates each sample's grid and floor in the workers.
        wrap_timed(steps, "_phase_densities", parts, "grid_and_floor_in_workers")

        with stages.stage("synthetic_phase"):
            seed_generators(np.random.SeedSequence([args.seed, 1]), all_devices=True)
            result.sample_proposal_extensions(
                synthetic_parameters_kwargs={**SYNTHETIC_PHASE, "num_processes": args.num_processes}
            )
        with stages.stage("importance_sample"):
            result.importance_sample(num_processes=args.num_processes)
        with stages.stage("save_result"):
            result.to_file(file_name=str(OUT / "importance_sampling.hdf5"))

        report["evidence"] = {
            "num_samples": len(result.samples),
            "log_evidence": float(result.log_evidence),
            "log_evidence_std": float(result.log_evidence_std),
            "n_eff": float(result.n_eff),
            "sample_efficiency": float(result.sample_efficiency)
        }
    except Exception as error:  # recorded for the report, then a failed exit
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
        print(report["traceback"], file=sys.stderr)
        return 1
    finally:
        report["total_seconds"] = round(time.perf_counter() - started, 3)
        report["job_peak_bytes"] = job_peak_bytes()
        report["children_peak_bytes"] = children_peak_bytes()
        write_report(report)

    print(json.dumps({k: report[k] for k in ("evidence", "total_seconds")}, indent=2))
    for name, record in stages.records.items():
        peak_gb = (record["main_peak_bytes"] or 0) / 1e9
        print(f"{name:26s} {record['seconds']:9.1f} s   main peak {peak_gb:6.2f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
