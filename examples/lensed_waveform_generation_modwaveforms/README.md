# Dingo Lensing Dataset Example

This example uses the native `dingo_lensing_generate_dataset` command from the
`dingo_lensing` conda environment. It does not depend on absolute paths from the
machine where it was created.

## Contents

- `waveform_dataset_lensed_100000_svd.yaml`: production settings for `100000`
  SVD-compressed lensed waveforms.
- `waveform_dataset_lensed_smoke.yaml`: tiny settings file for a quick command
  check.
- `generate_lensed_dataset.sh`: relative-path shell launcher.
- `data/smoke_test_lensed_svd.hdf5`: small verified smoke-test output, if present.
- `data/waveform_dataset_lensed_100000_svd.hdf5`: full production output created
  by the default shell command.

## Settings

The production YAML is based on the nonlensed waveform settings and adds the
two lensing parameters expected by `dingo_lensing`:

```yaml
lensing_delta_t: bilby.gw.prior.Uniform(minimum=0.0, maximum=0.1)
mu_rel: bilby.gw.prior.Uniform(minimum=0.0, maximum=1.0)
```

This corresponds to relative time delays from `0` to `100 ms` and relative
magnifications from `0` to `1`.

The default production settings use:

- `IMRPhenomXPNR`
- `f_min = 20 Hz`, `f_max = 1024 Hz`, `delta_f = 0.0625 Hz`
- chirp mass from `10` to `180`
- mass ratio from `0.1` to `1.0`
- `dev_mode: false`
- SVD size `300`
- `50000` SVD training waveforms
- `10000` SVD validation waveforms
- `100000` final compressed waveforms

## Environment

Activate an environment that provides `dingo_lensing_generate_dataset`. On the
original system this is:

```bash
conda activate dingo_lensing
```

If the command is not already on `PATH`, `generate_lensed_dataset.sh` falls back
to `conda run -n dingo_lensing`. Set `CONDA_ENV_NAME` if your environment has a
different name.

## Generate The Full Dataset

From this directory:

```bash
bash generate_lensed_dataset.sh
```

Optional controls:

```bash
NUM_PROCESSES=4 CONDA_ENV_NAME=dingo_lensing ./generate_lensed_dataset.sh
```

The full output is written to:

```text
data/waveform_dataset_lensed_100000_svd.hdf5
```

## Smoke Test

Use the small settings file to check the installed command quickly:

```bash
SETTINGS_FILE=waveform_dataset_lensed_smoke.yaml \
OUT_FILE=data/smoke_test_lensed_svd.hdf5 \
./generate_lensed_dataset.sh
```
