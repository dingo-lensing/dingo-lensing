import numpy as np
from dingo.gw.domains.build_domain import build_domain
from dingo.gw.injection import Injection

from dingo_lensing.injection import LensedInjection
from dingo_lensing.waveform_generator import LensedWaveformGenerator

DOMAIN = {
    "type": "FrequencyDomain",
    "f_min": 20.0,
    "f_max": 512.0,
    "delta_f": 0.125,
}
WFG_KWARGS = {
    "approximant": "IMRPhenomXPHM",
    "f_ref": 20.0,
    "spin_conversion_phase": 0.0,
}
LENS_KWARGS = {"fdsm_function": "one_image_BBH"}
THETA = {
    "chirp_mass": 30.0,
    "mass_ratio": 0.6,
    "a_1": 0.4,
    "a_2": 0.3,
    "tilt_1": 0.8,
    "tilt_2": 1.9,
    "phi_12": 0.5,
    "phi_jl": 2.1,
    "theta_jn": 1.1,
    "phase": 0.7,
    "luminosity_distance": 800.0,
    "ra": 1.2,
    "dec": -0.4,
    "psi": 0.9,
    "geocent_time": 0.0,
}


def signal_kwargs(wfg_kwargs):
    domain = build_domain(DOMAIN)
    return {
        "wfg_kwargs": wfg_kwargs,
        "wfg_domain": domain,
        "data_domain": domain,
        "ifo_list": ["H1", "L1"],
        "t_ref": 1126259462.4,
    }


def test_lensed_injection_has_lensed_generator():
    wfg_kwargs = {**WFG_KWARGS, **LENS_KWARGS}
    injection = LensedInjection(prior=None, **signal_kwargs(wfg_kwargs))
    generator = injection.waveform_generator
    assert isinstance(generator, LensedWaveformGenerator)
    assert generator.fdsm_function == "one_image_BBH"
    assert wfg_kwargs == {**WFG_KWARGS, **LENS_KWARGS}


def test_lensed_injection_signal_is_amplified():
    delta_phase = np.pi / 2
    lensed = LensedInjection(
        prior=None,
        **signal_kwargs({**WFG_KWARGS, **LENS_KWARGS})
    )
    unlensed = Injection(prior=None, **signal_kwargs(dict(WFG_KWARGS)))
    theta = {**THETA, "Delta_phase": delta_phase}
    h_lensed = lensed.signal(theta)["waveform"]
    h_unlensed = unlensed.signal(dict(THETA))["waveform"]
    generator = lensed.waveform_generator
    amplification = generator._get_lensing_amplification_factor(
        generator.domain.sample_frequencies,
        {"Delta_phase": delta_phase},
    )
    assert not np.allclose(amplification, 1.0)
    for ifo in ["H1", "L1"]:
        assert np.any(h_unlensed[ifo] != 0)
        np.testing.assert_allclose(
            h_lensed[ifo],
            amplification * h_unlensed[ifo],
            rtol=1e-10,
            atol=0,
        )
