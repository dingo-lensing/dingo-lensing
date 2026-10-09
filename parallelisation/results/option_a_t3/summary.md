# Option A results

Analysed 2026-10-09T03:52:39 from `/home/kailibryan.doney/dingo-lensing-runs/option_a_t3`.

```
date: 2026-10-09T08:41:38Z
host: ldas-grid
suite: T3
code: kailib-parallelisation at 1d7c4771b49fd0ce10ab1c7542ed4c5fecbbe73c
tests: local-tests-sync at c7ea3099f4c00b6a8eff350838cac8b64b444696
image: osdf:///igwn/cit/staging/kailibryan.doney/containers/dingo-lensing_1d7c4771b4_recipe-ff6622d_cpu.sif
workflows built with: /home/kailibryan.doney/.conda/envs/dingo_env
in the image: dingo 0.9.8, bilby_pipe 1.8.0, torch 2.13.0+cpu
```

## Verdicts

CHECK means the test passed but something needs a look before calling it a pass.

| Criterion | Verdict | Evidence |
|---|---|---|
| T3.1 Every chain completes | PASS | T3a 4 of 4 nodes done, T3b 4 of 4 nodes done, T3c 8 of 8 nodes done; every event has its sampling and importance-sampling results and corner plot |
| T3.2 No output file is written by more than one chain | PASS | T3c: Every output names its event |
| T3.3 GW150914 in T3c matches its single-event run | FAIL | Network samples: smallest KS p-value 0.0275 (luminosity_distance, T3a vs T3c/0) against a threshold of 0.000769 over 13 tests; log evidence not compared, since a run has fewer than 100 effective samples; event data DIFFER between runs in waveform/H1, waveform/L1; PSD files byte-identical |
| T3.3 GW151012 in T3c matches its single-event run | PASS | Network samples: smallest KS p-value 0.00762 (theta_jn, T3b vs T3c/1) against a threshold of 0.000769 over 13 tests; log evidence not compared, since a run has fewer than 100 effective samples; event data bit-identical across runs; PSD files byte-identical |
| T3.4 The two events' data really differ | PASS | T3c/0 vs T3c/1: event data differ: True, PSD files differ: True |
| T3.5 Timing recorded for every job | PASS | From each job's Condor log |
| Also: GW150914's event data match T1a's from the first launch | PASS | Bit-identical, so the fixes leave data handling unchanged |

## GW150914: Agreement between runs

Network samples, two-sample KS per parameter: 13 tests over 2 runs, Bonferroni threshold 0.000769 (0.01 family-wise). Smallest p-value per pair:

| Pair | Smallest p | Parameter | KS statistic |
|---|---|---|---|
| T3a vs T3c/0 | 0.0275 | luminosity_distance | 0.0207 |

| Run | ln Z | sigma | Effective samples | Efficiency |
|---|---|---|---|---|
| T3a | -5548.706 | 1.000 | 1.0 of 10000 | 0.01% |
| T3c/0 | -5576.335 | 1.000 | 1.0 of 10000 | 0.01% |

| Pair | Difference in ln Z | Combined sigma | Disagreement (sigma) |
|---|---|---|---|
| T3a vs T3c/0 | +27.628 | 1.414 | 19.54 |

