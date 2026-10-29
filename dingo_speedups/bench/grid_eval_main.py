"""Time and peak memory of DINGO main's all-sample phase-grid evaluation.

Copies StationaryGaussianGWLikelihood.log_likelihood_from_phase_grid_terms and
steps._floored_density from DINGO main (dd481d98) and runs them on random terms of
the stacked shapes the synthetic phase passes in: N samples, m = -4..4 (M = 9),
8 deltas, 2 polarisation bases, one psi per sample, n_grid_phase phases.
Single thread, as in a Condor job with OMP_NUM_THREADS=1 (set before numpy loads).
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import sys
import time
import tracemalloc

import numpy as np


def log_likelihood_from_phase_grid_terms(log_Zn, terms, phases, psis):
    phases = np.asarray(phases)
    psis = np.asarray(psis)
    w = np.stack([np.cos(2 * psis), np.sin(2 * psis)], axis=-1)
    phasor_m = np.exp(-1j * terms["m_vals"][:, None] * phases[..., None, :])
    phasor_delta = np.exp(-1j * terms["deltas"][:, None] * phases[..., None, :])
    kappa2_b = (terms["kappa2_modes"] @ phasor_m).real
    crossterms = terms["rho2opt_crossterms"]
    cross = (crossterms.reshape(*crossterms.shape[:-3], 4, -1) @ phasor_delta).real
    rho2opt_bc = np.asarray(terms["rho2opt_const"])[..., None] + cross.reshape(*kappa2_b.shape[:-2], 2, 2, -1)
    kappa2 = np.einsum("...bg,...hb->...gh", kappa2_b, w, optimize=True)
    rho2opt = np.einsum("...bcg,...hb,...hc->...gh", rho2opt_bc, w, w, optimize=True)
    return log_Zn + kappa2 - 0.5 * rho2opt


def floored_density(log_density, uniform_weight):
    density = np.exp(log_density - np.amax(log_density, axis=-1, keepdims=True))
    return density + density.mean(axis=-1, keepdims=True) * uniform_weight


def run(n, n_grid=5001, seed=0):
    rng = np.random.default_rng(seed)
    cplx = lambda *s: rng.normal(size=s) + 1j * rng.normal(size=s)
    terms = {
        "m_vals": np.arange(-4, 5),
        "deltas": np.arange(1, 9),
        "kappa2_modes": cplx(n, 2, 9),
        "rho2opt_const": rng.normal(size=(n, 2, 2)),
        "rho2opt_crossterms": cplx(n, 2, 2, 8)
    }
    phases = np.linspace(0, 2 * np.pi, n_grid)
    psis = rng.uniform(0, np.pi, size=n)[:, None]
    tracemalloc.start()
    t0 = time.perf_counter()
    log_post = log_likelihood_from_phase_grid_terms(0.0, terms, phases, psis)[..., 0]
    dens = floored_density(log_post, 0.01)
    t1 = time.perf_counter()
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return t1 - t0, peak, dens.shape


def main():
    for n in [500, 1000, 2000]:
        dt, peak, shape = run(n)
        print(f"N = {n:5d}: {dt:6.2f} s, peak {peak / 1e9:6.2f} GB, output {shape}")
    dt, peak, _ = run(2000)
    scale = 50_000 / 2000
    print(f"Scaled to N = 50,000 (linear): ~{dt * scale:.0f} s on one core, ~{peak * scale / 1e9:.0f} GB peak")


if __name__ == "__main__":
    sys.exit(main())
