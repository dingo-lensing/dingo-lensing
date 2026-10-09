# Parallelisation test log

Plans and results for the DINGO-Lensing parallelisation tests. Each test is
written up here before it runs; results are added underneath once it has.

## Option A: One config, several events

Route A runs several events from a single `dingo_lensing_pipe` config by listing
their segment start times in `--gps-file`. The pipeline then builds one Condor
workflow holding a full chain of jobs per event (data generation, sampling,
importance sampling, plot), and Condor runs the chains side by side.

### Common setup

- Code: DINGO-Lensing branch `kailib-parallelisation` (the launch script records
  the exact commit in `run_metadata.txt`), DINGO 0.9.8, bilby_pipe 1.8.0.
- Environment: Every job runs inside the container image
  `dingo-lensing_a4de31e72e_recipe-714878f_cpu.sif` (DINGO-Lensing `a4de31e`,
  every package at `dingo_env`'s version; see "Running jobs without `/home`"
  below), which each job receives from OSDF. `conda-env = /opt/dingo_env` names
  the environment inside it. `dingo_env` still builds the workflows on the
  access point, and `launch.sh` checks that the image holds the same commit.
- Submitted to Condor from `ldas-grid`. No local mode.
- `osg = True` with a requirements override: DINGO sends the image (and, to
  sampling, the model) to sampling and importance-sampling jobs only in osg mode,
  and osg mode also limits those jobs to remote-pool slots (`IS_GLIDEIN`), which
  `ldas-grid` does not submit to. Every config therefore also carries
  `extra-lines = [requirements = (HAS_SINGULARITY=?=True)]`, which replaces every
  job's requirements with the image's own, so all jobs stay on CIT's pool.
- Files: Configs and scripts in `option_a/`, unit tests in `tests/`.
- Run folder on the cluster: `~/dingo-lensing-runs/option_a/` (`T1/` and `T2/`).
  Large outputs stay there; logs and summaries come back through this branch.
- Launch: `bash option_a/launch.sh` from this folder. It runs the unit tests and
  the pre-flight checks, fetches the T1 data, reads both tests' frames and
  checks both models inside the image, builds the four workflows, checks every
  job in them (`check_workflow.py`: Runs inside the image, receives it with the
  access point's token, ends with the override, receives the model and data it
  reads, asks for enough disk) and only then submits.

### Things to remember (from the desk check)

1. If `trigger-time` is set, `--gps-file` is ignored and only one event runs.
2. `--gps-file` takes segment start times, not trigger times:
   start = trigger time − (duration − post-trigger duration).
3. `psd-dict` and `data-dict` apply to every event in a config.
4. Later events' data-generation jobs wait for event 0's.
5. `conda-env` decides which code the jobs run, on Condor as well as locally.
6. `n-parallel` is broken for lensed runs (the merge step crashes), so every
   test keeps the default of 1.
7. Lensed and non-lensed models need separate configs.
8. With a container, DINGO's sampling and importance-sampling jobs receive the
   image only in osg mode, and osg mode restricts them to remote-pool slots:
   Hence `osg = True` plus the requirements override.
9. Execute nodes no longer see `/home`, so every file a job reads must be sent
   with it: Data-generation jobs receive the model, frames and PSD files, and
   sampling jobs the model. T2's 4.5 GB model therefore travels to two jobs per
   event, T2 asks for 12 GB of disk, and input transfer is part of T2's timing.

### T1: Mechanism and correctness (toy model)

**Question:** Does listing an event twice give two independent analyses that
agree with each other and with the event run alone?

- Model: Exercise 2's lensed toy model (`two_images_BBH`, IMRPhenomD, H1 and L1,
  trained on a single O1 noise ASD near GW150914):
  `~/dingo_lensing_tutorial/materials/ex2_dingo_lensing/training/model_latest.pt`.
- Data: GW150914, from the 4096 s, 4 kHz GWOSC frame file per detector
  (fetched by the launch script). GWOSC serves the original O1 release
  (`H-H1_LOSC_4_V1-1126256640-4096.gwf` and the L1 equivalent), whose strain
  channel is `LOSC-STRAIN`. Each event's PSD is estimated from its own data:
  128 × 4 s immediately before the segment.
