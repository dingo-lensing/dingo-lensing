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
- [x] 1.5 (cluster) Done 27 October (`results/compat/`), all checks pass. See the log for numbers. Check whether the latest DINGO can (a) load Juno's 0.9.7-trained unlensed model and draw network samples, and (b) read the network samples from the tutorial's non-lensed run (`dingo_EXP2_nonlensed`) and importance-sample a subset (`run_compat_check.sh`, results in `results/compat/`). If (b) fails, sample a fresh proposal with the latest DINGO.

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
- 16 October 2026: Image `dingo-deps_recipe-8f44d79_cpu.sif` built, every check passed, staged at `osdf:///igwn/cit/staging/kailibryan.doney/containers/dingo-deps_recipe-8f44d79_cpu.sif` (1.4, first part). DINGO's own test suite not yet run.
- 27 October 2026: The collaboration chose DINGO 0.10.x for the strong-lensing background task; Juno asked for injections processable per week on CIT. 1.5 run on ldas-grid (AMD EPYC 9475F, 24 usable cores, no thread limits), DINGO dd481d9846 = 0.10.4.dev1+gdd481d98, all checks pass:
  - Juno's 0.9.7-trained unlensed model loads (46 s); 14 inference parameters, psi included, phase not.
  - 200 fresh network samples in 66.6 s: Mostly fixed costs, so not a per-sample figure.
  - The 50,000 network samples of the tutorial's non-lensed 0.9.8 run load unchanged.
  - Importance sampling of 200 of them on 4 processes: Synthetic phase 5.40 s (about 100 ms per sample per core, an upper bound as Pool start-up weighs more on a small run), weighting 0.15 s from the cached likelihoods, ln Z = -5829.59 ± 0.10 (n_eff 66).
  - 0.9.8 on comparable machines: About 205 ms per sample per core (Exercise 3 rerun on the login node, probably 24 cores for its 32 processes) and 217 ms (Juno's 32-core run). So 0.10's importance sampling is about 2x faster per sample, the separate likelihood step having gone into the cache.
  - Estimate given to Juno (preliminary, unoptimised, both models, 50k samples each, scaled from our measured 0.9.8 CIT runs): About 8 to 12 core-hours per injection against about 17 to 18 for 0.9.8, i.e. 14 to 21 injections per core per week, about 7,000 to 10,000 a week at 500 cores; the like-for-like 2x puts it in the upper half of that cost range (about 7,500 a week at 500 cores).
  - Lead for later: LAL returns 4,097 bins (to 512 Hz) and DINGO truncates to 3,585 (448 Hz) on every waveform call, about 12% of the bins.
  - Juno's branch `juno_upsteam_compatibility` (e36716b) ports DINGO-Lensing to 0.10.3 and, by reading, covers both porting hazards found on 15 October (lensed likelihood through the sampler context; the nine-call mode method). Not yet tested here.
- 27 October 2026: 1.5 again with 5,000 samples on 8 processes (`NUM_SAMPLES=5000 NUM_PROCESSES=8`, same login node):
  - Synthetic phase 89.9 s for 4,988 samples, about 144 ms per sample per core (108 ms in the 200-sample run). Against 0.9.8's 205 to 217 ms, 0.10's importance sampling is about 1.5x faster per sample, not 2x. Weighting 0.17 s from the cache. ln Z = -5829.62 ± 0.024 (n_eff 1,301, efficiency 26%), consistent with the 200-sample value.
  - Network sampling 146 s for 5,000 samples against 66.6 s for 200: About 17 ms per extra sample, against about 2.5 ms per sample for 0.9.8 in the Exercise 3 rerun (125.7 s for 50,000) and 1.4 to 1.8 ms on option A's execute nodes. If that holds at 50,000, sampling takes about 15 minutes per model instead of about 2. Unexplained so far; the 2.1 run measures it at full size.
  - The "LALsimulation waveform longer than domain" warning repeats once per 32-sample chunk (DINGO 0.10 reseeds per chunk), not per process: Harmless.
  - Revised estimate: 0.10 unoptimised, about 14 to 20 core-hours per injection (both models), 8 to 12 injections per core per week, about 4,000 to 6,000 a week at 500 cores; the high cost end if the slow network sampling holds at full size. So roughly the same as 0.9.8 (about 5,000) until it is measured and the speed-ups are in.
- 27 October 2026, correction: Both compatibility runs above had no thread limits (OMP_NUM_THREADS unset, 24 usable cores on a shared login node), so each process could start up to 24 threads. The 2.1 pre-flight ran the same steps with OMP_NUM_THREADS=1, as pipeline jobs have it: Network sampling 4.8 s for 500 samples (against 66.6 s for 200 without the limit) and synthetic phase 6.4 s for 496 samples on 4 processes, about 52 ms per sample per core (against 108 to 144 ms). So the slow network sampling and the 1.5x figure were thread oversubscription, not DINGO 0.10. With the limit, importance sampling is about 4x faster per sample than 0.9.8's 205 to 217 ms (those 0.9.8 runs' thread settings are not recorded). Estimate back to about 7 to 12 core-hours per injection (14 to 24 per core per week, about 7,000 to 12,000 a week at 500 cores), the main open question being whether 0.10's network sampling runs on one thread under OMP_NUM_THREADS=1 (about 10 minutes per model if so). The 2.1 job measures it.
- 27 October 2026: Step 2.1 launched: Pre-flight passed (500 samples: imports 20.8 s, model load 21.6 s with a 6.6 GB peak, network sampling 4.8 s, synthetic phase 6.4 s, ln Z = -5829.72 ± 0.06); job submitted as cluster 571477171 (run folder ~/dingo-speedups-runs/baseline/20261027T070059Z).
- 27 October 2026: Step 2.1 written (`baseline/`): `baseline_run.py` (the job: 50,000 network samples, saved and reloaded as the pipeline does, then importance sampling; per-step wall time and peak memory, the synthetic phase's parts timed by wrapping four DINGO functions unchanged), `make_submit.py` (the smoke test's proven submit settings, 32 cores, 48 GB, priority 50, OMP_NUM_THREADS=1 as bilby_pipe sets), `launch_baseline.sh` (pre-flight of the same script with 500 samples in the image, then submit), `collect_baseline.py` (report plus Condor's timing and memory into `results/baseline/`). 77 unit tests pass locally.
