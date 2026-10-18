"""Dataset adapter regression tests."""

from copy import deepcopy

import numpy as np
import pytest
from dingo.gw.dataset.waveform_dataset import WaveformDataset

from dingo_lensing.generate_dataset import generate_dataset
from dingo_lensing.toy_two_image import dataset_settings


@pytest.mark.parametrize(
    "compression",
    [
        None,
        {
            "svd": {
                "size": 2,
                "num_training_samples": 4,
                "num_validation_samples": 2,
            }
        },
    ],
)
def test_generate_and_reload(config, tmp_path, compression):
    settings = dataset_settings(config)
    settings["num_samples"] = 4
    settings["compression"] = compression
    original = deepcopy(settings)
    dataset = generate_dataset(settings)
    assert len(dataset.parameters) == 4
    assert settings == original
    assert all(np.isfinite(v).all() for v in dataset.polarizations.values())
    path = tmp_path / "waveforms.hdf5"
    dataset.to_file(path)
    loaded = WaveformDataset(file_name=path)
    assert len(loaded.domain) == 4097
    assert "mu_rel" in loaded.parameters


def test_parallel_generation(config):
    settings = dataset_settings(config)
    settings["num_samples"] = 2
    dataset = generate_dataset(settings, num_processes=2)
    assert len(dataset.parameters) == 2