- Settings: 4 s duration, 2 s post-trigger, 10,000 samples, importance sampling
  on (the model infers the phase, so no synthetic-phase step), 8 CPUs per job.

| Test | Files | Event(s) |
|---|---|---|
| T1a | `T1a_single.ini` | GW150914 via `trigger-time = 1126259462.4` |
| T1b | `T1b_twice.ini`, `T1b_gps.txt` | GW150914 listed twice, segment start 1126259460.4 |

**Pass criteria**
1. T1b builds two complete chains with distinct names (`data0`, `data1`), and
   every job finishes.
2. No output file is written by more than one chain.
3. The two T1b copies agree with each other and with T1a within statistical
   uncertainty: The median and 90% interval of every parameter, and the log
   evidence where the sample efficiency allows a meaningful comparison.

The toy model is only valid for GW150914's noise, which is why T1 repeats the
same event. T1 tests the machinery, not science.

### T2: Realism and timing (production model)

**Question:** Do several events in one workflow reproduce the Exercise 3
reference, and how does the wall time of three events compare with one?

- Model: Juno's production lensed model (4.5 GB, IMRPhenomXPHM), the same file
  as Exercise 3.
- Data: Exercise 3's injection frames (`gwf_files/`) and PSD files, unchanged.
- Settings: Exercise 3's, unchanged apart from label, outdir and the Condor
  settings (the image, osg mode with the override, 12 GB of disk): 50,000
  samples, 32 CPUs for sampling and importance sampling, 8 s duration, 2 s
  post-trigger.

| Test | Files | Event(s) |
|---|---|---|
| T2a | `T2a_single.ini` | The injection via `trigger-time = 1384782888.63` |
| T2b | `T2b_three.ini`, `T2b_gps.txt` | The same injection listed three times, segment start 1384782882.63 |

**Pass criteria**
1. T2b builds three complete chains, and every job finishes.
2. All four results agree with the Exercise 3 reference (your local tutorial
   run: log evidence −5829.945 ± 0.014, sample efficiency 9.40%) within
   combined uncertainty.
3. Timing recorded for every job: Queue wait, input transfer, run time and CPU
   used, plus each workflow's total wall time, so T2b can be compared with T2a.

### Launch attempts

| Date (UTC) | Outcome |
|---|---|
| 2026-10-08 06:33 | Stopped at the T1 data step; nothing was submitted. The configs named the strain channel `GWOSC-4KHZ_R1_STRAIN`, but GWOSC served the original O1 release, whose channel is `LOSC-STRAIN` (read from the files themselves). Every earlier check passed: Unit tests, environment, code at `a4de31e`, inputs. Fixed in the T1 configs. |
| 2026-10-08 06:37 | All checks passed and all four workflows were submitted from `ldas-grid`. Code `a4de31e`, tests `ef1e845`. T1 data: 2,113,536 samples per detector (516 s at 4096 Hz), all finite. Model check: Our branch rebuilt both models' lensed waveform generators (`modwaveforms/two_images_BBH`; IMRPhenomD for the toy model, IMRPhenomXPHM for Juno's) and generated one prior draw from each. Workflows: T1a 4 jobs, T1b 8 (2 events), T2a 4, T2b 12 (3 events), every job running from `dingo_env`. DAGMan clusters: T1a 569226231, T1b 569226232, T2a 569226233, T2b 569226234. |
| 2026-10-08 06:40 | All four data-generation jobs went on hold before running: "invalid interpreter (/home/kailibryan.doney/.conda/envs/dingo_env/bin/python3.13) ... No such file or directory" on node1720, node1243, node2305 and node2268. CIT is disabling `/home` on execute nodes (IGWN Computing Guide, "shared filesystem" page), so `dingo_env` does not exist where jobs run. Next: Run every job inside a container image staged on OSDF (`container/`), the guide's recommended route for custom software. |
| 2026-10-08 09:35 | Relaunch with the EPNFS requirement (tests `79a77c6`, code `a4de31e`). All checks passed, including 2195 EPNFS nodes available and every built job ending with the EPNFS requirement. DAGMan clusters: T1a 569281751, T1b 569281752, T2a 569281753, T2b 569281754. The held attempt's run folder is kept as `option_a_held_20261008`. |
| 2026-10-08 09:38 | Held again, the same way: "invalid interpreter (.../dingo_env/bin/python3.13)", this time on node2436, node2273, node2292 and node2282. The submit files end with the EPNFS requirement, and node2436 does advertise `EPNFS = true`, yet the job could not see `/home/kailibryan.doney` (on the `home5` server). The IGWN guide also says "Do not point `executable` at, or activate, a Conda environment or virtual environment that lives under `/home`." EPNFS dropped; T1 and T2 move into the container. |
| 2026-10-08, after the smoke test | First launch inside the image (tests `ac977f5`). Stopped at the inputs check, because the EPNFS attempt's run folder was still at `option_a`; nothing was created or submitted. Every earlier check passed: 83 unit tests, code `a4de31e`, the staged image (same commit), all six inputs. |
| 2026-10-08 15:32 | Launched inside the image (tests `00a1914`, code `a4de31e`), after moving the EPNFS attempt's run folder to `option_a_held_epnfs_20261008`. Every check passed. Inside the image, gwpy read GWF with LALFrame: T1's GWOSC frames hold GPS 1126256640 to 1126260736 at 4096 Hz (the jobs need the 516 s from 1126258948.4), T2's injection frames hold 1384782874.63 to 1384782890.63 at 1024 Hz (the jobs need the 8 s segment from 1384782882.63), all finite. The image rebuilt both models' waveform generators. Every job of every workflow passed `check_workflow.py`: T1a 4 jobs, T1b 8, T2a 4, T2b 12. Submitted 15:39 UTC; DAGMan clusters T1a 569441103, T1b 569441104, T2a 569441115, T2b 569441121. At 15:46 UTC the first nodes had finished (T1a 1 of 4, T1b 3 of 8, T2a 1 of 4, T2b 1 of 12) and released their sampling jobs; nothing held. |

