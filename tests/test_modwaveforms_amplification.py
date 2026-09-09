import hashlib
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from dingo.gw.waveform_generator import WaveformGenerator
from modwaveforms import geomoptics

import dingo_lensing.lens_code_loader as lens_code_loader
from dingo_lensing.modwaveforms_amplification import get_amplification_factor
from dingo_lensing.waveform_generator import LensedWaveformGenerator


FREQUENCIES = np.array([0.0, 20.0, 64.0, 512.0, 1024.0], dtype=np.float64)


def test_geomoptics_functions_are_delegated_without_numerical_change():
    cases = (
        (
            "one_image_BBH",
            {"Delta_phase": 0.5 * np.pi},
            None,
            None,
            geomoptics.one_image_BBH(FREQUENCIES, 0.5 * np.pi),
        ),
        (
            "two_images_BBH",
            {},
            0.037,
            0.42,
            geomoptics.two_images_BBH(FREQUENCIES, 0.42, 0.037, 0.5 * np.pi),
        ),
        (
            "fold_caustic",
            {"positive_phase": 1.0},
            0.037,
            None,
            geomoptics.fold_caustic(FREQUENCIES, 0.037, 1.0),
        ),
        (
            "cusp_caustic",
            {
                "Delta_t_10": 0.013,
                "Delta_t_20": 0.041,
                "positive_phase": 1.0,
            },
            None,
            0.42,
            geomoptics.cusp_caustic(
                FREQUENCIES, 0.013, 0.041, 0.42, 1.0
            ),
        ),
    )

    for function, parameters, lensing_delta_t, mu_rel, expected in cases:
        actual = get_amplification_factor(
            function,
            FREQUENCIES,
            parameters,
            lensing_delta_t=lensing_delta_t,
            mu_rel=mu_rel,
        )
        np.testing.assert_array_equal(actual, expected)


def test_pointlens_matches_pre_refactor_baseline():
    actual = get_amplification_factor(
        "pointlens",
        FREQUENCIES,
        {"ML": 1700.0, "y": 0.15},
    )

    assert actual.dtype == np.complex128
    assert hashlib.sha256(actual.tobytes()).hexdigest() == (
        "b2bd30a6a58e9db7de38a446d6e45887ecc24d2bd0216345f019ee20efc03a81"
    )


def test_pointlens_uses_waveform_generator_defaults():
    sampled = get_amplification_factor(
        "pointlens",
        FREQUENCIES,
        {"ML": 1700.0, "y": 0.15},
    )
    configured = get_amplification_factor(
        "pointlens",
        FREQUENCIES,
        {},
        ML=1700.0,
        y=0.15,
    )

    np.testing.assert_array_equal(configured, sampled)


def test_amplification_selection_errors_are_clear():
    with pytest.raises(ValueError, match="Unsupported lensing amplification function"):
        get_amplification_factor("other", FREQUENCIES, {})

    with pytest.raises(ValueError, match="pointlens requires ML and y"):
        get_amplification_factor("pointlens", FREQUENCIES, {})


def test_loader_rejects_unknown_lens_model_code():
    with pytest.raises(ValueError, match="Unsupported lens model code 'other'"):
        lens_code_loader.load_amplification_factor("other")


def test_loader_imports_and_caches_only_selected_backend(monkeypatch):
    lens_code_loader.load_amplification_factor.cache_clear()
    expected = lambda: None
    imported_modules = []

    def fake_import_module(module_name):
        imported_modules.append(module_name)
        return SimpleNamespace(get_amplification_factor=expected)

    monkeypatch.setitem(
        lens_code_loader._LENS_CODE_MODULES,
        "test_code",
        "test_package.amplification",
    )
    monkeypatch.setattr(lens_code_loader, "import_module", fake_import_module)

    try:
        first = lens_code_loader.load_amplification_factor("test_code")
        second = lens_code_loader.load_amplification_factor("test_code")
    finally:
        lens_code_loader.load_amplification_factor.cache_clear()

    assert first is expected
    assert second is expected
    assert imported_modules == ["test_package.amplification"]


def test_loader_reports_import_and_interface_errors(monkeypatch):
    monkeypatch.setitem(
        lens_code_loader._LENS_CODE_MODULES,
        "missing_code",
        "missing_package.amplification",
    )

    def fail_import(module_name):
        raise ModuleNotFoundError(module_name)

    lens_code_loader.load_amplification_factor.cache_clear()
    monkeypatch.setattr(lens_code_loader, "import_module", fail_import)
    with pytest.raises(ImportError, match="Install its required dependencies"):
        lens_code_loader.load_amplification_factor("missing_code")

    lens_code_loader.load_amplification_factor.cache_clear()
    monkeypatch.setattr(
        lens_code_loader,
        "import_module",
        lambda module_name: SimpleNamespace(get_amplification_factor=None),
    )
    with pytest.raises(TypeError, match="must provide a callable"):
        lens_code_loader.load_amplification_factor("missing_code")
    lens_code_loader.load_amplification_factor.cache_clear()


