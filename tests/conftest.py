"""Deterministic small fixtures shared by compatibility regression tests."""

from copy import deepcopy
from pathlib import Path

import pytest

from dingo_lensing.toy_two_image import read_config, seed_everything


@pytest.fixture
def config():
    """Use the real example configuration with a tiny dataset."""
    path = Path(__file__).parents[1] / "examples/toy_two_image_npe/config.yaml"
    value = deepcopy(read_config(path))
    value.update(
        num_samples=16, epochs=1, batch_size=8, posterior_samples=32, threads=1
    )
    value["model"]["embedding_kwargs"]["svd"].update(
        num_training_samples=8, num_validation_samples=4, size=4
    )
    seed_everything(value["seed"], 1)
    return value


@pytest.fixture
def event(config):
    """Build one noisy event and metadata without training a network."""
    from dingo.gw.domains import build_domain

    from dingo_lensing.injection import LensedInjection
    from dingo_lensing.toy_two_image import dataset_settings, make_asds

    settings = dataset_settings(config)
    extrinsic = dict(
        config["extrinsic"], luminosity_distance=1000.0, geocent_time=0.0
    )
    metadata = {
        "dataset_settings": settings,
        "train_settings": {
            "data": {
                "extrinsic_prior": extrinsic,
                "detectors": config["detectors"],
                "ref_time": config["ref_time"],
                "inference_parameters": ["mu_rel", "lensing_delta_t"],
            },
            "model": deepcopy(config["model"]),
        },
    }
    generator = LensedInjection.from_posterior_model_metadata(metadata)
    generator.asd = make_asds(
        build_domain(settings["domain"]), config["detectors"]
    )
    theta = {k: float(v) for k, v in generator.prior.sample().items()}
    theta.update(config["injection"])
    return metadata, generator.injection(theta), theta
