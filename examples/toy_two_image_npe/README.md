# Two-image toy NPE on local CPU

This example runs DINGO 0.10.3 with DINGO-Lensing's existing
`modwaveforms/two_images_BBH` model. It uses actual IMRPhenomD BBH waveforms,
10,000 training signals, 20–1024 Hz with 0.25 Hz spacing (4,097 stored bins),
20 epochs, batch size 64, and four local CPU threads. No scheduler or GPU.

Only `mu_rel` and `lensing_delta_t` are inferred. Masses, spins, orientation,
sky position, distance, source phase, and relative image phase are fixed.
H1/L1 design ASDs come from Bilby's bundled detector files. Gaussian noise is
resampled during training. Distance is fixed to give unlensed network SNR 15.
These conditional toy assumptions differ from the upstream example's broad
source priors and downloaded O1 noise. This is an execution example, not a
production analysis or posterior-calibration study.

## Run in the supplied workspace

From the workspace containing `run-local.sh` and `dingo-lensing/`:

```bash
./run-local.sh dingo-lensing/examples/toy_two_image_npe/run.py all \
  --config dingo-lensing/examples/toy_two_image_npe/config.yaml \
  --outdir artifacts/my_two_image_run
```

Use a fresh output directory. Generated settings store absolute data paths;
regenerate them if moving the workspace. `run-local.sh` selects the dedicated
Conda prefix and keeps caches, temporary files, and bytecode policy local.

To run stages separately:

```bash
./run-local.sh -m dingo_lensing.toy_two_image prepare \
  --config dingo-lensing/examples/toy_two_image_npe/config.yaml \
  --outdir artifacts/my_two_image_run
./run-local.sh -m dingo_lensing.toy_two_image train --outdir artifacts/my_two_image_run
./run-local.sh -m dingo_lensing.toy_two_image inference --outdir artifacts/my_two_image_run
./run-local.sh -m dingo_lensing.toy_two_image importance --outdir artifacts/my_two_image_run
```

The training stage calls upstream `run_training` without modifying DINGO.
Generated `train_settings.yaml` can also be passed to stock `dingo_train`.
The example runner seeds NumPy, Bilby, and PyTorch explicitly; a standalone
`dingo_train` invocation needs equivalent seeding for repeatable initialization.

Edit `config.yaml` to change dataset size, epochs, batch size, network settings,
posterior sample count, seed, or CPU thread count. Keep `device: cpu` in generated
training settings. Datasets use full frequency resolution; the embedding uses
the same kind of SVD-initialized projection as upstream toy NPE.

## Physical and density conventions

The existing backend implements

```text
F(f) = conjugate(1 + sqrt(mu_rel) *
                 exp(i * (2*pi*f*lensing_delta_t - sign(f)*Delta_phase)))
```

The first-image amplitude is one. `mu_rel` enters through its square root;
`Delta_phase` defaults to pi/2. Conjugation preserves the vendor's LALSuite
Fourier convention. The example calls this implementation, not a second lens
simulator. Delay phases use float64 even when a domain stores float32 frequencies.

Proposal `log_prob` comes from the upstream composed sampler in physical
coordinates, including standardization Jacobians. Fixed source parameters use
Delta priors and are not additional continuous proposal dimensions. Training and
target lens priors agree. No marginalization or synthetic parameters are used.

Importance sampling calls upstream `Result.importance_sample`. It verifies
`log_w = log_likelihood + log_prior - log_prob`; DINGO stores mean-one weights.
Out-of-prior proposals get zero weight. Diagnostics normalize to sum one for ESS.
The evidence estimate is `logsumexp(log_w) - log(N)`, including zero-weight draws.
The likelihood omits its PSD-dependent additive normalization, following DINGO;
reported log evidence uses that convention. Weights are not clipped.

## Outputs

- `waveforms.hdf5`, `asds.hdf5`: training data.
- `config.yaml`, `waveform_dataset_settings.yaml`, `train_settings.yaml`: settings.
- `training/model_latest.pt`, `training/model_stage_0.pt`: trained model.
- `training/history.txt`: losses and learning rate for each epoch.
- `injection.yaml`: held-out injection parameters.
- `proposal.hdf5`: original NPE samples, proposal densities, and observation.
- `importance.hdf5`: target likelihoods, priors, weights, and evidence.
- `posterior.csv`: importance-resampled inferred parameters.
- `diagnostics.json`, `posterior.png`: numerical checks and comparison plot.

