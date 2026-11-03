import inspect

from dingo_lensing.waveform_generator import (
    LENS_SETTING_KEYS,
    LensedWaveformGenerator,
    split_waveform_settings,
)


def test_split_waveform_settings():
    settings = {
        "approximant": "IMRPhenomXPHM",
        "f_ref": 20.0,
        "fdsm_function": "one_image_BBH",
        "lens_model_defaults": {"mu_rel": 0.5},
    }
    base, lens = split_waveform_settings(settings)
    assert base == {"approximant": "IMRPhenomXPHM", "f_ref": 20.0}
    assert lens == {
        "fdsm_function": "one_image_BBH",
        "lens_model_defaults": {"mu_rel": 0.5},
    }
    assert "fdsm_function" in settings


def test_lens_setting_keys_match_generator_arguments():
    parameters = inspect.signature(LensedWaveformGenerator.__init__).parameters
    keyword_only = {
        name
        for name, parameter in parameters.items()
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY
    }
    assert keyword_only == LENS_SETTING_KEYS
