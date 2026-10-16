# Option A results

Analysed 2026-10-15T19:15:58 from `/home/kailibryan.doney/dingo-lensing-runs/option_a_t4`.

```
date: 2026-10-15T01:37:33Z
host: ldas-grid
suite: T4
code: kailib-parallelisation at 1d7c4771b49fd0ce10ab1c7542ed4c5fecbbe73c
tests: local-tests-sync at 7bb0ddb0633c3449bf0c2ae29b6e2d282cc0b8c3
image: osdf:///igwn/cit/staging/kailibryan.doney/containers/dingo-lensing_1d7c4771b4_recipe-ff6622d_cpu.sif
workflows built with: /home/kailibryan.doney/.conda/envs/dingo_env
in the image: dingo 0.9.8, bilby_pipe 1.8.0, torch 2.13.0+cpu
```

## Verdicts

CHECK means the test passed but something needs a look before calling it a pass.

| Criterion | Verdict | Evidence |
|---|---|---|
| T4.1 Every chain completes | PASS | T4a 4 of 4 nodes done, T4b 4 of 4 nodes done, T4c 4 of 4 nodes done, T4d 4 of 4 nodes done, T4e 4 of 4 nodes done, T4f 4 of 4 nodes done, T4g 4 of 4 nodes done, T4m 28 of 28 nodes done, T4ua 4 of 4 nodes done, T4ub 4 of 4 nodes done, T4uc 4 of 4 nodes done, T4ud 4 of 4 nodes done, T4ue 4 of 4 nodes done, T4uf 4 of 4 nodes done, T4ug 4 of 4 nodes done; every event has its sampling and importance-sampling results and corner plot |
| T4.2 No output file is written by more than one chain | PASS | T4m: Every output names its event |
| T4.3 GW230628_231200 in T4m matches its single-event run | PASS | Network samples: smallest KS p-value 0.0476 (a_2, T4a vs T4m/0) against a threshold of 8.93e-05 over 16 tests; log evidence not compared, since a run has fewer than 100 effective samples; event data bit-identical; PSD files bit-identical |
| T4.3 GW230708_230935 in T4m matches its single-event run | PASS | Network samples: smallest KS p-value 0.0701 (theta_jn, T4b vs T4m/1) against a threshold of 8.93e-05 over 16 tests; log evidence: largest disagreement 0.63 sigma (limit 3); event data bit-identical; PSD files bit-identical |
| T4.3 GW230914_111401 in T4m matches its single-event run | PASS | Network samples: smallest KS p-value 0.0519 (phi_12, T4c vs T4m/2) against a threshold of 8.93e-05 over 16 tests; log evidence: largest disagreement 0.36 sigma (limit 3); event data bit-identical; PSD files bit-identical |
| T4.3 GW230927_153832 in T4m matches its single-event run | PASS | Network samples: smallest KS p-value 0.00648 (phi_12, T4d vs T4m/3) against a threshold of 8.93e-05 over 16 tests; log evidence not compared, since a run has fewer than 100 effective samples; event data bit-identical; PSD files bit-identical |
| T4.3 GW231102_071736 in T4m matches its single-event run | PASS | Network samples: smallest KS p-value 0.00706 (luminosity_distance, T4e vs T4m/4) against a threshold of 8.93e-05 over 16 tests; log evidence: largest disagreement 0.51 sigma (limit 3); event data bit-identical; PSD files bit-identical |
| T4.3 GW231206_233134 in T4m matches its single-event run | PASS | Network samples: smallest KS p-value 0.129 (phi_12, T4f vs T4m/5) against a threshold of 8.93e-05 over 16 tests; log evidence not compared, since a run has fewer than 100 effective samples; event data bit-identical; PSD files bit-identical |
| T4.3 GW231206_233901 in T4m matches its single-event run | PASS | Network samples: smallest KS p-value 0.0604 (mu_rel, T4g vs T4m/6) against a threshold of 8.93e-05 over 16 tests; log evidence not compared, since a run has fewer than 100 effective samples; event data bit-identical; PSD files bit-identical |
| T4.4 The seven events' data really differ | PASS | Every one of the 21 pairs of T4m's events has different event data and PSD files |
| T4.5 Each event's lensed and unlensed runs analyse the same data | PASS | GW230628_231200: event data bit-identical; GW230708_230935: event data bit-identical; GW230914_111401: event data bit-identical; GW230927_153832: event data bit-identical; GW231102_071736: event data bit-identical; GW231206_233134: event data bit-identical; GW231206_233901: event data bit-identical |
| T4.6 Timing recorded for every job | PASS | From each job's Condor log |
| T4.7 Importance sampling gives at least 100 effective samples in every run | CHECK | Fewer in T4a (2.0), T4d (2.9), T4g (4.1), T4m/0 (6.3), T4m/3 (4.6), T4m/5 (92.8), T4m/6 (4.1), T4ua (34.8), T4ud (5.4), T4ug (59.7): The model fits those events' data poorly, and their log evidences and Bayes factors are not reliable |
| Also: Lensing Bayes factors, log10 B (lensed vs unlensed) | CHECK | GW230628_231200 -0.59 +- 0.31 (unreliable); GW230708_230935 -0.87 +- 0.02; GW230914_111401 -0.95 +- 0.04; GW230927_153832 -0.54 +- 0.32 (unreliable); GW231102_071736 -1.03 +- 0.02; GW231206_233134 -1.05 +- 0.04; GW231206_233901 -1.25 +- 0.22 (unreliable). CHECK if any is unreliable or above 1 |
| Also: Detector-frame chirp mass agrees with the LVK's GWTC-4.0 results | PASS | The LVK's median lies inside every run's 90% interval for every event |

## Lensing Bayes factors

From each event's single-event runs with the lensed model (T4a to T4g) and the unlensed model (T4ua to T4ug): ln B = ln Z(lensed) - ln Z(unlensed), with DINGO's log-evidence errors combined. Reliable only if both runs have at least 100 effective samples.

| Event | ln Z lensed | ln Z unlensed | log10 B | Effective samples (lensed / unlensed) | Reliable |
|---|---|---|---|---|---|
| GW230628_231200 | -6042.244 | -6040.894 | -0.586 +- 0.314 | 2.0 / 34.8 | no |
| GW230708_230935 | -6042.346 | -6040.337 | -0.873 +- 0.016 | 909.1 / 2617.9 | yes |
| GW230914_111401 | -5873.831 | -5871.643 | -0.950 +- 0.035 | 317.9 / 287.5 | yes |
| GW230927_153832 | -5903.532 | -5902.294 | -0.538 +- 0.316 | 2.9 / 5.4 | no |
| GW231102_071736 | -6066.184 | -6063.803 | -1.034 +- 0.023 | 397.4 / 2265.8 | yes |
| GW231206_233134 | -6044.174 | -6041.759 | -1.049 +- 0.045 | 108.8 / 657.6 | yes |
| GW231206_233901 | -5874.541 | -5871.660 | -1.251 +- 0.222 | 4.1 / 59.7 | no |

## Comparison with GWTC-4.0

Median [5%, 95%] from the LVK's IMRPhenomXPHM-SpinTaylor analysis (t4_lvk.json) and from each event's single-event runs. The LVK's distance prior is uniform in comoving volume and the models' uniform in distance, so distances differ by design. The models always start at 20 Hz; the LVK's lowest frequency per detector is listed for each event.

