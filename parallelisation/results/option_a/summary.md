# Option A results

Analysed 2026-10-08T20:17:55 from `/home/kailibryan.doney/dingo-lensing-runs/option_a`.

```
date: 2026-10-08T15:32:00Z
host: ldas-grid
code: kailib-parallelisation at a4de31e72e75c9a38a100c2555a902d1eadc2f61
tests: local-tests-sync at 00a1914df6d8a2136f0068de06265e85832e1d37
image: osdf:///igwn/cit/staging/kailibryan.doney/containers/dingo-lensing_a4de31e72e_recipe-714878f_cpu.sif
workflows built with: /home/kailibryan.doney/.conda/envs/dingo_env
in the image: dingo 0.9.8, bilby_pipe 1.8.0, torch 2.13.0+cpu
```

## Verdicts

CHECK means the test passed but something needs a look before calling it a pass.

| Criterion | Verdict | Evidence |
|---|---|---|
| T1.1 T1b builds two complete chains, and every job finishes | PASS | T1a 4 of 4 nodes done, T1b 8 of 8 nodes done; every event has its sampling and importance-sampling results and corner plot |
| T1.2 No output file is written by more than one chain | FAIL | T1b: Every event's jobs write data/H1_psd.txt, data/L1_psd.txt under the same name, so the last to finish wins |
| T1.3 The T1b copies agree with each other and with T1a | PASS | Network samples: smallest KS p-value 0.119 (ra, T1a vs T1b/1) against a threshold of 0.000256 over 39 tests; log evidence not compared, since a run has fewer than 100 effective samples; event data bit-identical across runs |
| T2.1 T2b builds three complete chains, and every job finishes | PASS | T2a 4 of 4 nodes done, T2b 12 of 12 nodes done; every event has its sampling and importance-sampling results and corner plot |
| T2.2 All four runs agree with the Exercise 3 reference | CHECK | Network samples: smallest KS p-value 0.0537 (theta_jn, T2a vs T2b/1) against a threshold of 0.000104 over 96 tests; log evidence: largest disagreement 1.18 sigma (limit 3); event data bit-identical across runs; log evidence compared with Exercise 3's -5829.945 +- 0.014 too; sample efficiencies T2a 10.42%, T2b/0 9.02%, T2b/1 1.54%, T2b/2 0.27% (reference 9.40%); CHECK: T2b/1, T2b/2 outside a factor of 2 of the reference's efficiency (see Weights) |
| T2.3 Timing recorded for every job | PASS | Every job's queue wait, transfers, run time and CPU read from its Condor log |
| Also: No output file is written by more than one chain (T1.2's check on T2b) | FAIL | T2b: Every event's jobs write data/H1_psd.txt, data/L1_psd.txt under the same name, so the last to finish wins |

## T1: Agreement between runs

Network samples, two-sample KS per parameter: 39 tests over 3 runs, Bonferroni threshold 0.000256 (0.01 family-wise). Smallest p-value per pair:

| Pair | Smallest p | Parameter | KS statistic |
|---|---|---|---|
| T1a vs T1b/0 | 0.357 | chi_2 | 0.0131 |
| T1a vs T1b/1 | 0.119 | ra | 0.0168 |
| T1b/0 vs T1b/1 | 0.16 | phase | 0.0159 |

| Run | ln Z | sigma | Effective samples | Efficiency |
|---|---|---|---|---|
| T1a | -5605.572 | 0.958 | 1.1 of 10000 | 0.01% |
| T1b/0 | -5599.441 | 1.000 | 1.0 of 10000 | 0.01% |
| T1b/1 | -5541.555 | 1.000 | 1.0 of 10000 | 0.01% |

| Pair | Difference in ln Z | Combined sigma | Disagreement (sigma) |
|---|---|---|---|
| T1a vs T1b/0 | -6.131 | 1.385 | 4.43 |
| T1a vs T1b/1 | -64.017 | 1.385 | 46.23 |
| T1b/0 vs T1b/1 | -57.887 | 1.414 | 40.93 |

Event data (SHA-256 of every dataset in each event data file's data group): bit-identical across T1a, T1b/0, T1b/1.

### Weights

In units of each run's mean weight. A few heavy samples (a proposal missing part of the posterior) drag the efficiency down on their own; removing the heaviest then restores much of it.

| Run | Efficiency | Largest weight | Share of the 10 largest | Efficiency without the heaviest | Zero weights |
|---|---|---|---|---|---|
| T1a | 0.01% | 9570 | 100.00% | 0.01% | 5953 |
| T1b/0 | 0.01% | 1e+04 | 100.00% | 0.01% | 5955 |
| T1b/1 | 0.01% | 1e+04 | 100.00% | 0.01% | 5996 |

The heaviest sample of each run:

| Column | T1a | T1b/0 | T1b/1 |
|---|---|---|---|
| chirp_mass | 44.1793 | 45.8412 | 28.8681 |
| mass_ratio | 0.486464 | 0.50377 | 0.439673 |
| chi_1 | 0.00425504 | -0.173807 | 0.0943812 |
| chi_2 | 0.313798 | -0.00715925 | 0.237444 |
| theta_jn | 2.20831 | 0.942898 | 2.23517 |
| dec | -0.149193 | -1.08572 | -1.08107 |
| ra | 2.56884 | 1.95385 | 1.7763 |
| geocent_time | -0.000924178 | 0.00429249 | 0.0150835 |
| luminosity_distance | 752.638 | 952.054 | 653.03 |
| psi | 2.30696 | 2.72762 | 1.39249 |
| phase | 5.33929 | 2.64203 | 3.99915 |
| lensing_delta_t | 0.00716016 | 0.0588265 | 0.000306848 |
| mu_rel | 0.919411 | 0.691517 | 0.30629 |
| log_prob | -13.3365 | -13.3402 | -13.8107 |
| log_prior | -11.7236 | -12.1406 | -13.4505 |
| log_likelihood | -5598.02 | -5591.43 | -5532.7 |
| weights | 9569.88 | 10000 | 10000 |

Weighted median [5%, 95%] of every parameter after importance sampling:

| Parameter | T1a | T1b/0 | T1b/1 |
|---|---|---|---|
| chirp_mass | 44.18 [44.17, 44.2] | 45.84 [45.84, 45.84] | 28.87 [28.86, 28.87] |
| mass_ratio | 0.4865 [0.4864, 0.4867] | 0.5038 [0.5035, 0.5038] | 0.4397 [0.4395, 0.4397] |
| chi_1 | 0.004261 [0.004209, 0.004388] | -0.1738 [-0.1742, -0.1733] | 0.09438 [0.09404, 0.09443] |
| chi_2 | 0.3138 [0.3137, 0.3147] | -0.007159 [-0.007217, -0.007154] | 0.2374 [0.2373, 0.2376] |
| theta_jn | 2.208 [2.207, 2.209] | 0.9429 [0.9415, 0.9442] | 2.235 [2.235, 2.236] |
| dec | -0.1492 [-0.1499, -0.1485] | -1.086 [-1.087, -1.085] | -1.081 [-1.088, -1.078] |
| ra | 2.569 [2.567, 2.572] | 1.954 [1.952, 1.954] | 1.776 [1.772, 1.777] |
| geocent_time | -0.0009234 [-0.0009449, -0.0009069] | 0.004292 [0.004281, 0.004303] | 0.01508 [0.01507, 0.01511] |
| luminosity_distance | 752.6 [752.5, 752.7] | 952.1 [951.7, 953.2] | 653 [653, 653.2] |
| psi | 2.307 [2.306, 2.307] | 2.728 [2.727, 2.728] | 1.392 [1.392, 1.394] |
| phase | 5.339 [5.339, 5.343] | 2.642 [2.641, 2.643] | 3.999 [3.998, 4] |
| lensing_delta_t | 0.007167 [0.007083, 0.007319] | 0.05883 [0.05881, 0.05885] | 0.0003068 [0.0002197, 0.0003356] |
| mu_rel | 0.9194 [0.9185, 0.9195] | 0.6915 [0.6915, 0.6917] | 0.3063 [0.3062, 0.3063] |

## T2: Agreement between runs

Network samples, two-sample KS per parameter: 96 tests over 4 runs, Bonferroni threshold 0.000104 (0.01 family-wise). Smallest p-value per pair:

| Pair | Smallest p | Parameter | KS statistic |
|---|---|---|---|
| T2a vs T2b/0 | 0.167 | psi | 0.0070 |
| T2a vs T2b/1 | 0.0537 | theta_jn | 0.0085 |
| T2a vs T2b/2 | 0.273 | geocent_time | 0.0063 |
| T2b/0 vs T2b/1 | 0.116 | phi_12 | 0.0075 |
| T2b/0 vs T2b/2 | 0.109 | psi | 0.0076 |
| T2b/1 vs T2b/2 | 0.253 | tilt_2 | 0.0064 |

Including Exercise 3's own network samples: smallest p-value 0.0386 (phi_jl, T2a vs reference), threshold 6.25e-05.

| Run | ln Z | sigma | Effective samples | Efficiency |
|---|---|---|---|---|
| T2a | -5829.933 | 0.013 | 5210.9 of 50000 | 10.42% |
| T2b/0 | -5829.933 | 0.014 | 4509.4 of 50000 | 9.02% |
| T2b/1 | -5829.905 | 0.036 | 768.9 of 50000 | 1.54% |
| T2b/2 | -5829.843 | 0.085 | 137.3 of 50000 | 0.27% |
| Exercise 3 (reference) | -5829.945 | 0.014 | | 9.40% |

| Pair | Difference in ln Z | Combined sigma | Disagreement (sigma) |
|---|---|---|---|
| T2a vs T2b/0 | +0.001 | 0.019 | 0.04 |
| T2a vs T2b/1 | -0.028 | 0.038 | 0.73 |
| T2a vs T2b/2 | -0.089 | 0.086 | 1.04 |
| T2a vs Exercise 3 | +0.012 | 0.019 | 0.65 |
| T2b/0 vs T2b/1 | -0.028 | 0.039 | 0.74 |
| T2b/0 vs T2b/2 | -0.090 | 0.086 | 1.04 |
| T2b/0 vs Exercise 3 | +0.012 | 0.020 | 0.59 |
| T2b/1 vs T2b/2 | -0.062 | 0.092 | 0.67 |
| T2b/1 vs Exercise 3 | +0.040 | 0.038 | 1.04 |
| T2b/2 vs Exercise 3 | +0.102 | 0.086 | 1.18 |

Event data (SHA-256 of every dataset in each event data file's data group): bit-identical across T2a, T2b/0, T2b/1, T2b/2.

### Weights

In units of each run's mean weight. A few heavy samples (a proposal missing part of the posterior) drag the efficiency down on their own; removing the heaviest then restores much of it.

| Run | Efficiency | Largest weight | Share of the 10 largest | Efficiency without the heaviest | Zero weights |
|---|---|---|---|---|---|
| T2a | 10.42% | 199.3 | 2.18% | 11.27% | 224 |
| T2b/0 | 9.02% | 268.6 | 2.54% | 10.26% | 250 |
| T2b/1 | 1.54% | 1666 | 5.33% | 9.83% | 223 |
| T2b/2 | 0.27% | 4204 | 10.86% | 7.91% | 223 |

The heaviest sample of each run:

| Column | T2a | T2b/0 | T2b/1 | T2b/2 |
|---|---|---|---|---|
| chirp_mass | 131.061 | 103.452 | 134.04 | 83.4043 |
| mass_ratio | 0.365057 | 0.166276 | 0.918634 | 0.272229 |
| a_1 | 0.931226 | 0.963373 | 0.52225 | 0.971209 |
| a_2 | 0.390053 | 0.877352 | 0.870535 | 0.380874 |
| tilt_1 | 2.2568 | 1.79171 | 1.91265 | 2.49134 |
| tilt_2 | 0.91916 | 1.03526 | 2.25705 | 2.24604 |
| phi_12 | 0.924555 | 0.533174 | 2.68629 | 2.91248 |
| phi_jl | 1.85381 | 1.45217 | 1.19514 | 1.18529 |
| theta_jn | 0.791592 | 1.26698 | 1.96936 | 1.10147 |
| dec | 0.669466 | 0.0849682 | 0.698501 | 0.0226621 |
| ra | 4.30523 | 5.27034 | 3.96852 | 3.16709 |
| geocent_time | -0.00109198 | -0.00776305 | 0.00477542 | 0.0232879 |
| luminosity_distance | 3600.44 | 3070.03 | 5057.63 | 3042.87 |
| psi | 2.47246 | 3.08028 | 0.103178 | 1.71243 |
| lensing_delta_t | 0.0991334 | 0.0996045 | 0.00880394 | 0.0113839 |
| mu_rel | 0.0724533 | 0.0609069 | 0.601028 | 0.160386 |
| log_prob | -11.6058 | -3.73841 | -16.1573 | -11.9628 |
| phase | 6.27392 | 0.739802 | 5.38422 | 1.42035 |
| log_prior | -22.1219 | -20.6343 | -22.666 | -22.0449 |
| log_likelihood | -5814.12 | -5807.44 | -5815.98 | -5811.42 |
| weights | 199.297 | 268.627 | 1666.18 | 4204.04 |

Weighted median [5%, 95%] of every parameter after importance sampling:

| Parameter | T2a | T2b/0 | T2b/1 | T2b/2 |
|---|---|---|---|---|
| chirp_mass | 147.6 [107, 169.8] | 147.5 [105.6, 168.8] | 147.2 [104.8, 169.4] | 146.1 [83.4, 169.4] |
| mass_ratio | 0.6319 [0.2267, 0.9547] | 0.636 [0.2246, 0.9561] | 0.6452 [0.2145, 0.9513] | 0.6026 [0.2524, 0.9511] |
| a_1 | 0.4423 [0.04186, 0.9239] | 0.4514 [0.04304, 0.9296] | 0.4531 [0.04209, 0.9171] | 0.5016 [0.04793, 0.9712] |
| a_2 | 0.478 [0.04831, 0.9387] | 0.4848 [0.04563, 0.9358] | 0.5133 [0.05195, 0.9404] | 0.4435 [0.05218, 0.9314] |
| tilt_1 | 1.625 [0.4876, 2.69] | 1.621 [0.5185, 2.683] | 1.6 [0.5007, 2.614] | 1.673 [0.5206, 2.634] |
| tilt_2 | 1.588 [0.4736, 2.671] | 1.582 [0.4977, 2.675] | 1.616 [0.4861, 2.669] | 1.673 [0.5227, 2.661] |
| phi_12 | 3.057 [0.335, 5.949] | 3.177 [0.3109, 5.948] | 3.064 [0.304, 5.971] | 2.922 [0.3611, 6.006] |
| phi_jl | 2.867 [0.3467, 5.927] | 2.989 [0.3631, 5.92] | 2.817 [0.368, 5.918] | 2.687 [0.3704, 5.879] |
| theta_jn | 1.151 [0.2848, 2.816] | 1.173 [0.2749, 2.802] | 1.223 [0.2828, 2.794] | 1.101 [0.2888, 2.788] |
| dec | 0.112 [-1.275, 0.7821] | 0.1091 [-1.267, 0.7818] | 0.1364 [-1.262, 0.7792] | 0.05468 [-1.227, 0.791] |
| ra | 3.38 [2.588, 5.508] | 3.389 [2.597, 5.507] | 3.415 [2.625, 5.5] | 3.324 [2.64, 5.487] |
| geocent_time | 0.007642 [-0.02134, 0.02189] | 0.007827 [-0.02152, 0.02218] | 0.007085 [-0.0214, 0.0222] | 0.009321 [-0.02048, 0.02329] |
| luminosity_distance | 5344 [2067, 8971] | 5371 [2104, 8975] | 5260 [2137, 9037] | 5213 [2200, 8966] |
| psi | 1.559 [0.1524, 3.006] | 1.557 [0.153, 3.007] | 1.479 [0.1032, 2.976] | 1.712 [0.1587, 2.968] |
| lensing_delta_t | 0.09672 [0.004187, 0.09953] | 0.09671 [0.004509, 0.09957] | 0.09635 [0.004548, 0.09957] | 0.09594 [0.004915, 0.0995] |
| mu_rel | 0.1487 [0.02397, 0.8506] | 0.1416 [0.02609, 0.8391] | 0.1504 [0.02386, 0.8336] | 0.1604 [0.02683, 0.8554] |
| phase | 2.55 [0.2764, 6.02] | 2.587 [0.2955, 6.053] | 2.553 [0.2648, 5.991] | 2.369 [0.3218, 5.964] |

## Timing

**T1a** (1 event(s)): Wall time 0:07:38 from first submission to last job; per event: event 0 0:07:38. CPU 0.02 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T1a_data0_1126259462-4_generation_arg_0 | 0:01:45 | 0:00:09 | 0:01:13 | 0:00:01 | 0:00:43 | 0.59 / 1 | 324 / 8192 | 1.1 / 5 | 1.18 | 1 |
| T1a_data0_1126259462-4_sampling_arg_0 | 0:01:21 | 0:00:09 | 0:00:21 | 0:00:00 | 0:00:08 | 0.38 / 8 | 0 / 8192 | 0.87 / 5 | 0.935 | 1 |
| T1a_data0_1126259462-4_importance_sampling_arg_0 | 0:00:02 | 0:00:09 | 0:00:25 | 0:00:05 | 0:00:19 | 0.76 / 8 | 454 / 8192 | 0.82 / 5 | 0.875 | 1 |
| T1a_data0_1126259462-4_importance_sampling_plot_arg_0 | 0:00:40 | 0:00:05 | 0:00:37 | 0:00:02 | 0:00:16 | 0.43 / 1 | 408 / 32768 | 0.81 / 5 | 0.875 | 1 |

**T1b** (2 event(s)): Wall time 0:07:36 from first submission to last job; per event: event 0 0:07:32, event 1 0:04:15. CPU 0.05 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T1b_data0_1126259462-4_generation_arg_0 | 0:01:45 | 0:00:17 | 0:01:11 | 0:00:00 | 0:00:46 | 0.65 / 1 | 341 / 8192 | 1.1 / 5 | 1.18 | 1 |
| T1b_data1_1126259462-4_generation_arg_0 | 0:00:04 | 0:00:13 | 0:01:07 | 0:00:01 | 0:00:44 | 0.66 / 1 | 358 / 8192 | 1.1 / 5 | 1.18 | 1 |
| T1b_data0_1126259462-4_sampling_arg_0 | 0:01:16 | 0:00:09 | 0:00:21 | 0:00:00 | 0:00:08 | 0.38 / 8 | 0 / 8192 | 0.87 / 5 | 0.935 | 1 |
| T1b_data1_1126259462-4_sampling_arg_0 | 0:00:11 | 0:00:09 | 0:00:22 | 0:00:01 | 0:00:08 | 0.36 / 8 | 0 / 8192 | 0.87 / 5 | 0.935 | 1 |
| T1b_data0_1126259462-4_importance_sampling_arg_0 | 0:00:06 | 0:00:08 | 0:00:24 | 0:00:04 | 0:00:18 | 0.75 / 8 | 529 / 8192 | 0.82 / 5 | 0.875 | 1 |
| T1b_data1_1126259462-4_importance_sampling_arg_0 | 0:00:02 | 0:00:08 | 0:00:23 | 0:00:01 | 0:00:19 | 0.83 / 8 | 528 / 8192 | 0.82 / 5 | 0.875 | 1 |
| T1b_data0_1126259462-4_importance_sampling_plot_arg_0 | 0:00:42 | 0:00:04 | 0:00:33 | 0:00:02 | 0:00:15 | 0.45 / 1 | 460 / 32768 | 0.81 / 5 | 0.875 | 1 |
| T1b_data1_1126259462-4_importance_sampling_plot_arg_0 | 0:00:17 | 0:00:05 | 0:00:34 | 0:00:03 | 0:00:14 | 0.41 / 1 | 493 / 32768 | 0.81 / 5 | 0.875 | 1 |

**T2a** (1 event(s)): Wall time 2:45:55 from first submission to last job; per event: event 0 2:45:55. CPU 8.14 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T2a_data0_1384782888-63_generation_arg_0 | 0:01:35 | 0:00:53 | 0:00:49 | 0:00:01 | 0:00:24 | 0.49 / 1 | 376 / 16384 | 5 / 12 | 5.39 | 1 |
| T2a_data0_1384782888-63_sampling_arg_0 | 2:23:08 | 0:00:19 | 0:01:13 | 0:00:00 | 0:13:39 | 11 / 32 | 416 / 32768 | 5 / 12 | 5.39 | 1 |
| T2a_data0_1384782888-63_importance_sampling_arg_0 | 0:01:09 | 0:00:04 | 0:15:47 | 0:00:00 | 7:53:58 | 30 / 32 | 3200 / 8192 | 0.82 / 12 | 0.877 | 1 |
| T2a_data0_1384782888-63_importance_sampling_plot_arg_0 | 0:00:01 | 0:00:03 | 0:00:32 | 0:00:00 | 0:00:16 | 0.5 / 1 | 543 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T2b** (3 event(s)): Wall time 3:01:55 from first submission to last job; per event: event 0 2:46:23, event 1 2:58:08, event 2 2:42:00. CPU 23.42 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T2b_data0_1384782888-63_generation_arg_0 | 0:01:36 | 0:00:55 | 0:01:00 | 0:00:03 | 0:00:25 | 0.42 / 1 | 272 / 16384 | 5 / 12 | 5.39 | 1 |
| T2b_data1_1384782888-63_generation_arg_0 | 0:00:10 | 0:00:27 | 0:00:54 | 0:00:05 | 0:00:23 | 0.43 / 1 | 308 / 16384 | 5 / 12 | 5.39 | 1 |
| T2b_data2_1384782888-63_generation_arg_0 | 0:00:11 | 0:00:22 | 0:00:44 | 0:00:01 | 0:00:23 | 0.52 / 1 | 377 / 16384 | 5 / 12 | 5.39 | 1 |
| T2b_data0_1384782888-63_sampling_arg_0 | 2:23:49 | 0:00:17 | 0:01:32 | 0:00:01 | 0:29:01 | 19 / 32 | 420 / 32768 | 5 / 12 | 5.39 | 1 |
| T2b_data1_1384782888-63_sampling_arg_0 | 2:22:30 | 0:00:19 | 0:01:09 | 0:00:00 | 0:14:14 | 12 / 32 | 484 / 32768 | 5 / 12 | 5.39 | 1 |
| T2b_data2_1384782888-63_sampling_arg_0 | 2:22:17 | 0:00:17 | 0:01:29 | 0:00:00 | 0:27:28 | 19 / 32 | 417 / 32768 | 5 / 12 | 5.39 | 1 |
| T2b_data0_1384782888-63_importance_sampling_arg_0 | 0:00:00 | 0:00:04 | 0:16:01 | 0:00:01 | 7:53:26 | 30 / 32 | 3133 / 8192 | 0.82 / 12 | 0.877 | 1 |
| T2b_data1_1384782888-63_importance_sampling_arg_0 | 0:14:57 | 0:00:04 | 0:15:09 | 0:00:00 | 7:13:41 | 29 / 32 | 2514 / 8192 | 0.82 / 12 | 0.877 | 1 |
| T2b_data2_1384782888-63_importance_sampling_arg_0 | 0:00:07 | 0:00:05 | 0:14:59 | 0:00:00 | 7:04:57 | 28 / 32 | 2560 / 8192 | 0.82 / 12 | 0.877 | 1 |
| T2b_data0_1384782888-63_importance_sampling_plot_arg_0 | 0:00:03 | 0:00:04 | 0:00:31 | 0:00:01 | 0:00:17 | 0.55 / 1 | 518 / 32768 | 0.82 / 12 | 0.879 | 1 |
| T2b_data1_1384782888-63_importance_sampling_plot_arg_0 | 0:00:44 | 0:00:05 | 0:00:58 | 0:00:00 | 0:00:28 | 0.48 / 1 | 334 / 32768 | 0.82 / 12 | 0.879 | 1 |
| T2b_data2_1384782888-63_importance_sampling_plot_arg_0 | 0:00:19 | 0:00:04 | 0:00:34 | 0:00:00 | 0:00:19 | 0.56 / 1 | 506 / 32768 | 0.82 / 12 | 0.879 | 1 |