The completed run is under workspace `artifacts/toy_two_image/`:
5,000 proposal samples; 4,323 within target prior; ESS 3,222.69;
efficiency 64.45%; maximum normalized weight 0.00075323.
Injected values: `mu_rel=0.4`, `lensing_delta_t=0.008` seconds.
This single injection demonstrates execution and weight consistency only.

## Tests and CI

From workspace:

```bash
./run-local.sh -m pytest dingo-lensing/tests -q
./run-local.sh -m pytest dingo-lensing/tests/test_toy_two_image.py -m heavy -q
```

Normal CI runs fast tests including real network initialization without training.
The explicit `heavy` test runs 128 signals and one CPU epoch. It is excluded by
default. The full example is run manually. Local results do not establish that
GitHub Actions has executed successfully.

## Reproduce installation

Source revisions:

- DINGO 0.10.3: `4043464f3d1d5080d2cbeda858289c17ab7ec404`.
- DINGO-Lensing baseline: `c9d916b41db0ebac5277ae331a5a1cdc0b1edaa3`.
- modwaveforms: `fa692172c831160e9e615689caf6ed045f60a494`.
- Gravelamps: `5545fa16561db99d02aff404b3282fc85be6ff7b`.

Use the published DINGO wheel, not an editable upstream installation. Its SHA256:
`752b582b3cc8fa24395ca9ea8a0aeb6b3595237da401093f0db522b14c22d444`.
Upstream source snapshot remains read-only and is not on `PYTHONPATH`.

From workspace, in a **fresh** destination prefix:

```bash
export CONDA_NO_PLUGINS=true CONDA_SOLVER=classic CONDA_REGISTER_ENVS=false
export CONDA_PKGS_DIRS="$PWD/cache/conda" CONDA_ENVS_PATH="$PWD/envs"
export TMPDIR="$PWD/tmp" PIP_CACHE_DIR="$PWD/cache/pip"
export XDG_CACHE_HOME="$PWD/cache/xdg" MPLCONFIGDIR="$PWD/cache/matplotlib"
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
mkdir -p "$TMPDIR" "$PIP_CACHE_DIR" "$CONDA_PKGS_DIRS" "$MPLCONFIGDIR"
TASK_PREFIX="$PWD/envs/dingo_lensing_version_match"
conda create -y --prefix "$TASK_PREFIX" \
  --file dingo-lensing/examples/toy_two_image_npe/reproducibility/conda-linux-64.explicit.txt
```

`environment-version-match.yml` provides a more portable native environment
specification; the explicit file fixes the tested Linux builds. This host's
Conda libmamba plugin fails to load, so the settings above select its working
classic solver without changing base Conda. Registration is disabled to avoid
writing the external environment registry.

Gravelamps requires native FLINT >=3 libraries, Boost's `math_c99`, a C++20
compiler, and CMake >=3.27. Tested compiler: GCC 11.5.0, CMake 3.31.8, system
Boost 1.75.0. No system packages were changed. Set `BOOST_CMAKE_DIR` explicitly
when another active Conda's Boost would otherwise be detected:

```bash
export BOOST_CMAKE_DIR=/usr/lib64/cmake/Boost-1.75.0  # Tested host; adapt on other hosts.
bash dingo-lensing/scripts/install_gravelamps_native.sh \
  "$TASK_PREFIX" "$PWD/cache/gravelamps-native"
export CPLUS_INCLUDE_PATH="$TASK_PREFIX/include"
export LIBRARY_PATH="$TASK_PREFIX/lib"
export LD_LIBRARY_PATH="$TASK_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export LDFLAGS="-L$TASK_PREFIX/lib -Wl,-rpath,$TASK_PREFIX/lib"
"$TASK_PREFIX/bin/python" -m pip install \
  -r dingo-lensing/examples/toy_two_image_npe/reproducibility/requirements-linux-64.txt
"$TASK_PREFIX/bin/python" -m pip install --no-deps --no-build-isolation -e ./dingo-lensing
"$TASK_PREFIX/bin/python" -m pip check
```

The pip lock records the tested CPU PyTorch pair and dependency versions.
Pinned source archives avoid Git checkouts during installation. On hosts without
Boost development libraries, install them into the dedicated prefix; CI does this
with Conda. Do not point native discovery at an unrelated environment.

A normal wheel was also built and installed separately to verify that pipeline
subpackages ship correctly. Workspace installation/build logs and source
checksums are under `artifacts/`.
