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
  generates the dataset and also saves waveform comparison and amplification
  factor plots

Each waveform comparison plot overlays:

- the nonlensed waveform
- the lensed waveform

Each amplification factor plot shows:

- the amplification magnitude
- the unwrapped amplification phase

## One-image phase shifts

`one_image_BBH` accepts an optional, case-sensitive `Delta_phase` entry in
`intrinsic_prior`. The phase is expressed in radians. If `Delta_phase` is
omitted, the Modwaveforms backend retains the backward-compatible default of
`pi / 2`.

The example settings include three configurations:

- `waveform_dataset_settings_one_image_BBH.yaml`: omit `Delta_phase` and use
  the default `pi / 2`
- `waveform_dataset_settings_one_image_BBH_fixed_phase.yaml`: use a fixed
  phase of `1.0` rad
- `waveform_dataset_settings_one_image_BBH_sampled_phase.yaml`: sample the
  phase uniformly from `0` to `2 * pi`

A fixed phase is configured as a number:

```yaml
intrinsic_prior:
  Delta_phase: 1.0
```

An arbitrary sampled phase is configured as a Bilby prior:

```yaml
intrinsic_prior:
  Delta_phase: bilby.core.prior.Uniform(minimum=0.0, maximum=6.283185307179586)
```

The comparison is generated from the same sample at the point where both versions
are already available, so dev-mode plotting does not recompute the waveform.

## Plot Output

When `dev_mode: true`, plots are written to:

```text
dev_plots/<lens model>/waveform
dev_plots/<lens model>/amplification_factor
```

relative to this settings directory.

Example filenames:

```text
dev_plots/two_images_BBH/waveform/waveform_sample_000000.png
dev_plots/two_images_BBH/amplification_factor/amplification_sample_000000.png
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