def test_importing_waveform_generator_does_not_import_modwaveforms():
    script = """
import sys
import dingo_lensing.waveform_generator

assert "modwaveforms" not in sys.modules
assert "dingo_lensing.modwaveforms_amplification" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_generator_resolves_new_and_legacy_selectors(monkeypatch):
    monkeypatch.setattr(WaveformGenerator, "__init__", lambda self, *args, **kwargs: None)

    default = LensedWaveformGenerator()
    legacy = LensedWaveformGenerator(fdsm_function="fold_caustic")
    current = LensedWaveformGenerator(
        lens_model_code="modwaveforms",
        amplification_factor_function="cusp_caustic",
    )
    matching = LensedWaveformGenerator(
        fdsm_function="pointlens",
        amplification_factor_function="pointlens",
    )

    assert default.lens_model_code == "modwaveforms"
    assert default.amplification_factor_function == "two_images_BBH"
    assert default.fdsm_function == "two_images_BBH"
    assert default._amplification_factor is get_amplification_factor
    assert legacy.amplification_factor_function == "fold_caustic"
    assert legacy.fdsm_function == "fold_caustic"
    assert current.amplification_factor_function == "cusp_caustic"
    assert matching.fdsm_function == "pointlens"

    legacy.fdsm_function = "cusp_caustic"
    assert legacy.amplification_factor_function == "cusp_caustic"
    current.amplification_factor_function = "pointlens"
    assert current.fdsm_function == "pointlens"

    with pytest.raises(ValueError, match="must match"):
        LensedWaveformGenerator(
            fdsm_function="fold_caustic",
            amplification_factor_function="cusp_caustic",
        )


def test_resolve_lensing_parameters_pops_all_four_keys_and_leaves_others():
    generator = object.__new__(LensedWaveformGenerator)
    generator.pointlens_ML = None
    generator.pointlens_y = None
    parameters = {
        "chirp_mass": 30.0,
        "lensing_delta_t": 0.037,
        "mu_rel": 0.42,
        "ML": 1700.0,
        "y": 0.15,
    }

    lensing_delta_t, mu_rel, ML, y = generator._resolve_lensing_parameters(parameters)

    assert (lensing_delta_t, mu_rel, ML, y) == (0.037, 0.42, 1700.0, 0.15)
    # The four lensing-specific keys are stripped; unrelated parameters are untouched.
    assert parameters == {"chirp_mass": 30.0}


def test_resolve_lensing_parameters_falls_back_to_generator_defaults():
    generator = object.__new__(LensedWaveformGenerator)
    generator.pointlens_ML = 1700.0
    generator.pointlens_y = 0.15
    parameters = {"chirp_mass": 30.0}

    lensing_delta_t, mu_rel, ML, y = generator._resolve_lensing_parameters(parameters)

    assert lensing_delta_t is None
    assert mu_rel is None
    assert ML == 1700.0
    assert y == 0.15


def test_resolve_lensing_parameters_prefers_sampled_over_generator_defaults():
    generator = object.__new__(LensedWaveformGenerator)
    generator.pointlens_ML = 1700.0
    generator.pointlens_y = 0.15
    parameters = {"ML": 2500.0, "y": 0.18}

    _, _, ML, y = generator._resolve_lensing_parameters(parameters)

    assert ML == 2500.0
    assert y == 0.18


def test_generator_delegates_amplification_selection():
    generator = object.__new__(LensedWaveformGenerator)
    generator.amplification_factor_function = "two_images_BBH"
    expected = np.arange(len(FREQUENCIES), dtype=np.complex128)
    received = {}

    def fake_get_amplification_factor(*args, **kwargs):
        received["args"] = args
        received["kwargs"] = kwargs
        return expected

    generator._amplification_factor = fake_get_amplification_factor
    actual = generator._get_lensing_amplification_factor(
        FREQUENCIES,
        {"Delta_phase": 0.5 * np.pi},
        lensing_delta_t=0.037,
        mu_rel=0.42,
        ML=1700.0,
        y=0.15,
    )

    assert actual is expected
    assert received["args"][0] == "two_images_BBH"
    assert received["args"][1] is FREQUENCIES
    assert received["kwargs"]["lensing_delta_t"] == 0.037
    assert received["kwargs"]["mu_rel"] == 0.42
    assert received["kwargs"]["ML"] == 1700.0
    assert received["kwargs"]["y"] == 0.15


def test_get_lensing_amplification_factor_does_not_read_pointlens_attrs():
    # Regression guard: ML/y must come from the explicit ML=/y= arguments,
    # never from self.pointlens_ML/self.pointlens_y directly (that was the
    # source of the dead-fallback / inconsistent-resolution bug).
    generator = object.__new__(LensedWaveformGenerator)
    generator.amplification_factor_function = "pointlens"
    generator.pointlens_ML = 9999.0
    generator.pointlens_y = 0.99
    received = {}

    def fake_get_amplification_factor(*args, **kwargs):
        received["kwargs"] = kwargs
        return np.ones(len(FREQUENCIES), dtype=np.complex128)

    generator._amplification_factor = fake_get_amplification_factor
    generator._get_lensing_amplification_factor(
        FREQUENCIES, {}, lensing_delta_t=None, mu_rel=None, ML=1700.0, y=0.15
    )

    assert received["kwargs"]["ML"] == 1700.0
    assert received["kwargs"]["y"] == 0.15


def test_full_waveform_generation_only_applies_amplification(monkeypatch):
    generator = object.__new__(LensedWaveformGenerator)
    generator.domain = SimpleNamespace(sample_frequencies=FREQUENCIES)
    generator.dev_mode = False
    generator._current_plot_parameters = {"lensed": {}}
    unlensed = {
        "h_plus": np.ones(len(FREQUENCIES), dtype=np.complex128),
        "h_cross": 2.0 * np.ones(len(FREQUENCIES), dtype=np.complex128),
    }
    factor = np.arange(1, len(FREQUENCIES) + 1, dtype=np.complex128)
    received = {}

    monkeypatch.setattr(
        WaveformGenerator,
        "generate_FD_waveform",
        lambda self, parameters_lal, target_function: unlensed,
    )

    def fake_get_lensing_amplification_factor(*args, **kwargs):
        received["kwargs"] = kwargs
        return factor

    monkeypatch.setattr(
        generator,
        "_get_lensing_amplification_factor",
        fake_get_lensing_amplification_factor,
    )

    lensed = generator.generate_lensed_FD_waveform(
        (), lambda: None, 0.037, 0.42, ML=1700.0, y=0.15
    )

    np.testing.assert_array_equal(lensed["h_plus"], factor)
    np.testing.assert_array_equal(lensed["h_cross"], 2.0 * factor)
    assert received["kwargs"]["ML"] == 1700.0
    assert received["kwargs"]["y"] == 0.15


def test_mode_generation_only_applies_amplification(monkeypatch):
    generator = object.__new__(LensedWaveformGenerator)
    generator.domain = SimpleNamespace(sample_frequencies=FREQUENCIES)
    generator.pointlens_ML = None
    generator.pointlens_y = None
    modes = {
        2: {
            "h_plus": np.ones(len(FREQUENCIES), dtype=np.complex128),
            "h_cross": 2.0 * np.ones(len(FREQUENCIES), dtype=np.complex128),
        }
    }
    factor = np.arange(1, len(FREQUENCIES) + 1, dtype=np.complex128)

    monkeypatch.setattr(
        WaveformGenerator,
        "generate_hplus_hcross_m",
        lambda self, parameters: modes,
    )
    monkeypatch.setattr(
        generator,
        "_get_lensing_amplification_factor",
        lambda *args, **kwargs: factor,
    )
    parameters = {"phase": 0.0, "lensing_delta_t": 0.037, "mu_rel": 0.42}

    lensed = generator.generate_hplus_hcross_m(parameters)

    np.testing.assert_array_equal(lensed[2]["h_plus"], factor)
    np.testing.assert_array_equal(lensed[2]["h_cross"], 2.0 * factor)


def test_mode_generation_strips_pointlens_parameters_before_delegating(monkeypatch):
    # Regression test for the ML/y leak: generate_hplus_hcross_m must strip
    # ML/y from parameters before calling the base class, exactly like
    # generate_hplus_hcross already does, so the base waveform generator
    # never sees these lensing-only keys as if they were physical BBH
    # parameters. This is exercised in practice by any pointlens config that
    # samples ML/y per-event (see examples/dev_mode/waveform_dataset_settings_pointlens.yaml).
    generator = object.__new__(LensedWaveformGenerator)
    generator.domain = SimpleNamespace(sample_frequencies=FREQUENCIES)
    generator.pointlens_ML = None
    generator.pointlens_y = None
    modes = {2: {"h_plus": np.ones(len(FREQUENCIES), dtype=np.complex128),
                 "h_cross": np.ones(len(FREQUENCIES), dtype=np.complex128)}}
    received = {}

    def fake_base_generate_hplus_hcross_m(self, parameters):
        received["parameters"] = dict(parameters)
        return modes

    monkeypatch.setattr(
        WaveformGenerator, "generate_hplus_hcross_m", fake_base_generate_hplus_hcross_m
    )
    monkeypatch.setattr(
        generator,
        "_get_lensing_amplification_factor",
        lambda *args, **kwargs: np.ones(len(FREQUENCIES), dtype=np.complex128),
    )

    parameters = {
        "chirp_mass": 30.0,
        "lensing_delta_t": 0.037,
        "mu_rel": 0.42,
        "ML": 1700.0,
        "y": 0.15,
    }
    generator.generate_hplus_hcross_m(parameters)

    assert "ML" not in received["parameters"]
    assert "y" not in received["parameters"]
    assert received["parameters"] == {"chirp_mass": 30.0}


def test_dev_plot_output_dir_includes_lens_model_code():
    generator = object.__new__(LensedWaveformGenerator)
    generator.dev_plot_dir = Path("dev_plots")
    generator.lens_model_code = "modwaveforms"
    generator.amplification_factor_function = "two_images_BBH"

    output_dir = generator._dev_plot_output_dir("waveform")

    assert output_dir == Path("dev_plots") / "modwaveforms" / "two_images_BBH" / "waveform"
