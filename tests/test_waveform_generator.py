"""Physical and API regression tests for the existing two-image backend."""

import pickle
from copy import deepcopy

import numpy as np
from dingo.gw.domains import build_domain
from dingo.gw.waveform_generator import WaveformGenerator

from dingo_lensing.toy_two_image import dataset_settings
from dingo_lensing.waveform_generator import LensedWaveformGenerator


def test_two_image_and_unlensed_limit(config):
    settings = dataset_settings(config)
    domain = build_domain(settings["domain"])
    generator = LensedWaveformGenerator(
        domain=domain, **settings["waveform_generator"]
    )
    plain = WaveformGenerator(
        domain=domain, approximant="IMRPhenomD", f_ref=20
    )
    theta = dict(config["source"], luminosity_distance=100.0, geocent_time=0.0)
    unlensed = plain.generate_hplus_hcross(theta)
    parameters = dict(
        theta, mu_rel=0.4, lensing_delta_t=0.008, Delta_phase=float(np.pi / 2)
    )
    original = deepcopy(parameters)
    actual = generator.generate_hplus_hcross(
        parameters, apply_postprocessing=False
    )
    frequencies = domain.sample_frequencies.astype(float)
    factor = np.conj(
        1
        + np.sqrt(0.4)
        * np.exp(
            1j
            * (
                2 * np.pi * frequencies * 0.008
                - np.sign(frequencies) * np.pi / 2
            )
        )
    )
    for name in actual:
        np.testing.assert_allclose(
            actual[name], unlensed[name] * factor, rtol=1e-12, atol=1e-30
        )
    assert parameters == original
    parameters["mu_rel"] = 0.0
    for name, value in generator.generate_hplus_hcross(parameters).items():
        np.testing.assert_allclose(
            value, unlensed[name], rtol=1e-12, atol=1e-30
        )
    # Generation must not leave an unpicklable lambda on the instance.
    restored = pickle.loads(pickle.dumps(generator))
    assert restored._model is not None


def test_dft_modes_are_lensed_once(config):
    """DFT phase calls retain lens parameters and apply one factor."""
    settings = dataset_settings(config)
    domain = build_domain(settings["domain"])
    generator = LensedWaveformGenerator(
        domain=domain, approximant="IMRPhenomXPHM", f_ref=20.0,
        spin_conversion_phase=0.0, use_dft_phase_decomposition=True,
        amplification_factor_function="two_images_BBH",
    )
    theta = dict(config["source"], luminosity_distance=1000.0,
                 geocent_time=0.0, mu_rel=0.4, lensing_delta_t=0.008,
                 Delta_phase=float(np.pi / 2))
    expected = generator.generate_hplus_hcross(theta)
    modes = generator.generate_hplus_hcross_m(theta)
    for key, value in expected.items():
        reconstructed = sum(mode[key] for mode in modes.values())
        np.testing.assert_allclose(reconstructed, value,
                                   rtol=1e-7, atol=1e-30)
