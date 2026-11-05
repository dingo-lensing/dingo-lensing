"""How many CPUs and threads the image's Python gets with a LAL, and how fast small numpy and torch workloads run, importing in run_suite.py's order: numpy, then LAL, then torch.

DINGO's suite took about 3x as long on the patched LAL in two launches (306 against 899 s, 342 against 858 s), all of it in torch tests (test_nsf 5 s against 256 s, test_enets 3.7 s against 140 s; the waveform tests ran at the same speed), using 0.98 of its 8 cores against 2.84. This shows whether the patched LAL and its libraries (LD_LIBRARY_PATH, as xphm_job.py sets it) pin the process to fewer CPUs or change the BLAS or OpenMP libraries numpy and torch run. run_thread_check.sh runs it in the image with each LAL.

    python -I thread_check.py [--lal-site DIR] [--label TEXT]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List

KEYWORDS = ("blas", "lapack", "mkl", "omp", "gsl", "fftw")
SETTINGS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "OPENBLAS_MAIN_FREE", "LD_LIBRARY_PATH")


def thread_cpus(tasks: Path = Path("/proc/self/task")) -> Dict[str, int]:
    """How many of this process's threads may run on each set of CPUs (their Cpus_allowed_list)."""
    counts: Dict[str, int] = {}
    for status in tasks.glob("*/status"):
        try:
            text = status.read_text(encoding="utf-8", errors="replace")
        except OSError:  # a thread that has ended
            continue
        for line in text.splitlines():
            if line.startswith("Cpus_allowed_list:"):
                cpus = line.split(":", 1)[1].strip()
                counts[cpus] = counts.get(cpus, 0) + 1
    return counts


def mapped(keywords=KEYWORDS, maps: Path = Path("/proc/self/maps")) -> List[str]:
    """The loaded shared libraries whose file names contain one of keywords."""
    files = set()
    for line in maps.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) == 6 and any(keyword in Path(parts[5].strip()).name.lower() for keyword in keywords):
            files.add(parts[5].strip())
    return sorted(files)


def best_of(work: Callable[[], object], repeats: int = 3) -> float:
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        work()
        times.append(time.perf_counter() - start)
    return min(times)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lal-site", help="A folder with the lal and lalsimulation packages, to go first on sys.path")
    parser.add_argument("--label", default="")
    args = parser.parse_args(argv)

    cpus = {"start": len(os.sched_getaffinity(0))}
    import numpy as np
    cpus["after numpy"] = len(os.sched_getaffinity(0))
    if args.lal_site:
        sys.path.insert(0, str(Path(args.lal_site).resolve()))
    import lalsimulation
    cpus["after LAL"] = len(os.sched_getaffinity(0))
    import torch
    cpus["after torch"] = len(os.sched_getaffinity(0))

    matrix = np.random.default_rng(1).random((600, 600))
    numpy_seconds = best_of(lambda: [matrix @ matrix for _ in range(10)])
    torch.manual_seed(1)
    network = torch.nn.Sequential(torch.nn.Linear(64, 128), torch.nn.ReLU(), torch.nn.Linear(128, 128), torch.nn.ReLU(), torch.nn.Linear(128, 1))
    batch = torch.randn(256, 64)

    def train():
        for _ in range(50):
            network.zero_grad()
            network(batch).sum().backward()

    torch_seconds = best_of(train)
    cpus["after the work"] = len(os.sched_getaffinity(0))

    lines = [f"== {args.label}"]
    lines.append("  " + ", ".join(f"{name}={os.environ[name]}" for name in SETTINGS if name in os.environ))
    lines.append(f"  lalsimulation: {lalsimulation.__file__}")
    lines.append("  CPUs allowed: " + ", ".join(f"{stage} {count}" for stage, count in cpus.items()))
    lines.append(f"  threads by the CPUs they may use: {thread_cpus()}")
    lines.append(f"  torch threads {torch.get_num_threads()}; numpy matmul {numpy_seconds:.3f} s; torch MLP {torch_seconds:.3f} s")
    lines += [f"  {line.strip()}" for line in torch.__config__.parallel_info().splitlines() if any(word in line for word in ("OpenMP", "MKL", "max_threads", "backend"))]
    try:
        from threadpoolctl import threadpool_info
    except ImportError:
        lines.append("  (no threadpoolctl)")
    else:
        lines += [f"  pool: {pool.get('internal_api')} {pool.get('version')}, {pool.get('num_threads')} threads, {pool.get('threading_layer', '-')}, {pool.get('filepath')}" for pool in threadpool_info()]
    lines += [f"  loaded: {path}" for path in mapped()]
    print("\n".join(lines), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
