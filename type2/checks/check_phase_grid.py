import argparse
import time

import numpy as np
from bilby.core.prior import Constraint
from dingo.gw.likelihood import StationaryGaussianGWLikelihood

import dingo_lensing
from dingo_lensing.result import LensedGWResult

parser = argparse.ArgumentParser()
parser.add_argument("result")
parser.add_argument("--num-samples", type=int, default=200)
args = parser.parse_args()
print(f"dingo_lensing from {dingo_lensing.__file__}")

result = LensedGWResult(file_name=args.result)
result._build_likelihood()
likelihood = result.likelihood
likelihood.phase_grid = np.linspace(0, 2 * np.pi, 5001)
keys = [k for k, v in result.prior.items() if not isinstance(v, Constraint)]
theta = result.samples[keys].iloc[: args.num_samples]
dingo_grid = StationaryGaussianGWLikelihood._log_likelihood_phase_grid_mode_decomposed

max_abs_diff = 0.0
time_dingo = 0.0
time_vectorised = 0.0
for row in theta.to_dict("records"):
    t0 = time.perf_counter()
    expected = dingo_grid(likelihood, dict(row))
    t1 = time.perf_counter()
    grid = likelihood._log_likelihood_phase_grid_mode_decomposed(dict(row))
    t2 = time.perf_counter()
    max_abs_diff = max(max_abs_diff, float(np.max(np.abs(grid - expected))))
    time_dingo += t1 - t0
    time_vectorised += t2 - t1

n = len(theta)
print(f"{n} samples, max |difference| {max_abs_diff:.3e}, log L around {np.median(expected):.1f}")
print(f"DINGO loop {1e3 * time_dingo / n:.1f} ms per sample, vectorised {1e3 * time_vectorised / n:.1f} ms per sample")
