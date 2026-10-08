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
- Environment: `dingo_env` (`/home/kailibryan.doney/.conda/envs/dingo_env`),
  set as `conda-env` in every config so all jobs run our branch.
- Submitted to Condor from `ldas-grid`. No local mode.
- Jobs run only on execute nodes that still mount `/home` (where `dingo_env`
  lives): Every config carries
  `extra-lines = [requirements = (TARGET.EPNFS =?= True)]`, and `launch.sh` checks
  that every built job ends with that requirement. 2195 machines advertised
  `EPNFS` on 2026-10-08. The guide's dedicated access point,
  `epnfs.ligo.caltech.edu`, does not resolve from `ldas-grid`.
- Files: Configs and scripts in `option_a/`, unit tests in `tests/`.
- Run folder on the cluster: `~/dingo-lensing-runs/option_a/` (`T1/` and `T2/`).
  Large outputs stay there; logs and summaries come back through this branch.
- Launch: `bash option_a/launch.sh` from this folder. It runs the unit tests and
  all pre-flight checks, fetches the data, builds the four workflows, checks
  them and only then submits.

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
- Settings: Exercise 3's, unchanged apart from Condor, `conda-env`, label and
  outdir (50,000 samples, 32 CPUs for sampling and importance sampling,
  8 s duration, 2 s post-trigger).

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

### Running jobs without `/home`: The container

For production; T1 and T2 use the EPNFS nodes above in the meantime.

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
  cluster's older GCC. Documented fix: `-fpermissive`. Not yet retried.
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

### Results

Not run yet.