### Running jobs without `/home`: The container

T1 and T2 will run inside this image. (EPNFS nodes were tried first and did not
work for software in `/home`; see the launch attempts above.)

- `container/dingo-lensing.def`: CPU-only image with Python 3.13.13, every package
  at `dingo_env`'s exact version (`requirements-cpu.txt`, generated from
  `dingo_env_pip_list.txt` by `make_requirements.py`; PyTorch 2.13.0 and
  torchvision 0.28.0 as CPU builds; the 19 CUDA-only packages left out),
  modwaveforms at the commit `dingo_env` has, and DINGO-Lensing at one commit of
  our branch (editable install, since a normal install omits `dingo_lensing/pipe/`).
  `ligo-segments` 1.4.0 and `python-ligo-lw` 1.8.4 exist only as source on PyPI
  for Linux (conda-forge has no 1.8.4 for Python 3.13), so the build compiles them
  with conda-forge's `gcc` from a temporary prefix that is deleted afterwards.
- First build (recipe `97860b7`) stopped at exactly that: No `gcc` in the base image.
- Second build (recipe `83ecffc`) found conda-forge's GCC 16, which rejects their
  older C code: Since GCC 14, `-Wint-conversion` and similar warnings are errors
  by default (GCC 14 porting notes), whereas `dingo_env` was compiled with the
  cluster's older GCC. GCC 15 also changed the default C standard to `gnu23`
  (GCC 15 porting notes). The recipe now pins conda-forge's `gcc=13`, which has
  neither change.
- Third build (recipe `f8acded`) succeeded: 834 MB. Its self-test then failed
  correctly: Run from `~/dingo-lensing-sync`, Python imported the old package copy
  at that branch's root instead of the image's, because Apptainer shares the
  current folder and home by default. The checks now run from `/`, the self-test
  with `--contain` (no `/home`, as on execute nodes) and in Python's isolated
  mode, the model check without user site-packages.
- Fourth build (recipe `714878f`) passed every check: The self-test (with no
  `/home`), `pip check` ("No broken requirements found") and the model check, in
  which the image rebuilt both models' lensed waveform generators. Staged as
  `osdf:///igwn/cit/staging/kailibryan.doney/containers/dingo-lensing_a4de31e72e_recipe-714878f_cpu.sif`
  (834 MB). bilby_pipe warns that frameCPP is missing. dingo_env has neither
  frameCPP nor FrameL, so its frame reads (the T1 data check) went through gwpy
  4.0.2's third reader, LALFrame, which comes with `lalsuite` 7.26.15; the image
  has the same versions. The launch checks will read both tests' frames inside
  the image before anything is submitted.
