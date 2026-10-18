"""Verify a complete initialized lens generator in injection objects."""

import numpy as np
from dingo.gw.domains import build_domain

from dingo_lensing.injection import LensedInjection
from dingo_lensing.toy_two_image import dataset_settings, make_asds


def test_injection(config):
    settings = dataset_settings(config)
    domain = build_domain(settings["domain"])
    injection = LensedInjection(
        prior=None,
        wfg_kwargs=settings["waveform_generator"],
        wfg_domain=domain,
        data_domain=domain,
        ifo_list=config["detectors"],
        t_ref=config["ref_time"],
    )
    injection.asd = make_asds(domain, config["detectors"])
    theta = dict(
        config["source"],
        **config["extrinsic"],
        luminosity_distance=1000.0,
        geocent_time=0.0,
        mu_rel=0.4,
        lensing_delta_t=0.008,
    )
    observation = injection.injection(theta)
    assert set(observation["waveform"]) == {"H1", "L1"}
    assert all(
        v.shape == (4097,) and np.isfinite(v).all()
        for v in observation["waveform"].values()
    )
