"""Run the full shared example only when explicitly requested."""

import json

import pytest

from dingo_lensing.toy_two_image import (
    importance_sampling,
    inference,
    prepare,
    train,
)


@pytest.mark.heavy
def test_cpu_pipeline(config, tmp_path):
    config["num_samples"] = 128
    config["batch_size"] = 16
    config["posterior_samples"] = 128
    prepare(config, tmp_path)
    train(tmp_path)
    inference(tmp_path)
    importance_sampling(tmp_path)
    report = json.loads((tmp_path / "diagnostics.json").read_text())
    assert report["weight_formula_verified"]
    assert report["effective_sample_size"] > 0
    assert (tmp_path / "posterior.csv").exists()


def test_data_and_network_initialization(config, tmp_path):
    """Normal CI initializes the real network without training it."""
    import numpy as np
    import torch
    from dingo.gw.training.train_pipeline import prepare_training_new

    from dingo_lensing.toy_two_image import read_config

    prepare(config, tmp_path)
    settings = read_config(tmp_path / "train_settings.yaml")
    local = settings.pop("local")
    model, dataset = prepare_training_new(settings, str(tmp_path), local)
    model.network.eval()
    context = torch.from_numpy(dataset[0][1][None])
    with torch.no_grad():
        samples, log_prob = model.sample_and_log_prob(context, num_samples=4)
    assert np.isfinite(samples.numpy()).all()
    assert np.isfinite(log_prob.numpy()).all()
