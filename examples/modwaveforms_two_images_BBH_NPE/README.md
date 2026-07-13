# Dingo Lensing modwaveforms two images BBH NPE Example

This example uses two images BBH in modwaveforms to train NPE model.

## Contents

- `waveform_dataset_settings_two_images_BBH.yaml`: production settings for `5000000`
  SVD-compressed lensed waveforms.
  check.
- `generate_lensed_dataset.sh`: shell launcher for generate lensed waveform dataset using `dingo_lensing_generate_dataset`.
- `training_data/waveform_dataset_xphm.hdf5`: full production output created
  by the default shell command.
- `train_settings_xphm_prod.yaml`: training setting.
- `asd_dataset.hdf5`: asd dataset for training 
- `dingo_train.sh`: shell launcher for training the model using `dingo_train`.

## Settings

The production YAML is based on the nonlensed waveform settings and adds the
two lensing parameters expected by `dingo_lensing`:

```yaml
lensing_delta_t: bilby.gw.prior.Uniform(minimum=0.0, maximum=0.1)
mu_rel: bilby.gw.prior.Uniform(minimum=0.0, maximum=1.0)
```

## Generate The Full Dataset

```bash
bash generate_lensed_dataset.sh
```

## Train The Model

specify the GPU in `export CUDA_VISIBLE_DEVICES=` and start the training with

```bash
bash dingo_train.sh
```