- Smoke test: One job inside the staged image, cluster 569423966, submitted
  2026-10-08 14:52 UTC from `ldas-grid`. HTCondor accepted it with an advisory to
  use its newer container universe instead of `MY.SingularityImage`; bilby_pipe
  writes every job the older way, so T1 and T2's jobs will carry the same
  advisory. Passed on node1070: The job ran the image's Python inside Apptainer,
  imported DINGO, DINGO-Lensing (from the image, commit `a4de31e`) and its
  pipeline, LAL, modwaveforms and PyTorch 2.13.0+cpu, and ran
  `dingo_lensing_pipe --help`, on a node where `/home/kailibryan.doney` was not
  visible. So the OSDF transfer, the access point's token and the
  `(HAS_SINGULARITY=?=True)` requirement all work on CIT's pool.
- `container/build_image.sh`: Builds, self-tests and model-checks the image, then
  stages it at `/osdf/igwn/cit/staging/kailibryan.doney/containers/` under a name
  made of both commits (staged files can never be replaced).
- `container/smoke_test.sh`: One Condor job run inside the staged image exactly as
  bilby_pipe will run the pipeline's jobs, before T1 and T2.
- Tokens: The CIT access points issue job tokens themselves
  (`LOCAL_CREDMON_ISSUER = https://osdf.igwn.org/cit`), so jobs use
  `use_oauth_services = scitokens` and no browser login is needed.
- Models: Sent by Condor from their `/home` paths for now, because DINGO's grid
  mode requests a different token type for models on OSDF (finding 13).

### Analysis

`bash option_a/analyse.sh` on the cluster, once all four workflows have
finished. It runs `analyse_results.py` inside the image, reads only the run
folder, and writes `results/option_a/` in this branch: `summary.md` (a verdict
on each pass criterion, with the numbers behind it), `summary.json` (every
number) and the corner plots.

- Completion (T1.1, T2.1): Each DAG's own log (`dagman.out`) shows success with
  every node done, and each event has one sampling result, one
  importance-sampling result and one corner plot.
- Shared files (T1.2, also run on T2b): Every file the jobs write must name its
  event (`_data<i>_`), or the chains overwrite each other's. DINGO 0.9.8's data
  generation writes each detector's PSD to `data/<detector>_psd.txt` without the
  event index (`dingo/pipe/data_generation.py`), and every job sends its whole
  output folder back, so T1b and T2b are expected to fail this check: Harmless
  here, as the copies analyse identical data, but in a run of different events
  those files would hold only the last-finished event's PSDs (finding 15).
- Agreement (T1.3, T2.2): "Within statistical uncertainty" is tested three ways.
  1. Network samples: Every run of a test analyses identical data with the same
     network, so all its runs draw independently from one distribution. A
     two-sample KS test compares each parameter for every pair of runs (T1: 3
     pairs, T2: 6), with a Bonferroni correction holding the chance of any false
     alarm in a test at 1%. If the tutorial run's own results are on the
     cluster, T2's runs are also compared with its network samples.
  2. Log evidence: Every pair of runs, and for T2 the Exercise 3 reference, must
     agree within 3 sigma combined, using DINGO's error
     (sqrt((N - n_eff) / (N n_eff))), provided every run has at least 100
     effective samples; below that the error estimate is too rough. Sample
     efficiencies are reported next to the reference's 9.40%.
  3. The weighted median and 90% interval of every parameter, side by side, for
     reading.
  4. Event data: The copies' event data files (the strain and ASDs that both the
     network and the likelihood see) must be bit-identical, since identical
     inputs are what the comparisons above assume.
- Weights: For each run, how far the heaviest samples dominate (largest weight,
  share of the 10 largest, efficiency without the heaviest sample) and the
  heaviest sample itself. A proposal missing part of the posterior gives a few
  samples huge weights, which drag the efficiency down on their own. A sample
  efficiency outside a factor of 2 of the reference's is flagged CHECK: Not a
  test, as the efficiency has no reliable error when a few weights dominate.
