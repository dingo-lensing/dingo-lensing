# Speeding up importance sampling in the latest DINGO

Not for review/merge. Plan and log for four exact speed-ups to the synthetic phase in DINGO `main`, tested on the CIT cluster.

## Goal and constraints

- Target: The latest DINGO (upstream `main`), not the 0.9.8 that DINGO-Lensing pins.
- Only changes that leave results unchanged up to round-off: No fewer samples, no approximations, nothing that lowers efficiency.
- Only running time counts. Queue waits are out of scope.

## Background (16 October 2026)

- Juno's Exercise 3 models are plain normalising flows (no GNPE) for IMRPhenomXPHM with `spin_conversion_phase: 0.0`, on a uniform frequency domain from 20 to 448 Hz at 0.125 Hz (3,585 bins). See `parallelisation/model_info/`.
- In DINGO `main` (dd481d98), the synthetic phase (`SyntheticPhaseFactor` in `dingo/gw/inference/steps.py`) runs in three steps:
  1. Pool workers compute small per-sample terms, from 9 ordinary XPHM calls per sample (the DFT phase decomposition, #381).
  2. The main process evaluates the 5,001-point phase grid for all samples at once (`_phase_profile`, then `log_likelihood_from_phase_grid_terms`).
  3. Pool workers draw each phase from a scipy `rv_histogram`, after the whole (samples × 5,001) density array is copied out to them (`dingo/core/density/interpolation.py`).

  Importance sampling then reuses the cached log likelihood at the drawn phase (#422).
- Local benchmark of step 2 (`bench/grid_eval_main.py`, DINGO's code copied, one thread, on Kaili's Windows machine): 0.64 MB per sample every time, so about 32 GB at 50,000 samples. The time varied between runs, 0.7 to 1.6 ms per sample, so about 33 to 80 s at 50,000 samples. Not yet measured in the real pipeline or on the cluster.
- Estimate: The 9 XPHM calls cost about 40 to 55 ms per sample (4 to 6 ms per ordinary call, from Exercise 3's likelihood step).

## The four speed-ups

1. Grid evaluation in the workers, in chunks, so it runs in parallel and memory stays small.
2. Vectorised phase draws.
3. XPHM's precession computed once per sample instead of nine times (feasibility first).
4. Parameter conversion done once per sample instead of nine times.

## Plan

Items marked (Kaili) are decisions; items marked (cluster) are runs on the CIT cluster.

**0. Decide first**
- [x] 0.1 (Kaili) Fork dingo-gw/dingo on GitHub; one branch per speed-up, cut from the pinned baseline. Done: `git@github.com:KailibRyanDoney/dingo-effeciency.git`, `main` at dd481d98 (level with upstream). First branch: `kailib-synthetic-phase-in-workers` (speed-ups 1 and 2).
- [x] 0.2 (Kaili) Upstream or not: Decided 16 October: The work stays on our fork's branch, and at the end we decide what to push upstream. Tooling, benchmarks and results stay on this branch.
- [x] 0.3 Baseline: Upstream `main` at dd481d98 (12 October 2026), recorded in `BASELINE_COMMIT`; recompare if `main` moves.
- [ ] 0.4 Test data: The unlensed Exercise 3 model, so plain DINGO works without porting DINGO-Lensing.

**1. The right DINGO on the cluster**
- [x] 1.1 A dependencies-only image: The current recipe minus DINGO and DINGO-Lensing (`pytest` was already pinned). With no DINGO installed, a wrong path fails loudly instead of importing 0.9.8. DINGO-Lensing must never go into it, since it pins `dingo-gw==0.9.8`. Done in code: `container/dingo-deps.def`, `container/make_deps_requirements.py` (reuses the DINGO-Lensing image's generator unchanged; the pins differ only by `dingo-gw==0.9.8`), `container/build_deps_image.sh`. Not built yet: That is step 1.4.
- [x] 1.2 Ship DINGO as source with each job: `pack_dingo.py` writes `dingo_<commit10>.tar.gz`, a `git archive` of the commit plus `COMMIT.json` (commit, `git describe`, version) and `dingo/_version.py`. Without the version file DINGO stamps its outputs "dingo=None", which reads back as version 0.0.0 and sets off its backward-compatibility warning. Version as setuptools_scm gives it: `0.10.4.dev1+gdd481d98` for the baseline. The same commit gives the same bytes. Scripts put the unpacked tree first on `sys.path` themselves (`python -I` ignores `PYTHONPATH`). DINGO is pure Python, so no image rebuild per change.
- [x] 1.3 A guard every script runs first (`guard.py`): DINGO not yet imported; no dingo-gw or DINGO-Lensing installed or importable; `COMMIT.json` names the expected commit; `dingo` imports from inside the tree with the recorded version. Refuses (exit 2) otherwise, and returns the provenance for results (versions, host, CPU flags, threads). Also runs DINGO's own tests from a tree (`guard.py pytest`).
  Locally (Windows, Python 3.9): 59 unit tests pass (4 pytest-mode tests skipped; they run inside the image), 28 of 28 mutations caught (`tests/mutation_check.py`; 2 more need the image), and the real baseline packs (1.1 MB, sha256 74f0463d…) and passes the guard.
- [ ] 1.4 (cluster) Build and stage the image (`container/build_deps_image.sh`, which also runs the unit tests and the guard's mutation check inside it); run DINGO's test suite in it at the baseline commit (`run_dingo_tests.sh`, results in `results/dingo_tests/`).
- [ ] 1.5 (cluster) Check whether the latest DINGO can (a) load Juno's 0.9.7-trained unlensed model and draw network samples, and (b) read the network samples from the tutorial's non-lensed run (`dingo_EXP2_nonlensed`) and importance-sample a subset (`run_compat_check.sh`, results in `results/compat/`). If (b) fails, sample a fresh proposal with the latest DINGO.

**2. Baseline (latest DINGO, unchanged)**
- [ ] 2.1 Importance sampling on 50,000 samples, 32 CPUs, ample memory: Time and peak memory per step, to confirm or rule out the 32 GB grid step.
- [ ] 2.2 Per-sample microbenchmarks on one core (200 samples): One XPHM call, the nine-call DFT, projection, inner products, grid, draw; a profile of one sample's DFT separating LAL time from Python overhead.
- [ ] 2.3 (cluster) Run both on dedicated slots, on two node types.
- [ ] 2.4 Gate: Order the speed-ups by the measured split.

**3. Speed-ups 1 and 2**
- [ ] 3.1 Grid evaluation and draw in the workers, in chunks; workers return the phase, its log probability and the small terms for the cache. Uniform variates still drawn in the main process.
- [ ] 3.2 Vectorised inverse CDF reproducing scipy's `rv_histogram` exactly, including normalisation and edge cases.
- [ ] 3.3 Check the reverse direction (`log_prob` for given phases) and the phase-and-psi factor for the same pattern.
- [ ] 3.4 Tests: Same phases, log probabilities and cached likelihoods as the current code to round-off, on identical inputs and seeds; draws against `rv_histogram`; peak memory bounded as the sample count grows.
- [ ] 3.5 (cluster) Rerun 2.1 with the branch.

**4. Speed-up 4: Convert once per sample**
- [ ] 4.1 From 2.2's profile, confirm the converted LAL arguments differ across the nine calls only in phiRef.
- [ ] 4.2 Convert once, change only phiRef per call. Tests: Bit-identical m-components to the current DFT path.
- [ ] 4.3 (cluster) Microbenchmark and end-to-end rerun.

**5. Speed-up 3: Shared XPHM precession (feasibility first)**
- [ ] 5.1 Read LALSimulation's IMRPhenomXPHM code: Where phiRef enters the polarisation routine, and which parts do not depend on it.
- [ ] 5.2 (cluster) List what lalsuite 7.26's Python bindings expose for XPHM and time those parts against one full call.
- [ ] 5.3 (Kaili) Gate: Either (a) do it in DINGO with exposed functions, only if that reproduces LAL's polarisations to round-off, (b) propose a multi-phase XPHM function to LALSuite, or (c) stop.
- [ ] 5.4 If going ahead: The m-components match the current DFT path to round-off at all nine phases and sum to `generate_hplus_hcross`.

**6. Wrap up**
- [ ] 6.1 (cluster) End to end, baseline against the branch with everything in, same proposal and seed: Same phases, weights, ln Z and effective samples to round-off; time and peak memory per step.
- [ ] 6.2 DINGO's test suite passes on the branch, with new tests for each change.
- [ ] 6.3 Everything logged here.
- [ ] 6.4 If 0.2 is yes: An upstream issue about the grid memory first, then the PRs.

## Log

- 16 October 2026: Folder added with this plan and `bench/grid_eval_main.py`. Fork (0.1) in progress.
- 16 October 2026: Fork created (0.1), level with upstream `main` at dd481d98, so the baseline (0.3) holds. Local clone has `upstream` set to dingo-gw/dingo, fetch only. Branch `kailib-synthetic-phase-in-workers` cut from `main` locally; it gets pushed with its first commit.
- 16 October 2026: 1.1 to 1.3 written and tested locally (see the plan); runners for 1.4 and 1.5 ready. The fork on GitHub has no tags, so a clone of it needs `git fetch upstream --tags` before `pack_dingo.py` can compute the version.
