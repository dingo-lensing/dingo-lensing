# Waveform Generator Development Notes

This directory contains a local development setup for generating a lensed waveform
dataset with `dingo_lensing_generate_dataset`.

## Files

- `waveform_dataset_settings.yaml`: dataset and waveform generation settings
- `dingo_generate_dataset.sh`: launcher script for dataset generation
- `training_data/waveform_dataset.hdf5`: generated dataset output

## Dev Mode

The settings file supports a top-level flag:

```yaml
dev_mode: true
```

Behavior:

- `dev_mode: false` or omitted:
  normal dataset generation only
- `dev_mode: true`:
  generates the dataset and also saves waveform comparison plots

Each dev-mode plot overlays:

- the nonlensed waveform
- the lensed waveform

The comparison is generated from the same sample at the point where both versions
are already available, so dev-mode plotting does not recompute the waveform.

## Plot Output

When `dev_mode: true`, plots are written to:

```text
dev_plots/waveform
```

relative to this settings directory.

Example filename:

```text
waveform_sample_000000.png
```

Plot properties:

- sample index is included in the filename
- lensed and nonlensed traces are labeled in the legend
- x-axis is frequency in Hz
- y-axis is strain amplitude

## Run

From this directory, run:

```bash
bash dingo_generate_dataset.sh
```

This executes:

```bash
dingo_lensing_generate_dataset \
  --settings_file waveform_dataset_settings.yaml \
  --out_file training_data/waveform_dataset.hdf5
```

## Toggle Dev Mode

Enable:

```yaml
dev_mode: true
```

Disable:

```yaml
dev_mode: false
```

If `dev_mode` is disabled, dataset generation proceeds normally and no new dev
plots are written.