- Verdicts: PASS, FAIL, or CHECK (passed, but something needs a look first).
- Timing (T2.3): From each job's Condor event log: Queue wait (first submission
  to the start of the successful run), input transfer, run time, output
  transfer, CPU used and cores used against requested, memory and disk used
  against requested, bytes received, attempts and CPU wasted on failed ones;
  and each workflow's wall time, overall and per event.

### Results

All four workflows finished on 2026-10-08 (DAG status 0, every node done),
about 8 min after submission for T1a and T1b, 2 h 46 min for T2a and 3 h 2 min
for T2b. Full analysis: `results/option_a/summary.md` (analysis `4f46c13`,
results `cead9f4`). A first analysis (`6e865f5`) gave the same verdicts but did
not test the sample efficiency, which the T2.2 criterion names; the weight and
event-data diagnostics were added to explain it.

| Criterion | Verdict |
|---|---|
| T1.1 Complete chains | PASS: T1a 4 of 4 nodes, T1b 8 of 8, every event's results present. |
| T1.2 No shared files | FAIL, as expected from DINGO's code: Every T1b data-generation job writes `data/H1_psd.txt` and `data/L1_psd.txt` (finding 15). The same holds for T2b. |
| T1.3 Agreement | PASS: Network samples agree (smallest KS p-value 0.119, ra, T1a vs T1b/1, over 39 tests; threshold 0.000256), and the event data are bit-identical. Log evidence not comparable: In every T1 run a single sample carries all the weight (about 1 effective sample of 10,000, with 60% of samples at zero weight), as expected of Exercise 2's toy model on real data. T1 tests the machinery, not the science. |
| T2.1 Complete chains | PASS: T2a 4 of 4 nodes, T2b 12 of 12. |
| T2.2 Agreement with Exercise 3 | PASS on review (the analysis flags CHECK). Network samples agree (smallest KS p-value 0.0537, theta_jn, T2a vs T2b/1, over 96 tests; threshold 0.000104; 0.0386 including Exercise 3's own network samples), the event data are bit-identical, and every log evidence agrees within 1.18 sigma, including with -5829.945 +- 0.014. Sample efficiencies: T2a 10.42%, T2b/0 9.02%, T2b/1 1.54%, T2b/2 0.27% (reference 9.40%). The two low ones each come from a single sample, with 1,666 and 4,204 times the mean weight; without it they are 9.83% and 7.91% (T2a 11.27%, T2b/0 10.26%). Those samples have ordinary likelihoods but low network density (log_prob -16.2 and -12.0): The network under-covers part of this posterior (finding 16), a property of the model rather than of option A. |
| T2.3 Timing recorded | PASS: See below. |

**Timing** (one run each; queue waits depend on the cluster's load at the time):

- Option A ran three events side by side for little extra wall time: T2b took
  3 h 2 min for three events against T2a's 2 h 46 min for one (per-event chains
  2 h 46 min, 2 h 58 min and 2 h 42 min); T1b took 7 min 36 s for two events
  against T1a's 7 min 38 s.
- Waiting dominated. All four T2 sampling jobs (32 CPUs, 32 GB) waited 2 h 22 min
  to 2 h 24 min for a slot, about 86% of T2's wall time; one T2b
  importance-sampling job (32 CPUs) waited another 15 min.
- Running took about 19 min per T2 event: Data generation about 1 min, plus up
  to 1 min receiving the 4.5 GB model and 0.8 GB image (5.4 GB in 17 to 55 s);
  sampling 1 min 9 s to 1 min 32 s; importance sampling 15 to 16 min; plot
  about 30 s.
- Importance sampling is the compute: 7.1 to 7.9 CPU-hours per event, on 28 to
  30 of its 32 cores (the synthetic-phase step). Sampling used only 11 to 19 of
  its 32 cores, for about 1.5 min, so bilby_pipe's `OMP_NUM_THREADS=1` (finding
  10) does not make it single-threaded. CPU in all: T2a 8.1 h, T2b 23.4 h.
- Requests far exceed use: Sampling asks for 32 GB (HTCondor recorded under
  0.5 GB, though its periodic sampling can miss a short job's peak: The model
  alone is 4.5 GB), plot jobs for 32 GB (used about 0.5 GB), importance
  sampling for 8 GB (used 2.5 to 3.2 GB). Disk: 5 GB used of 12 by the jobs that
  receive the model, as estimated. No job was evicted or retried.