Event data (SHA-256 of every dataset in each event data file's data group): DIFFERENT between runs, in waveform/H1, waveform/L1.

### Weights

In units of each run's mean weight. A few heavy samples (a proposal missing part of the posterior) drag the efficiency down on their own; removing the heaviest then restores much of it.

| Run | Efficiency | Largest weight | Share of the 10 largest | Efficiency without the heaviest | Zero weights |
|---|---|---|---|---|---|
| T3a | 0.01% | 1e+04 | 100.00% | 0.01% | 6058 |
| T3c/0 | 0.01% | 1e+04 | 100.00% | 0.01% | 6038 |

The heaviest sample of each run:

| Column | T3a | T3c/0 |
|---|---|---|
| chirp_mass | 26.1334 | 25.4047 |
| mass_ratio | 0.212523 | 0.453852 |
| chi_1 | 0.0681275 | 0.0400155 |
| chi_2 | 0.447636 | 0.0300465 |
| theta_jn | 2.0165 | 1.26527 |
| dec | -0.888449 | 0.149033 |
| ra | 0.931431 | 1.3588 |
| geocent_time | 0.0144993 | 0.0402059 |
| luminosity_distance | 344.671 | 448.292 |
| psi | 2.40609 | 2.89778 |
| phase | 4.09273 | 4.23575 |
| lensing_delta_t | 0.0228852 | 0.0618486 |
| mu_rel | 0.134416 | 0.48729 |
| log_prob | -13.7237 | -10.1506 |
| log_prior | -12.8278 | -11.4186 |
| log_likelihood | -5540.39 | -5565.86 |
| weights | 10000 | 10000 |

Weighted median [5%, 95%] of every parameter after importance sampling:

| Parameter | T3a | T3c/0 |
|---|---|---|
| chirp_mass | 26.13 [26.13, 26.13] | 25.4 [25.4, 25.41] |
| mass_ratio | 0.2125 [0.2116, 0.2138] | 0.4539 [0.4538, 0.4539] |
| chi_1 | 0.06813 [0.06811, 0.06816] | 0.04002 [0.04001, 0.04005] |
| chi_2 | 0.4476 [0.4475, 0.4486] | 0.03005 [0.02999, 0.03018] |
| theta_jn | 2.017 [2.016, 2.017] | 1.265 [1.264, 1.265] |
| dec | -0.8884 [-0.8896, -0.8876] | 0.149 [0.1478, 0.15] |
| ra | 0.9314 [0.9307, 0.9327] | 1.359 [1.358, 1.36] |
| geocent_time | 0.0145 [0.01443, 0.01455] | 0.04021 [0.0402, 0.04022] |
| luminosity_distance | 344.7 [344.6, 344.7] | 448.3 [448.3, 448.6] |
| psi | 2.406 [2.406, 2.407] | 2.898 [2.893, 2.902] |
| phase | 4.093 [4.092, 4.093] | 4.236 [4.236, 4.236] |
| lensing_delta_t | 0.02289 [0.02286, 0.02289] | 0.06185 [0.06184, 0.06193] |
| mu_rel | 0.1344 [0.1344, 0.135] | 0.4873 [0.4867, 0.4876] |

## GW151012: Agreement between runs

Network samples, two-sample KS per parameter: 13 tests over 2 runs, Bonferroni threshold 0.000769 (0.01 family-wise). Smallest p-value per pair:

| Pair | Smallest p | Parameter | KS statistic |
|---|---|---|---|
| T3b vs T3c/1 | 0.00762 | theta_jn | 0.0236 |

| Run | ln Z | sigma | Effective samples | Efficiency |
|---|---|---|---|---|
| T3b | -5735.541 | 0.418 | 5.7 of 10000 | 0.06% |
| T3c/1 | -5734.765 | 0.928 | 1.2 of 10000 | 0.01% |

| Pair | Difference in ln Z | Combined sigma | Disagreement (sigma) |
|---|---|---|---|
| T3b vs T3c/1 | -0.776 | 1.018 | 0.76 |

Event data (SHA-256 of every dataset in each event data file's data group): bit-identical across T3b, T3c/1.

### Weights

In units of each run's mean weight. A few heavy samples (a proposal missing part of the posterior) drag the efficiency down on their own; removing the heaviest then restores much of it.

| Run | Efficiency | Largest weight | Share of the 10 largest | Efficiency without the heaviest | Zero weights |
|---|---|---|---|---|---|
| T3b | 0.06% | 3352 | 84.16% | 0.07% | 5743 |
| T3c/1 | 0.01% | 9274 | 97.66% | 0.10% | 5720 |

The heaviest sample of each run:

| Column | T3b | T3c/1 |
|---|---|---|
| chirp_mass | 36.7753 | 53.7455 |
| mass_ratio | 0.994063 | 0.835384 |
| chi_1 | -0.354615 | -0.015063 |
| chi_2 | 0.0116352 | -0.16253 |
| theta_jn | 1.36228 | 2.33601 |
| dec | -0.631063 | -0.826881 |
| ra | 0.582723 | 0.737468 |
| geocent_time | 0.0432586 | 0.0246297 |
| luminosity_distance | 849.681 | 792.375 |
| psi | 2.22639 | 0.700211 |
| phase | 0.565422 | 1.36265 |
| lensing_delta_t | 0.0654733 | 0.0981622 |
| mu_rel | 0.692886 | 0.915712 |
| log_prob | -15.1327 | -14.4427 |
| log_prior | -13.001 | -12.3796 |
| log_likelihood | -5729.56 | -5727.69 |
| weights | 3352.08 | 9273.75 |

Weighted median [5%, 95%] of every parameter after importance sampling:

| Parameter | T3b | T3c/1 |
|---|---|---|
| chirp_mass | 27.65 [20.24, 36.78] | 53.74 [26.35, 53.76] |
| mass_ratio | 0.571 [0.1331, 0.9947] | 0.8354 [0.7547, 0.8354] |
| chi_1 | -0.1856 [-0.3548, 0.3424] | -0.01506 [-0.01521, -0.01469] |
| chi_2 | 0.01163 [-0.5966, 0.1613] | -0.1625 [-0.1627, -0.162] |
| theta_jn | 1.549 [1.362, 1.686] | 2.336 [1.699, 2.337] |
| dec | -0.3001 [-0.6703, 0.949] | -0.8268 [-0.8274, -0.01499] |
| ra | 1.14 [0.5814, 5.528] | 0.7379 [0.7335, 2.377] |
| geocent_time | 0.04327 [-0.0399, 0.05643] | 0.02463 [0.02461, 0.0247] |
| luminosity_distance | 849.3 [604.4, 952.6] | 792.4 [792.2, 792.6] |
| psi | 2.058 [0.4493, 2.586] | 0.7002 [0.7, 0.8357] |
| phase | 0.9019 [0.5609, 5.269] | 1.363 [1.361, 1.364] |
| lensing_delta_t | 0.06546 [0.02294, 0.08181] | 0.09816 [0.07405, 0.09819] |
| mu_rel | 0.4217 [0.04546, 0.712] | 0.9157 [0.2485, 0.9164] |

## Timing

**T3a** (1 event(s)): Wall time 0:08:42 from first submission to last job; per event: event 0 0:08:42. CPU 0.03 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T3a_data0_1126259462-4_generation_arg_0 | 0:00:47 | 0:00:16 | 0:01:54 | 0:00:00 | 0:00:59 | 0.52 / 1 | 250 / 8192 | 1.3 / 5 | 1.44 | 1 |
| T3a_data0_1126259462-4_sampling_arg_0 | 0:01:04 | 0:00:08 | 0:00:20 | 0:00:00 | 0:00:08 | 0.4 / 8 | 0 / 8192 | 0.87 / 5 | 0.935 | 1 |
| T3a_data0_1126259462-4_importance_sampling_arg_0 | 0:01:04 | 0:00:08 | 0:00:24 | 0:00:00 | 0:00:18 | 0.75 / 8 | 534 / 8192 | 0.82 / 5 | 0.875 | 1 |
| T3a_data0_1126259462-4_importance_sampling_plot_arg_0 | 0:01:30 | 0:00:05 | 0:00:37 | 0:00:00 | 0:00:18 | 0.49 / 1 | 430 / 32768 | 0.81 / 5 | 0.875 | 1 |

**T3b** (1 event(s)): Wall time 0:08:41 from first submission to last job; per event: event 0 0:08:41. CPU 0.03 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T3b_data0_1128678900-4_generation_arg_0 | 0:00:48 | 0:00:18 | 0:01:45 | 0:00:00 | 0:01:04 | 0.61 / 1 | 255 / 8192 | 1.3 / 5 | 1.44 | 1 |
| T3b_data0_1128678900-4_sampling_arg_0 | 0:01:08 | 0:00:09 | 0:00:21 | 0:00:00 | 0:00:08 | 0.38 / 8 | 0 / 8192 | 0.87 / 5 | 0.935 | 1 |
| T3b_data0_1128678900-4_importance_sampling_arg_0 | 0:01:05 | 0:00:08 | 0:00:23 | 0:00:00 | 0:00:19 | 0.83 / 8 | 533 / 8192 | 0.82 / 5 | 0.875 | 1 |
| T3b_data0_1128678900-4_importance_sampling_plot_arg_0 | 0:01:29 | 0:00:04 | 0:00:37 | 0:00:00 | 0:00:18 | 0.49 / 1 | 396 / 32768 | 0.82 / 5 | 0.875 | 1 |

**T3c** (2 event(s)): Wall time 0:09:22 from first submission to last job; per event: event 0 0:08:43, event 1 0:06:12. CPU 0.06 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T3c_data0_1126259462-4_generation_arg_0 | 0:00:47 | 0:00:24 | 0:01:52 | 0:00:00 | 0:01:03 | 0.56 / 1 | 239 / 8192 | 1.3 / 5 | 1.44 | 1 |
| T3c_data1_1128678900-4_generation_arg_0 | 0:00:40 | 0:00:18 | 0:02:15 | 0:00:00 | 0:01:07 | 0.5 / 1 | 142 / 8192 | 1.3 / 5 | 1.44 | 1 |
| T3c_data0_1126259462-4_sampling_arg_0 | 0:00:59 | 0:00:09 | 0:00:20 | 0:00:00 | 0:00:08 | 0.4 / 8 | 0 / 8192 | 0.87 / 5 | 0.935 | 1 |
| T3c_data1_1128678900-4_sampling_arg_0 | 0:00:14 | 0:00:09 | 0:00:21 | 0:00:00 | 0:00:09 | 0.43 / 8 | 0 / 8192 | 0.87 / 5 | 0.935 | 1 |
| T3c_data0_1126259462-4_importance_sampling_arg_0 | 0:01:05 | 0:00:08 | 0:00:21 | 0:00:00 | 0:00:18 | 0.86 / 8 | 529 / 8192 | 0.82 / 5 | 0.875 | 1 |
| T3c_data1_1128678900-4_importance_sampling_arg_0 | 0:00:23 | 0:00:08 | 0:00:23 | 0:00:00 | 0:00:19 | 0.83 / 8 | 452 / 8192 | 0.82 / 5 | 0.875 | 1 |
| T3c_data0_1126259462-4_importance_sampling_plot_arg_0 | 0:01:34 | 0:00:05 | 0:00:38 | 0:00:00 | 0:00:19 | 0.5 / 1 | 404 / 32768 | 0.81 / 5 | 0.875 | 1 |
| T3c_data1_1128678900-4_importance_sampling_plot_arg_0 | 0:00:15 | 0:00:05 | 0:00:36 | 0:00:00 | 0:00:18 | 0.5 / 1 | 409 / 32768 | 0.81 / 5 | 0.875 | 1 |