**GW230628_231200** (LVK's lowest frequency: H1 20 Hz, L1 20 Hz)

| Parameter | LVK | T4a | T4ua |
|---|---|---|---|
| chirp_mass | 35.92 [33.14, 38.85] | 35.5 [35.42, 37.43] | 35.85 [33.49, 38.24] |
| mass_ratio | 0.8425 [0.5891, 0.9843] | 0.9496 [0.8458, 0.9954] | 0.8428 [0.5849, 0.9816] |
| luminosity_distance | 2290 [1223, 3102] | 2056 [1958, 4759] | 1809 [886.5, 2767] |
| chi_eff | -0.001885 [-0.1658, 0.1578] | -0.08803 [-0.08803, 0.1204] | -0.02494 [-0.1605, 0.1037] |

**GW230708_230935** (LVK's lowest frequency: H1 20 Hz, L1 20 Hz)

| Parameter | LVK | T4b | T4ub |
|---|---|---|---|
| chirp_mass | 68.6 [53.19, 82.78] | 68.48 [52.17, 82.08] | 68.89 [54.23, 82.71] |
| mass_ratio | 0.6187 [0.303, 0.9471] | 0.6164 [0.2784, 0.9454] | 0.6304 [0.3158, 0.9464] |
| luminosity_distance | 3482 [1859, 5770] | 4002 [1866, 7584] | 3218 [1485, 5361] |
| chi_eff | 0.02854 [-0.2687, 0.3168] | 0.04846 [-0.2615, 0.3237] | 0.05315 [-0.2581, 0.3289] |

**GW230914_111401** (LVK's lowest frequency: H1 20 Hz, L1 20 Hz)

| Parameter | LVK | T4c | T4uc |
|---|---|---|---|
| chirp_mass | 59.02 [47.39, 67.5] | 58.21 [46.25, 66.54] | 57.42 [46.51, 65.83] |
| mass_ratio | 0.6155 [0.3592, 0.9319] | 0.599 [0.3477, 0.9216] | 0.5653 [0.3594, 0.8849] |
| luminosity_distance | 2647 [1443, 4316] | 3377 [1490, 6368] | 2374 [1294, 3994] |
| chi_eff | 0.1321 [-0.06746, 0.3332] | 0.1157 [-0.08095, 0.3192] | 0.1238 [-0.08311, 0.3017] |

**GW230927_153832** (LVK's lowest frequency: H1 20 Hz, L1 20 Hz)

| Parameter | LVK | T4d | T4ud |
|---|---|---|---|
| chirp_mass | 20.22 [19.82, 20.62] | 19.8 [19.71, 20.22] | 20.1 [19.6, 20.74] |
| mass_ratio | 0.7499 [0.555, 0.9653] | 0.7449 [0.7431, 0.8492] | 0.7244 [0.6129, 0.9754] |
| luminosity_distance | 1209 [662.3, 1577] | 1048 [977.7, 1079] | 946.7 [668.3, 1451] |
| chi_eff | 0.04287 [-0.03351, 0.121] | -0.0313 [-0.05882, 0.05752] | 0.0172 [-0.07099, 0.1134] |

**GW231102_071736** (LVK's lowest frequency: H1 20.13 Hz, L1 20.13 Hz)

| Parameter | LVK | T4e | T4ue |
|---|---|---|---|
| chirp_mass | 71.76 [61.1, 79.65] | 70.71 [58.91, 78.38] | 71.31 [60.22, 78.33] |
| mass_ratio | 0.7139 [0.44, 0.9633] | 0.6827 [0.4124, 0.9494] | 0.6686 [0.4266, 0.9395] |
| luminosity_distance | 3782 [2013, 5932] | 4444 [2345, 8072] | 3405 [1759, 5439] |
| chi_eff | 0.06283 [-0.155, 0.2894] | 0.03474 [-0.2234, 0.2244] | 0.02868 [-0.1893, 0.2361] |

**GW231206_233134** (LVK's lowest frequency: H1 40 Hz, L1 30 Hz)

| Parameter | LVK | T4f | T4uf |
|---|---|---|---|
| chirp_mass | 41.88 [37.1, 46.21] | 41.02 [34.94, 45.67] | 41.26 [36.09, 45.47] |
| mass_ratio | 0.806 [0.5351, 0.9807] | 0.7706 [0.4508, 0.9694] | 0.7946 [0.5054, 0.9776] |
| luminosity_distance | 3310 [1478, 5095] | 3271 [1137, 7042] | 3079 [1283, 5025] |
| chi_eff | -0.07749 [-0.3201, 0.1307] | -0.04829 [-0.4365, 0.1301] | -0.07231 [-0.3352, 0.1171] |

**GW231206_233901** (LVK's lowest frequency: H1 20 Hz, L1 20 Hz)

| Parameter | LVK | T4g | T4ug |
|---|---|---|---|
| chirp_mass | 36.44 [34.04, 38.77] | 33.15 [30.74, 37.49] | 35.42 [31.87, 38.41] |
| mass_ratio | 0.7654 [0.5045, 0.9766] | 0.5235 [0.4508, 0.9678] | 0.6832 [0.466, 0.969] |
| luminosity_distance | 1495 [994.3, 1845] | 2512 [1038, 2512] | 1390 [903, 1867] |
| chi_eff | -0.0238 [-0.1702, 0.1109] | -0.1801 [-0.2313, 0.07892] | -0.07576 [-0.2647, 0.07461] |


## GW230628_231200: Agreement between runs

Network samples, two-sample KS per parameter: 16 tests over 2 runs, Bonferroni threshold 8.93e-05 (0.00142857 family-wise). Smallest p-value per pair:

| Pair | Smallest p | Parameter | KS statistic |
|---|---|---|---|
| T4a vs T4m/0 | 0.0476 | a_2 | 0.0086 |

| Run | ln Z | sigma | Effective samples | Efficiency |
|---|---|---|---|---|
| T4a | -6042.244 | 0.703 | 2.0 of 50000 | 0.00% |
| T4m/0 | -6043.791 | 0.399 | 6.3 of 50000 | 0.01% |

| Pair | Difference in ln Z | Combined sigma | Disagreement (sigma) |
|---|---|---|---|
| T4a vs T4m/0 | +1.547 | 0.809 | 1.91 |

Event data (every dataset in each event data file's data group): the same across T4a, T4m/0: bit-identical.

### Weights

In units of each run's mean weight. A few heavy samples (a proposal missing part of the posterior) drag the efficiency down on their own; removing the heaviest then restores much of it.

| Run | Efficiency | Largest weight | Share of the 10 largest | Efficiency without the heaviest | Zero weights |
|---|---|---|---|---|---|
| T4a | 0.00% | 3.468e+04 | 95.60% | 0.01% | 734 |
| T4m/0 | 0.01% | 1.572e+04 | 83.35% | 0.02% | 699 |

The heaviest sample of each run:

| Column | T4a | T4m/0 |
|---|---|---|
| chirp_mass | 35.4983 | 40.4737 |
| mass_ratio | 0.949643 | 0.951209 |
| a_1 | 0.906213 | 0.377702 |
| a_2 | 0.692085 | 0.978779 |
| tilt_1 | 1.75477 | 1.34569 |
| tilt_2 | 1.57968 | 1.25015 |
| phi_12 | 5.26168 | 0.0217893 |
| phi_jl | 4.68784 | 5.37976 |
| theta_jn | 2.18418 | 2.48998 |
| dec | 0.347875 | 1.23825 |
| ra | 2.21843 | 3.332 |
| geocent_time | 0.00898685 | 0.00856012 |
| luminosity_distance | 2056.07 | 3056.65 |
| psi | 0.966471 | 2.41615 |
| lensing_delta_t | 0.09554 | 0.0880184 |
| mu_rel | 0.00309983 | 0.0142306 |
| log_prob | -8.12634 | -9.23511 |
| phase | 3.48652 | 1.68487 |
| log_prior | -23.6435 | -24.9313 |
| log_likelihood | -6016.27 | -6018.43 |
| weights | 34676.6 | 15721.1 |

Weighted median [5%, 95%] of every parameter after importance sampling:

| Parameter | T4a | T4m/0 |
|---|---|---|
| chirp_mass | 35.5 [35.42, 37.43] | 36.9 [32.8, 40.47] |
| mass_ratio | 0.9496 [0.8458, 0.9954] | 0.848 [0.6026, 0.9512] |
| a_1 | 0.9062 [0.1761, 0.9062] | 0.3777 [0.06817, 0.9725] |
| a_2 | 0.6921 [0.2379, 0.6921] | 0.2123 [0.03967, 0.9788] |
| tilt_1 | 1.755 [1.221, 1.755] | 1.412 [1.138, 2.159] |
| tilt_2 | 1.58 [0.5453, 2.588] | 1.457 [1.002, 2.441] |
| phi_12 | 5.262 [1.314, 5.915] | 0.08099 [0.02176, 4.686] |
| phi_jl | 4.688 [1.239, 4.688] | 5.347 [1.5, 5.781] |
| theta_jn | 2.184 [0.8168, 2.601] | 2.49 [0.6783, 2.944] |
| dec | 0.348 [0.3479, 1.334] | 1.23 [0.4701, 1.238] |
| ra | 2.218 [2.218, 4.837] | 3.332 [2.375, 5.313] |
| geocent_time | 0.008987 [0.001215, 0.01046] | 0.008559 [-0.002508, 0.01121] |
| luminosity_distance | 2056 [1958, 4759] | 2228 [1010, 3057] |
| psi | 0.9665 [0.2142, 2.804] | 1.811 [0.4323, 2.581] |
| lensing_delta_t | 0.09552 [0.0002749, 0.09556] | 0.005343 [0.0008967, 0.08802] |
| mu_rel | 0.003104 [0.003094, 0.9288] | 0.01423 [0.009478, 0.9836] |
| phase | 3.487 [2.786, 4.653] | 4.31 [1.175, 6.167] |

## GW230708_230935: Agreement between runs

Network samples, two-sample KS per parameter: 16 tests over 2 runs, Bonferroni threshold 8.93e-05 (0.00142857 family-wise). Smallest p-value per pair:

| Pair | Smallest p | Parameter | KS statistic |
|---|---|---|---|
| T4b vs T4m/1 | 0.0701 | theta_jn | 0.0082 |

| Run | ln Z | sigma | Effective samples | Efficiency |
|---|---|---|---|---|
| T4b | -6042.346 | 0.033 | 909.1 of 50000 | 1.82% |
| T4m/1 | -6042.371 | 0.022 | 1911.0 of 50000 | 3.82% |

| Pair | Difference in ln Z | Combined sigma | Disagreement (sigma) |
|---|---|---|---|
| T4b vs T4m/1 | +0.025 | 0.040 | 0.63 |

Event data (every dataset in each event data file's data group): the same across T4b, T4m/1: bit-identical.

### Weights

In units of each run's mean weight. A few heavy samples (a proposal missing part of the posterior) drag the efficiency down on their own; removing the heaviest then restores much of it.

| Run | Efficiency | Largest weight | Share of the 10 largest | Efficiency without the heaviest | Zero weights |
|---|---|---|---|---|---|
| T4b | 1.82% | 882.6 | 7.39% | 2.45% | 184 |
| T4m/1 | 3.82% | 279.4 | 4.31% | 4.02% | 171 |

The heaviest sample of each run:

| Column | T4b | T4m/1 |
|---|---|---|
| chirp_mass | 55.3549 | 75.8674 |
| mass_ratio | 0.361407 | 0.560786 |
| a_1 | 0.984405 | 0.977068 |
| a_2 | 0.443752 | 0.0471662 |
| tilt_1 | 1.74678 | 1.04158 |
| tilt_2 | 1.52056 | 2.58447 |
| phi_12 | 1.98852 | 4.39339 |
| phi_jl | 6.23206 | 5.9349 |
| theta_jn | 0.868238 | 1.97111 |
| dec | -0.745613 | -0.92445 |
| ra | 3.96162 | 3.67187 |
| geocent_time | -0.0128447 | -0.013638 |
| luminosity_distance | 2594.67 | 3018.94 |
| psi | 2.55373 | 0.00439644 |
| lensing_delta_t | 0.0439986 | 0.0159684 |
| mu_rel | 0.0421478 | 0.0838861 |
| log_prob | -7.10415 | -12.3769 |
| phase | 5.59062 | 3.94789 |
| log_prior | -22.4989 | -23.4345 |
| log_likelihood | -6020.17 | -6025.68 |
| weights | 882.568 | 279.356 |

Weighted median [5%, 95%] of every parameter after importance sampling:

| Parameter | T4b | T4m/1 |
|---|---|---|
| chirp_mass | 68.48 [52.17, 82.08] | 68.39 [51.85, 82.31] |
| mass_ratio | 0.6164 [0.2784, 0.9454] | 0.6339 [0.2977, 0.9453] |
| a_1 | 0.4772 [0.04904, 0.9543] | 0.4465 [0.0485, 0.9391] |
| a_2 | 0.4764 [0.05412, 0.9394] | 0.4714 [0.0445, 0.9316] |
| tilt_1 | 1.434 [0.4452, 2.565] | 1.447 [0.4361, 2.619] |
| tilt_2 | 1.521 [0.4319, 2.629] | 1.501 [0.4326, 2.684] |
| phi_12 | 3.045 [0.3076, 6.099] | 3.186 [0.3232, 5.988] |
| phi_jl | 3.465 [0.3505, 6.086] | 3.497 [0.3609, 5.976] |
| theta_jn | 2.092 [0.3748, 2.966] | 2.105 [0.3909, 2.92] |
| dec | -0.8902 [-1.109, -0.08229] | -0.9026 [-1.114, -0.09868] |
| ra | 4.319 [3.473, 4.863] | 4.337 [3.523, 4.86] |
| geocent_time | -0.02189 [-0.02901, -0.01106] | -0.02191 [-0.02906, -0.01162] |
| luminosity_distance | 4002 [1866, 7584] | 3960 [1775, 7632] |
| psi | 1.807 [0.1858, 2.938] | 1.826 [0.1869, 2.984] |
| lensing_delta_t | 0.004954 [0.0006241, 0.07542] | 0.004621 [0.0004978, 0.08205] |
| mu_rel | 0.158 [0.006768, 0.9163] | 0.1775 [0.007176, 0.9209] |
| phase | 3.317 [0.8405, 5.713] | 3.257 [0.9237, 5.523] |

## GW230914_111401: Agreement between runs

Network samples, two-sample KS per parameter: 16 tests over 2 runs, Bonferroni threshold 8.93e-05 (0.00142857 family-wise). Smallest p-value per pair:

| Pair | Smallest p | Parameter | KS statistic |
|---|---|---|---|
| T4c vs T4m/2 | 0.0519 | phi_12 | 0.0085 |

| Run | ln Z | sigma | Effective samples | Efficiency |
|---|---|---|---|---|
| T4c | -5873.831 | 0.056 | 317.9 of 50000 | 0.64% |
| T4m/2 | -5873.791 | 0.096 | 108.9 of 50000 | 0.22% |

| Pair | Difference in ln Z | Combined sigma | Disagreement (sigma) |
|---|---|---|---|
| T4c vs T4m/2 | -0.040 | 0.111 | 0.36 |

Event data (every dataset in each event data file's data group): the same across T4c, T4m/2: bit-identical.

### Weights

In units of each run's mean weight. A few heavy samples (a proposal missing part of the posterior) drag the efficiency down on their own; removing the heaviest then restores much of it.

| Run | Efficiency | Largest weight | Share of the 10 largest | Efficiency without the heaviest | Zero weights |
|---|---|---|---|---|---|
| T4c | 0.64% | 1070 | 12.09% | 0.71% | 304 |
| T4m/2 | 0.22% | 3630 | 19.85% | 0.44% | 303 |

The heaviest sample of each run:

| Column | T4c | T4m/2 |
|---|---|---|
| chirp_mass | 66.5433 | 61.0367 |
| mass_ratio | 0.904324 | 0.554445 |
| a_1 | 0.180325 | 0.228844 |
| a_2 | 0.60352 | 0.640773 |
| tilt_1 | 0.777231 | 0.908837 |
| tilt_2 | 0.644938 | 1.04328 |
| phi_12 | 0.827362 | 6.22543 |
| phi_jl | 1.76251 | 1.34801 |
| theta_jn | 2.02809 | 2.43992 |
| dec | -0.566629 | -0.62958 |
| ra | 4.91955 | 4.95763 |
| geocent_time | -0.0319871 | -0.0311494 |
| luminosity_distance | 2654.05 | 2778.27 |
| psi | 2.51619 | 2.32978 |
| lensing_delta_t | 0.00225597 | 0.0615453 |
| mu_rel | 0.53973 | 0.0200309 |
| log_prob | -3.57778 | -2.28246 |
| phase | 5.1453 | 5.20983 |
| log_prior | -23.8278 | -23.3002 |
| log_likelihood | -5846.6 | -5844.58 |
| weights | 1070.41 | 3629.79 |

Weighted median [5%, 95%] of every parameter after importance sampling:

| Parameter | T4c | T4m/2 |
|---|---|---|
| chirp_mass | 58.21 [46.25, 66.54] | 58.33 [47.22, 66.54] |
| mass_ratio | 0.599 [0.3477, 0.9216] | 0.5845 [0.366, 0.8889] |
| a_1 | 0.2352 [0.02288, 0.7179] | 0.2288 [0.01333, 0.7595] |
| a_2 | 0.5495 [0.07822, 0.9284] | 0.4984 [0.06749, 0.9094] |
| tilt_1 | 1.351 [0.4262, 2.46] | 1.329 [0.4563, 2.467] |
| tilt_2 | 1.171 [0.356, 2.4] | 1.099 [0.2792, 2.32] |
| phi_12 | 3.055 [0.279, 5.831] | 3.541 [0.4295, 6.225] |
| phi_jl | 3.345 [0.4636, 5.953] | 2.579 [0.4028, 5.944] |
| theta_jn | 1.93 [0.3572, 2.823] | 2.168 [0.3654, 2.849] |
| dec | -0.3721 [-0.6304, 0.4882] | -0.474 [-0.6296, 0.3964] |
| ra | 4.582 [3.982, 5.878] | 4.795 [4.001, 5.808] |
| geocent_time | -0.03033 [-0.03483, -0.01384] | -0.03077 [-0.03404, -0.01598] |
| luminosity_distance | 3377 [1490, 6368] | 3084 [1106, 6095] |
| psi | 1.608 [0.4845, 2.783] | 1.835 [0.403, 2.742] |
| lensing_delta_t | 0.002256 [0.0004769, 0.07586] | 0.002734 [0.0004027, 0.06567] |
| mu_rel | 0.4818 [0.009392, 0.9445] | 0.3428 [0.004197, 0.9536] |
| phase | 4.788 [2.061, 5.782] | 4.858 [2.007, 5.718] |

## GW230927_153832: Agreement between runs

Network samples, two-sample KS per parameter: 16 tests over 2 runs, Bonferroni threshold 8.93e-05 (0.00142857 family-wise). Smallest p-value per pair:

| Pair | Smallest p | Parameter | KS statistic |
|---|---|---|---|
| T4d vs T4m/3 | 0.00648 | phi_12 | 0.0107 |

| Run | ln Z | sigma | Effective samples | Efficiency |
|---|---|---|---|---|
| T4d | -5903.532 | 0.586 | 2.9 of 50000 | 0.01% |
| T4m/3 | -5905.935 | 0.467 | 4.6 of 50000 | 0.01% |

| Pair | Difference in ln Z | Combined sigma | Disagreement (sigma) |
|---|---|---|---|
| T4d vs T4m/3 | +2.404 | 0.749 | 3.21 |

Event data (every dataset in each event data file's data group): the same across T4d, T4m/3: bit-identical.

### Weights

In units of each run's mean weight. A few heavy samples (a proposal missing part of the posterior) drag the efficiency down on their own; removing the heaviest then restores much of it.

| Run | Efficiency | Largest weight | Share of the 10 largest | Efficiency without the heaviest | Zero weights |
|---|---|---|---|---|---|
| T4d | 0.01% | 2.429e+04 | 99.67% | 0.00% | 1948 |
| T4m/3 | 0.01% | 1.516e+04 | 99.08% | 0.01% | 1894 |

The heaviest sample of each run:

| Column | T4d | T4m/3 |
|---|---|---|
| chirp_mass | 19.7117 | 19.8611 |
| mass_ratio | 0.743145 | 0.928496 |
| a_1 | 0.434184 | 0.318334 |
| a_2 | 0.382864 | 0.0721291 |
| tilt_1 | 1.41828 | 1.62745 |
| tilt_2 | 2.20453 | 2.31694 |
| phi_12 | 4.12288 | 2.62761 |
| phi_jl | 2.36337 | 5.5492 |
| theta_jn | 2.79436 | 2.98552 |
| dec | 0.0857636 | 0.113458 |
| ra | 5.20517 | 5.19008 |
| geocent_time | -0.0171372 | -0.0167143 |
| luminosity_distance | 1048.06 | 1029.05 |
| psi | 0.706366 | 0.558237 |
| lensing_delta_t | 0.0725903 | 0.0824692 |
| mu_rel | 0.0006226 | 0.0493853 |
| log_prob | -0.881319 | -2.32452 |
| phase | 5.27853 | 5.27301 |
| log_prior | -25.0114 | -26.0999 |
| log_likelihood | -5869.3 | -5872.53 |
| weights | 24290.6 | 15160.4 |

Weighted median [5%, 95%] of every parameter after importance sampling:

| Parameter | T4d | T4m/3 |
|---|---|---|
| chirp_mass | 19.8 [19.71, 20.22] | 20.16 [19.64, 20.27] |
| mass_ratio | 0.7449 [0.7431, 0.8492] | 0.7295 [0.723, 0.9285] |
| a_1 | 0.1612 [0.1049, 0.4342] | 0.1531 [0.05516, 0.3184] |
| a_2 | 0.3829 [0.02937, 0.7673] | 0.1531 [0.07213, 0.5865] |
| tilt_1 | 1.418 [0.9573, 1.856] | 1.029 [0.7133, 2.525] |
| tilt_2 | 2.169 [1.355, 2.205] | 1.834 [1.483, 2.317] |
| phi_12 | 4.123 [0.8347, 5.09] | 1.372 [0.767, 2.628] |
| phi_jl | 2.363 [1.936, 3.065] | 4.395 [0.03326, 5.549] |
| theta_jn | 2.268 [0.8331, 2.794] | 2.594 [1.193, 2.986] |
| dec | -0.04654 [-0.9344, 0.08579] | 0.2589 [-0.8461, 0.4131] |
| ra | 5.205 [0.3743, 5.275] | 5.116 [5.066, 6.169] |
| geocent_time | -0.0181 [-0.01875, -0.01714] | -0.01472 [-0.02209, -0.01113] |
| luminosity_distance | 1048 [977.7, 1079] | 795.5 [647.6, 1029] |
| psi | 1.312 [0.7063, 2.34] | 0.5582 [0.3239, 3.059] |
| lensing_delta_t | 0.0135 [0.0006831, 0.07263] | 0.05597 [0.0005603, 0.08247] |
| mu_rel | 0.02124 [0.000622, 0.08352] | 0.04939 [0.02911, 0.6001] |
| phase | 3.827 [3.401, 5.279] | 4.992 [4.648, 5.706] |

## GW231102_071736: Agreement between runs

Network samples, two-sample KS per parameter: 16 tests over 2 runs, Bonferroni threshold 8.93e-05 (0.00142857 family-wise). Smallest p-value per pair:

| Pair | Smallest p | Parameter | KS statistic |
|---|---|---|---|
| T4e vs T4m/4 | 0.00706 | luminosity_distance | 0.0106 |

| Run | ln Z | sigma | Effective samples | Efficiency |
|---|---|---|---|---|
| T4e | -6066.184 | 0.050 | 397.4 of 50000 | 0.79% |
| T4m/4 | -6066.218 | 0.045 | 499.6 of 50000 | 1.00% |

| Pair | Difference in ln Z | Combined sigma | Disagreement (sigma) |
|---|---|---|---|
| T4e vs T4m/4 | +0.034 | 0.067 | 0.51 |

Event data (every dataset in each event data file's data group): the same across T4e, T4m/4: bit-identical.

### Weights

In units of each run's mean weight. A few heavy samples (a proposal missing part of the posterior) drag the efficiency down on their own; removing the heaviest then restores much of it.

| Run | Efficiency | Largest weight | Share of the 10 largest | Efficiency without the heaviest | Zero weights |
|---|---|---|---|---|---|
| T4e | 0.79% | 1803 | 10.88% | 1.53% | 281 |
| T4m/4 | 1.00% | 1134 | 10.37% | 1.28% | 296 |

The heaviest sample of each run:

| Column | T4e | T4m/4 |
|---|---|---|
| chirp_mass | 63.2687 | 58.5798 |
| mass_ratio | 0.563724 | 0.472907 |
| a_1 | 0.3549 | 0.263423 |
| a_2 | 0.713876 | 0.0155403 |
| tilt_1 | 0.658407 | 1.38967 |
| tilt_2 | 1.58625 | 1.31804 |
| phi_12 | 4.46636 | 3.69368 |
| phi_jl | 4.28986 | 3.31531 |
| theta_jn | 1.85994 | 1.80388 |
| dec | 0.922827 | -0.649763 |
| ra | 1.49529 | 3.84442 |
| geocent_time | 0.00912149 | -0.0318795 |
| luminosity_distance | 2851.1 | 4951.16 |
| psi | 2.63455 | 0.103409 |
| lensing_delta_t | 0.00234212 | 0.00484668 |
| mu_rel | 0.261541 | 0.964178 |
| log_prob | -11.16 | -8.43705 |
| phase | 5.71744 | 5.85431 |
| log_prior | -23.2866 | -22.4421 |
| log_likelihood | -6046.56 | -6045.18 |
| weights | 1802.8 | 1133.69 |

Weighted median [5%, 95%] of every parameter after importance sampling:

| Parameter | T4e | T4m/4 |
|---|---|---|
| chirp_mass | 70.71 [58.91, 78.38] | 70.96 [58.58, 79.05] |
| mass_ratio | 0.6827 [0.4124, 0.9494] | 0.7052 [0.4248, 0.954] |
| a_1 | 0.3535 [0.03477, 0.8659] | 0.338 [0.03238, 0.9078] |
| a_2 | 0.4574 [0.04315, 0.9072] | 0.4208 [0.02829, 0.9123] |
| tilt_1 | 1.364 [0.4978, 2.478] | 1.39 [0.4315, 2.508] |
| tilt_2 | 1.642 [0.5553, 2.802] | 1.602 [0.5055, 2.628] |
| phi_12 | 3.386 [0.3222, 6.002] | 3.312 [0.3048, 5.945] |
| phi_jl | 3.345 [0.3272, 5.981] | 3.315 [0.4189, 5.89] |
| theta_jn | 1.847 [0.4254, 2.715] | 1.828 [0.4807, 2.72] |
| dec | 0.07993 [-1.047, 1.022] | -0.05318 [-1.04, 1.047] |
| ra | 1.83 [0.3796, 5.192] | 3.261 [0.3469, 5.29] |
| geocent_time | -0.00103 [-0.03474, 0.009138] | -0.0104 [-0.03449, 0.008914] |
| luminosity_distance | 4444 [2345, 8072] | 4374 [2251, 7792] |
| psi | 1.702 [0.1909, 2.996] | 1.557 [0.1035, 2.972] |
| lensing_delta_t | 0.003753 [0.0003693, 0.06982] | 0.003926 [0.0004388, 0.08765] |
| mu_rel | 0.3352 [0.005316, 0.9377] | 0.3791 [0.004427, 0.9642] |
| phase | 5.559 [0.09805, 6.216] | 5.518 [0.08458, 6.198] |

## GW231206_233134: Agreement between runs

Network samples, two-sample KS per parameter: 16 tests over 2 runs, Bonferroni threshold 8.93e-05 (0.00142857 family-wise). Smallest p-value per pair:

| Pair | Smallest p | Parameter | KS statistic |
|---|---|---|---|
| T4f vs T4m/5 | 0.129 | phi_12 | 0.0074 |

| Run | ln Z | sigma | Effective samples | Efficiency |
|---|---|---|---|---|
| T4f | -6044.174 | 0.096 | 108.8 of 50000 | 0.22% |
| T4m/5 | -6043.974 | 0.104 | 92.8 of 50000 | 0.19% |

| Pair | Difference in ln Z | Combined sigma | Disagreement (sigma) |
|---|---|---|---|
| T4f vs T4m/5 | -0.200 | 0.141 | 1.42 |

Event data (every dataset in each event data file's data group): the same across T4f, T4m/5: bit-identical.

### Weights

In units of each run's mean weight. A few heavy samples (a proposal missing part of the posterior) drag the efficiency down on their own; removing the heaviest then restores much of it.

| Run | Efficiency | Largest weight | Share of the 10 largest | Efficiency without the heaviest | Zero weights |
|---|---|---|---|---|---|
| T4f | 0.22% | 2881 | 22.95% | 0.30% | 223 |
| T4m/5 | 0.19% | 2500 | 25.31% | 0.22% | 227 |

The heaviest sample of each run:

| Column | T4f | T4m/5 |
|---|---|---|
| chirp_mass | 41.9881 | 40.1478 |
| mass_ratio | 0.780756 | 0.657697 |
| a_1 | 0.318033 | 0.0581604 |
| a_2 | 0.0583536 | 0.102639 |
| tilt_1 | 1.52499 | 2.44141 |
| tilt_2 | 0.554055 | 2.40482 |
| phi_12 | 4.27455 | 0.269695 |
| phi_jl | 5.13776 | 4.44225 |
| theta_jn | 1.76466 | 1.67107 |
| dec | 0.919231 | 0.0596297 |
| ra | 6.06863 | 2.10152 |
| geocent_time | 0.0116651 | -0.022036 |
| luminosity_distance | 2511.42 | 1445.59 |
| psi | 2.26546 | 2.00209 |
| lensing_delta_t | 0.00736926 | 0.00677239 |
| mu_rel | 0.130929 | 0.111242 |
| log_prob | -5.34355 | -2.96641 |
| phase | 2.56609 | 1.60452 |
| log_prior | -24.1591 | -23.7084 |
| log_likelihood | -6017.39 | -6015.41 |
| weights | 2880.8 | 2500.14 |

Weighted median [5%, 95%] of every parameter after importance sampling:

| Parameter | T4f | T4m/5 |
|---|---|---|
| chirp_mass | 41.02 [34.94, 45.67] | 40.76 [35.81, 45.64] |
| mass_ratio | 0.7706 [0.4508, 0.9694] | 0.721 [0.4705, 0.9667] |
| a_1 | 0.394 [0.03321, 0.9137] | 0.329 [0.04678, 0.8311] |
| a_2 | 0.3627 [0.05824, 0.8883] | 0.4666 [0.06456, 0.9226] |
| tilt_1 | 1.758 [0.6612, 2.684] | 1.792 [0.7016, 2.63] |
| tilt_2 | 1.69 [0.5541, 2.829] | 1.744 [0.7035, 2.748] |
| phi_12 | 3.182 [0.5611, 5.82] | 3.117 [0.2697, 6.064] |
| phi_jl | 3.624 [0.363, 5.972] | 4.031 [0.3672, 5.814] |
| theta_jn | 1.691 [0.3049, 2.818] | 1.671 [0.3094, 2.823] |
| dec | 0.0005762 [-0.9855, 0.9673] | -0.1569 [-0.9596, 0.9656] |
| ra | 3.39 [1.856, 6.069] | 2.738 [1.929, 5.842] |
| geocent_time | -0.004083 [-0.02964, 0.01303] | -0.02048 [-0.02969, 0.01222] |
| luminosity_distance | 3271 [1137, 7042] | 3583 [1446, 7622] |
| psi | 1.861 [0.2343, 3.001] | 1.765 [0.3146, 2.89] |
| lensing_delta_t | 0.007015 [0.0003256, 0.07847] | 0.006299 [0.0002542, 0.07563] |
| mu_rel | 0.1095 [0.003725, 0.9634] | 0.1258 [0.005539, 0.904] |
| phase | 2.784 [0.6175, 5.514] | 2.225 [0.5753, 5.706] |

## GW231206_233901: Agreement between runs

Network samples, two-sample KS per parameter: 16 tests over 2 runs, Bonferroni threshold 8.93e-05 (0.00142857 family-wise). Smallest p-value per pair:

| Pair | Smallest p | Parameter | KS statistic |
|---|---|---|---|
| T4g vs T4m/6 | 0.0604 | mu_rel | 0.0084 |

| Run | ln Z | sigma | Effective samples | Efficiency |
|---|---|---|---|---|
| T4g | -5874.541 | 0.495 | 4.1 of 50000 | 0.01% |
| T4m/6 | -5873.545 | 0.493 | 4.1 of 50000 | 0.01% |

| Pair | Difference in ln Z | Combined sigma | Disagreement (sigma) |
|---|---|---|---|
| T4g vs T4m/6 | -0.996 | 0.699 | 1.43 |

Event data (every dataset in each event data file's data group): the same across T4g, T4m/6: bit-identical.

### Weights

In units of each run's mean weight. A few heavy samples (a proposal missing part of the posterior) drag the efficiency down on their own; removing the heaviest then restores much of it.

| Run | Efficiency | Largest weight | Share of the 10 largest | Efficiency without the heaviest | Zero weights |
|---|---|---|---|---|---|
| T4g | 0.01% | 2.419e+04 | 76.19% | 0.05% | 567 |
| T4m/6 | 0.01% | 2.211e+04 | 84.13% | 0.01% | 534 |

The heaviest sample of each run:

| Column | T4g | T4m/6 |
|---|---|---|
| chirp_mass | 33.1465 | 35.9621 |
| mass_ratio | 0.523524 | 0.746404 |
| a_1 | 0.426292 | 0.306001 |
| a_2 | 0.358329 | 0.622211 |
| tilt_1 | 2.07916 | 1.07855 |
| tilt_2 | 1.93504 | 1.88862 |
| phi_12 | 5.29069 | 5.20457 |
| phi_jl | 0.68057 | 2.78079 |
| theta_jn | 0.821578 | 0.484934 |
| dec | 0.317063 | -0.0783898 |
| ra | 0.216017 | 6.10852 |
| geocent_time | 0.00491115 | 0.00493891 |
| luminosity_distance | 2512.2 | 2959.44 |
| psi | 0.898652 | 1.9607 |
| lensing_delta_t | 0.0017357 | 0.00258655 |
| mu_rel | 0.845216 | 0.726701 |
| log_prob | -1.84671 | -3.33711 |
| phase | 4.56031 | 6.14154 |
| log_prior | -23.3819 | -24.0496 |
| log_likelihood | -5842.91 | -5842.83 |
| weights | 24187.9 | 22109.6 |

Weighted median [5%, 95%] of every parameter after importance sampling:

| Parameter | T4g | T4m/6 |
|---|---|---|
| chirp_mass | 33.15 [30.74, 37.49] | 35.96 [32.94, 37.67] |
| mass_ratio | 0.5235 [0.4508, 0.9678] | 0.7464 [0.6093, 0.969] |
| a_1 | 0.4263 [0.1277, 0.915] | 0.306 [0.09398, 0.9572] |
| a_2 | 0.3583 [0.06625, 0.8144] | 0.6222 [0.04977, 0.7935] |
| tilt_1 | 2.079 [0.961, 2.25] | 1.115 [0.6883, 3.022] |
| tilt_2 | 1.935 [1.063, 2.398] | 1.889 [0.8487, 2.382] |
| phi_12 | 5.29 [1.17, 5.913] | 5.144 [1.11, 5.205] |
| phi_jl | 0.6806 [0.3036, 4.813] | 2.781 [0.3956, 5.609] |
| theta_jn | 0.8216 [0.1703, 2.506] | 0.485 [0.4633, 2.787] |
| dec | 0.3072 [-0.1893, 0.3171] | 0.05719 [-0.07846, 0.2444] |
| ra | 0.216 [0.05017, 6.269] | 6.109 [0.03913, 6.216] |
| geocent_time | 0.004911 [0.003184, 0.006953] | 0.004939 [0.004634, 0.006728] |
| luminosity_distance | 2512 [1038, 2512] | 2791 [1383, 2961] |
| psi | 0.8987 [0.1985, 2.723] | 1.961 [0.9675, 3.055] |
| lensing_delta_t | 0.001736 [0.0006107, 0.05688] | 0.002587 [0.001668, 0.01781] |
| mu_rel | 0.8452 [0.01084, 0.8452] | 0.7267 [0.01978, 0.9136] |
| phase | 4.56 [0.6455, 6.035] | 5.229 [1.446, 6.142] |

## Timing

**T4a** (1 event(s)): Wall time 6:55:10 from first submission to last job; per event: event 0 6:55:10. CPU 14.33 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4a_data0_1372029138-372559_generation_arg_0 | 0:12:37 | 0:03:31 | 0:01:14 | 0:00:00 | 0:00:47 | 0.64 / 1 | 373 / 8192 | 5.3 / 12 | 5.69 | 1 |
| T4a_data0_1372029138-372559_sampling_arg_0 | 0:19:24 | 0:01:00 | 0:04:58 | 0:00:00 | 0:53:52 | 11 / 16 | 285 / 16384 | 5 / 12 | 5.39 | 1 |
| T4a_data0_1372029138-372559_importance_sampling_arg_0 | 5:41:47 | 0:00:12 | 0:27:36 | 0:00:00 | 13:24:17 | 29 / 32 | 2984 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4a_data0_1372029138-372559_importance_sampling_plot_arg_0 | 0:00:06 | 0:00:11 | 0:02:05 | 0:00:00 | 0:01:04 | 0.51 / 1 | 163 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4b** (1 event(s)): Wall time 6:40:01 from first submission to last job; per event: event 0 6:40:01. CPU 7.88 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4b_data0_1372892993-476775_generation_arg_0 | 0:14:30 | 0:01:32 | 0:01:11 | 0:00:00 | 0:00:42 | 0.59 / 1 | 403 / 8192 | 5.3 / 12 | 5.65 | 1 |
| T4b_data0_1372892993-476775_sampling_arg_0 | 0:13:16 | 0:00:36 | 0:05:32 | 0:00:00 | 1:00:24 | 11 / 16 | 313 / 16384 | 5 / 12 | 5.39 | 1 |
| T4b_data0_1372892993-476775_importance_sampling_arg_0 | 5:47:13 | 0:00:06 | 0:14:42 | 0:00:00 | 6:51:06 | 28 / 32 | 2625 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4b_data0_1372892993-476775_importance_sampling_plot_arg_0 | 0:00:10 | 0:00:05 | 0:00:43 | 0:00:00 | 0:00:21 | 0.49 / 1 | 472 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4c** (1 event(s)): Wall time 6:57:32 from first submission to last job; per event: event 0 6:57:32. CPU 7.42 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4c_data0_1378725259-728516_generation_arg_0 | 0:15:50 | 0:00:30 | 0:01:22 | 0:00:00 | 0:00:53 | 0.65 / 1 | 365 / 8192 | 5.3 / 12 | 5.65 | 1 |
| T4c_data0_1378725259-728516_sampling_arg_0 | 1:57:12 | 0:00:21 | 0:01:42 | 0:00:00 | 0:13:31 | 8 / 16 | 402 / 16384 | 5 / 12 | 5.39 | 1 |
| T4c_data0_1378725259-728516_importance_sampling_arg_0 | 4:21:40 | 0:00:05 | 0:15:21 | 0:00:00 | 7:09:53 | 28 / 32 | 2574 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4c_data0_1378725259-728516_importance_sampling_plot_arg_0 | 0:00:38 | 0:00:12 | 0:02:15 | 0:00:00 | 0:01:10 | 0.52 / 1 | 143 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4d** (1 event(s)): Wall time 7:39:13 from first submission to last job; per event: event 0 7:39:13. CPU 4.03 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4d_data0_1379864330-918945_generation_arg_0 | 0:17:18 | 0:00:20 | 0:00:58 | 0:00:00 | 0:00:35 | 0.6 / 1 | 384 / 8192 | 5.3 / 12 | 5.65 | 1 |
| T4d_data0_1379864330-918945_sampling_arg_0 | 1:56:17 | 0:00:30 | 0:02:23 | 0:00:00 | 0:19:16 | 8.1 / 16 | 312 / 16384 | 5 / 12 | 5.39 | 1 |
| T4d_data0_1379864330-918945_importance_sampling_arg_0 | 5:08:47 | 0:00:03 | 0:07:35 | 0:00:00 | 3:41:13 | 29 / 32 | 2588 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4d_data0_1379864330-918945_importance_sampling_plot_arg_0 | 0:02:30 | 0:00:08 | 0:01:56 | 0:00:00 | 0:00:37 | 0.32 / 1 | 153 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4e** (1 event(s)): Wall time 7:54:32 from first submission to last job; per event: event 0 7:54:32. CPU 4.42 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4e_data0_1382944674-370605_generation_arg_0 | 0:17:31 | 0:00:32 | 0:01:22 | 0:00:00 | 0:00:55 | 0.67 / 1 | 369 / 8192 | 5.3 / 12 | 5.65 | 1 |
| T4e_data0_1382944674-370605_sampling_arg_0 | 1:55:28 | 0:00:30 | 0:05:11 | 0:00:00 | 0:52:28 | 10 / 16 | 303 / 16384 | 5 / 12 | 5.39 | 1 |
| T4e_data0_1382944674-370605_importance_sampling_arg_0 | 5:21:15 | 0:00:04 | 0:07:18 | 0:00:00 | 3:31:31 | 29 / 32 | 2757 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4e_data0_1382944674-370605_importance_sampling_plot_arg_0 | 0:04:01 | 0:00:05 | 0:00:45 | 0:00:00 | 0:00:23 | 0.51 / 1 | 415 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4f** (1 event(s)): Wall time 8:06:40 from first submission to last job; per event: event 0 8:06:40. CPU 7.85 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4f_data0_1385940712-527832_generation_arg_0 | 0:16:30 | 0:00:25 | 0:01:01 | 0:00:00 | 0:00:37 | 0.61 / 1 | 339 / 8192 | 5.2 / 12 | 5.62 | 1 |
| T4f_data0_1385940712-527832_sampling_arg_0 | 1:56:58 | 0:00:31 | 0:02:45 | 0:00:00 | 0:25:54 | 9.4 / 16 | 293 / 16384 | 5 / 12 | 5.39 | 1 |
| T4f_data0_1385940712-527832_importance_sampling_arg_0 | 5:22:46 | 0:00:04 | 0:15:49 | 0:00:00 | 7:23:37 | 28 / 32 | 2486 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4f_data0_1385940712-527832_importance_sampling_plot_arg_0 | 0:08:08 | 0:00:09 | 0:01:09 | 0:00:00 | 0:00:38 | 0.55 / 1 | 312 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4g** (1 event(s)): Wall time 2:45:47 from first submission to last job; per event: event 0 2:45:47. CPU 6.74 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4g_data0_1385941159-497681_generation_arg_0 | 0:14:30 | 0:01:31 | 0:00:53 | 0:00:00 | 0:00:33 | 0.62 / 1 | 382 / 8192 | 5.2 / 12 | 5.62 | 1 |
| T4g_data0_1385941159-497681_sampling_arg_0 | 0:07:37 | 0:00:34 | 0:05:21 | 0:00:00 | 0:57:26 | 11 / 16 | 300 / 16384 | 5 / 12 | 5.39 | 1 |
| T4g_data0_1385941159-497681_importance_sampling_arg_0 | 2:00:33 | 0:00:04 | 0:12:41 | 0:00:00 | 5:45:39 | 27 / 32 | 2891 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4g_data0_1385941159-497681_importance_sampling_plot_arg_0 | 0:00:16 | 0:00:08 | 0:01:15 | 0:00:00 | 0:00:28 | 0.37 / 1 | 301 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4m** (7 event(s)): Wall time 8:08:09 from first submission to last job; per event: event 0 8:08:09, event 1 6:26:07, event 2 7:02:10, event 3 7:25:53, event 4 7:36:58, event 5 6:54:14, event 6 7:09:03. CPU 49.04 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4m_data0_1372029138-372559_generation_arg_0 | 0:16:55 | 0:00:22 | 0:00:59 | 0:00:00 | 0:00:37 | 0.63 / 1 | 390 / 8192 | 6.5 / 12 | 6.94 | 1 |
| T4m_data1_1372892993-476775_generation_arg_0 | 0:00:40 | 0:00:44 | 0:01:53 | 0:00:00 | 0:01:14 | 0.65 / 1 | 250 / 8192 | 6.5 / 12 | 6.94 | 1 |
| T4m_data2_1378725259-728516_generation_arg_0 | 0:00:39 | 0:00:42 | 0:01:55 | 0:00:00 | 0:01:01 | 0.53 / 1 | 99 / 8192 | 6.5 / 12 | 6.94 | 1 |
| T4m_data3_1379864330-918945_generation_arg_0 | 0:01:01 | 0:00:41 | 0:01:18 | 0:00:00 | 0:00:54 | 0.69 / 1 | 390 / 8192 | 6.5 / 12 | 6.94 | 1 |
| T4m_data4_1382944674-370605_generation_arg_0 | 0:00:24 | 0:00:36 | 0:00:52 | 0:00:00 | 0:00:32 | 0.62 / 1 | 589 / 8192 | 6.5 / 12 | 6.94 | 1 |
| T4m_data5_1385940712-527832_generation_arg_0 | 0:00:17 | 0:00:28 | 0:00:58 | 0:00:00 | 0:00:34 | 0.59 / 1 | 379 / 8192 | 6.5 / 12 | 6.94 | 1 |
| T4m_data6_1385941159-497681_generation_arg_0 | 0:00:13 | 0:00:27 | 0:01:03 | 0:00:00 | 0:00:38 | 0.6 / 1 | 395 / 8192 | 6.5 / 12 | 6.94 | 1 |
| T4m_data0_1372029138-372559_sampling_arg_0 | 1:56:39 | 0:00:31 | 0:06:15 | 0:00:00 | 1:03:43 | 10 / 16 | 2358 / 16384 | 5 / 12 | 5.39 | 1 |
| T4m_data1_1372892993-476775_sampling_arg_0 | 1:53:12 | 0:00:22 | 0:01:11 | 0:00:00 | 0:11:35 | 9.8 / 16 | 3627 / 16384 | 5 / 12 | 5.39 | 1 |
| T4m_data2_1378725259-728516_sampling_arg_0 | 1:53:12 | 0:00:30 | 0:02:07 | 0:00:00 | 0:16:35 | 7.8 / 16 | 300 / 16384 | 5 / 12 | 5.39 | 1 |
| T4m_data3_1379864330-918945_sampling_arg_0 | 1:53:27 | 0:00:25 | 0:02:24 | 0:00:00 | 0:23:36 | 9.8 / 16 | 342 / 16384 | 5 / 12 | 5.39 | 1 |
| T4m_data4_1382944674-370605_sampling_arg_0 | 1:54:37 | 0:00:30 | 0:03:26 | 0:00:00 | 0:36:09 | 11 / 16 | 343 / 16384 | 5 / 12 | 5.39 | 1 |
| T4m_data5_1385940712-527832_sampling_arg_0 | 1:54:47 | 0:00:23 | 0:02:04 | 0:00:00 | 0:19:26 | 9.4 / 16 | 410 / 16384 | 5 / 12 | 5.39 | 1 |
| T4m_data6_1385941159-497681_sampling_arg_0 | 1:54:47 | 0:00:30 | 0:02:10 | 0:00:00 | 0:16:26 | 7.6 / 16 | 306 / 16384 | 5 / 12 | 5.39 | 1 |
| T4m_data0_1372029138-372559_importance_sampling_arg_0 | 5:26:39 | 0:00:05 | 0:18:00 | 0:00:00 | 8:38:41 | 29 / 32 | 2722 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4m_data1_1372892993-476775_importance_sampling_arg_0 | 4:07:57 | 0:00:05 | 0:17:59 | 0:00:00 | 8:26:10 | 28 / 32 | 2765 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4m_data2_1378725259-728516_importance_sampling_arg_0 | 4:53:07 | 0:00:04 | 0:07:57 | 0:00:01 | 3:48:54 | 29 / 32 | 2395 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4m_data3_1379864330-918945_importance_sampling_arg_0 | 5:08:10 | 0:00:04 | 0:14:58 | 0:00:00 | 7:03:02 | 28 / 32 | 2558 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4m_data4_1382944674-370605_importance_sampling_arg_0 | 5:18:38 | 0:00:05 | 0:14:20 | 0:00:00 | 6:36:43 | 28 / 32 | 2740 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4m_data5_1385940712-527832_importance_sampling_arg_0 | 4:45:18 | 0:00:04 | 0:07:54 | 0:00:00 | 3:48:22 | 29 / 32 | 2409 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4m_data6_1385941159-497681_importance_sampling_arg_0 | 4:52:00 | 0:00:04 | 0:15:26 | 0:00:00 | 7:24:03 | 29 / 32 | 2441 / 8192 | 0.82 / 12 | 0.878 | 1 |
| T4m_data0_1372029138-372559_importance_sampling_plot_arg_0 | 0:00:24 | 0:00:05 | 0:00:49 | 0:00:00 | 0:00:26 | 0.53 / 1 | 365 / 32768 | 0.82 / 12 | 0.879 | 1 |
| T4m_data1_1372892993-476775_importance_sampling_plot_arg_0 | 0:00:20 | 0:00:08 | 0:01:08 | 0:00:00 | 0:00:29 | 0.43 / 1 | 212 / 32768 | 0.82 / 12 | 0.879 | 1 |
| T4m_data2_1378725259-728516_importance_sampling_plot_arg_0 | 0:00:33 | 0:00:04 | 0:00:51 | 0:00:00 | 0:00:26 | 0.51 / 1 | 374 / 32768 | 0.82 / 12 | 0.879 | 1 |
| T4m_data3_1379864330-918945_importance_sampling_plot_arg_0 | 0:02:05 | 0:00:05 | 0:00:45 | 0:00:00 | 0:00:25 | 0.56 / 1 | 407 / 32768 | 0.82 / 12 | 0.879 | 1 |
| T4m_data4_1382944674-370605_importance_sampling_plot_arg_0 | 0:02:13 | 0:00:05 | 0:00:46 | 0:00:00 | 0:00:23 | 0.5 / 1 | 411 / 32768 | 0.82 / 12 | 0.879 | 1 |
| T4m_data5_1385940712-527832_importance_sampling_plot_arg_0 | 0:00:15 | 0:00:08 | 0:01:09 | 0:00:00 | 0:00:39 | 0.57 / 1 | 330 / 32768 | 0.82 / 12 | 0.879 | 1 |
| T4m_data6_1385941159-497681_importance_sampling_plot_arg_0 | 0:00:41 | 0:00:09 | 0:01:05 | 0:00:00 | 0:00:37 | 0.57 / 1 | 267 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4ua** (1 event(s)): Wall time 7:44:36 from first submission to last job; per event: event 0 7:44:36. CPU 4.20 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4ua_data0_1372029138-372559_generation_arg_0 | 0:15:50 | 0:00:24 | 0:01:23 | 0:00:00 | 0:00:56 | 0.67 / 1 | 339 / 8192 | 5.3 / 12 | 5.68 | 1 |
| T4ua_data0_1372029138-372559_sampling_arg_0 | 1:57:17 | 0:00:27 | 0:02:51 | 0:00:00 | 0:28:42 | 10 / 16 | 286 / 16384 | 5 / 12 | 5.39 | 1 |
| T4ua_data0_1372029138-372559_importance_sampling_arg_0 | 5:16:01 | 0:00:04 | 0:07:33 | 0:00:00 | 3:41:52 | 29 / 32 | 2501 / 8192 | 0.82 / 12 | 0.877 | 1 |
| T4ua_data0_1372029138-372559_importance_sampling_plot_arg_0 | 0:00:35 | 0:00:09 | 0:01:35 | 0:00:00 | 0:00:34 | 0.36 / 1 | 172 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4ub** (1 event(s)): Wall time 2:33:21 from first submission to last job; per event: event 0 2:33:21. CPU 6.36 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4ub_data0_1372892993-476775_generation_arg_0 | 0:14:30 | 0:00:53 | 0:01:05 | 0:00:00 | 0:00:39 | 0.6 / 1 | 411 / 8192 | 5.3 / 12 | 5.64 | 1 |
| T4ub_data0_1372892993-476775_sampling_arg_0 | 0:01:13 | 0:00:34 | 0:06:12 | 0:00:00 | 1:05:37 | 11 / 16 | 2351 / 16384 | 5 / 12 | 5.39 | 1 |
| T4ub_data0_1372892993-476775_importance_sampling_arg_0 | 1:55:16 | 0:00:04 | 0:11:08 | 0:00:00 | 5:15:05 | 28 / 32 | 3110 / 8192 | 0.82 / 12 | 0.877 | 1 |
| T4ub_data0_1372892993-476775_importance_sampling_plot_arg_0 | 0:01:11 | 0:00:05 | 0:00:42 | 0:00:00 | 0:00:20 | 0.48 / 1 | 389 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4uc** (1 event(s)): Wall time 7:37:58 from first submission to last job; per event: event 0 7:37:58. CPU 8.62 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4uc_data0_1378725259-728516_generation_arg_0 | 0:17:40 | 0:00:30 | 0:01:17 | 0:00:00 | 0:00:50 | 0.65 / 1 | 327 / 8192 | 5.3 / 12 | 5.64 | 1 |
| T4uc_data0_1378725259-728516_sampling_arg_0 | 1:55:27 | 0:00:25 | 0:02:13 | 0:00:00 | 0:22:37 | 10 / 16 | 409 / 16384 | 5 / 12 | 5.39 | 1 |
| T4uc_data0_1378725259-728516_importance_sampling_arg_0 | 5:01:34 | 0:00:05 | 0:17:25 | 0:00:00 | 8:13:10 | 28 / 32 | 2883 / 8192 | 0.82 / 12 | 0.877 | 1 |
| T4uc_data0_1378725259-728516_importance_sampling_plot_arg_0 | 0:00:02 | 0:00:04 | 0:00:47 | 0:00:00 | 0:00:23 | 0.49 / 1 | 364 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4ud** (1 event(s)): Wall time 7:21:27 from first submission to last job; per event: event 0 7:21:27. CPU 8.84 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4ud_data0_1379864330-918945_generation_arg_0 | 0:17:08 | 0:00:38 | 0:01:41 | 0:00:00 | 0:01:08 | 0.67 / 1 | 260 / 8192 | 5.3 / 12 | 5.64 | 1 |
| T4ud_data0_1379864330-918945_sampling_arg_0 | 1:55:27 | 0:00:21 | 0:01:58 | 0:00:00 | 0:20:21 | 10 / 16 | 408 / 16384 | 5 / 12 | 5.39 | 1 |
| T4ud_data0_1379864330-918945_importance_sampling_arg_0 | 4:44:02 | 0:00:05 | 0:17:46 | 0:00:00 | 8:28:37 | 29 / 32 | 2678 / 8192 | 0.82 / 12 | 0.877 | 1 |
| T4ud_data0_1379864330-918945_importance_sampling_plot_arg_0 | 0:01:04 | 0:00:05 | 0:00:45 | 0:00:00 | 0:00:23 | 0.51 / 1 | 385 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4ue** (1 event(s)): Wall time 7:11:20 from first submission to last job; per event: event 0 7:11:20. CPU 7.37 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4ue_data0_1382944674-370605_generation_arg_0 | 0:15:50 | 0:00:29 | 0:01:34 | 0:00:00 | 0:00:59 | 0.63 / 1 | 274 / 8192 | 5.3 / 12 | 5.64 | 1 |
| T4ue_data0_1382944674-370605_sampling_arg_0 | 1:57:02 | 0:00:26 | 0:01:51 | 0:00:00 | 0:18:13 | 9.8 / 16 | 368 / 16384 | 5 / 12 | 5.39 | 1 |
| T4ue_data0_1382944674-370605_importance_sampling_arg_0 | 4:37:16 | 0:00:04 | 0:15:05 | 0:00:00 | 7:02:41 | 28 / 32 | 2554 / 8192 | 0.82 / 12 | 0.877 | 1 |
| T4ue_data0_1382944674-370605_importance_sampling_plot_arg_0 | 0:00:07 | 0:00:08 | 0:01:07 | 0:00:00 | 0:00:36 | 0.54 / 1 | 284 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4uf** (1 event(s)): Wall time 7:05:00 from first submission to last job; per event: event 0 7:05:00. CPU 4.07 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4uf_data0_1385940712-527832_generation_arg_0 | 0:17:14 | 0:00:25 | 0:01:01 | 0:00:00 | 0:00:37 | 0.61 / 1 | 396 / 8192 | 5.2 / 12 | 5.61 | 1 |
| T4uf_data0_1385940712-527832_sampling_arg_0 | 1:56:17 | 0:00:22 | 0:01:53 | 0:00:00 | 0:20:11 | 11 / 16 | 2714 / 16384 | 5 / 12 | 5.39 | 1 |
| T4uf_data0_1385940712-527832_importance_sampling_arg_0 | 4:37:51 | 0:00:04 | 0:07:37 | 0:00:00 | 3:42:57 | 29 / 32 | 2442 / 8192 | 0.82 / 12 | 0.877 | 1 |
| T4uf_data0_1385940712-527832_importance_sampling_plot_arg_0 | 0:00:22 | 0:00:09 | 0:01:21 | 0:00:00 | 0:00:41 | 0.51 / 1 | 263 / 32768 | 0.82 / 12 | 0.879 | 1 |

**T4ug** (1 event(s)): Wall time 7:03:28 from first submission to last job; per event: event 0 7:03:28. CPU 8.89 h, wasted on failed attempts 0.00 h.

| Job | Wait | Input transfer | Run | Output transfer | CPU | Cores used / requested | Memory used / requested (MB) | Disk used / requested (GB) | Received (GB) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4ug_data0_1385941159-497681_generation_arg_0 | 0:15:50 | 0:00:28 | 0:01:11 | 0:00:00 | 0:00:48 | 0.68 / 1 | 356 / 8192 | 5.2 / 12 | 5.61 | 1 |
| T4ug_data0_1385941159-497681_sampling_arg_0 | 1:57:27 | 0:00:24 | 0:01:42 | 0:00:00 | 0:17:08 | 10 / 16 | 402 / 16384 | 5 / 12 | 5.39 | 1 |
| T4ug_data0_1385941159-497681_importance_sampling_arg_0 | 4:25:31 | 0:00:05 | 0:18:06 | 0:00:00 | 8:34:58 | 28 / 32 | 2716 / 8192 | 0.82 / 12 | 0.877 | 1 |
| T4ug_data0_1385941159-497681_importance_sampling_plot_arg_0 | 0:00:27 | 0:00:09 | 0:01:42 | 0:00:00 | 0:00:47 | 0.46 / 1 | 148 / 32768 | 0.82 / 12 | 0.879 | 1 |

