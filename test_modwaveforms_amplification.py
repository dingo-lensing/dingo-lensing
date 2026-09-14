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
from dingo_lensing.modwaveforms_amplification import (
    CuspCaustic,
    FoldCaustic,
    OneImageBBH,
    PointLens,
    TwoImagesBBH,
    get_model,
)
from dingo_lensing.waveform_generator import LensedWaveformGenerator


FREQUENCIES = np.array([0.0, 20.0, 64.0, 512.0, 1024.0], dtype=np.float64)


# --------------------------------------------------------------------------
# Per-model resolve()/compute() correctness. Each model is fully
# self-contained, so these tests exercise it directly, no shared registry
# or dispatcher to reason about.
# --------------------------------------------------------------------------


def test_one_image_bbh_matches_vendor_and_applies_local_default():
    model = OneImageBBH()

    resolved = model.resolve({}, {})
    assert resolved == {"Delta_phase": 0.5 * np.pi}
    np.testing.assert_array_equal(
        model.compute(FREQUENCIES, resolved),
        geomoptics.one_image_BBH(FREQUENCIES, 0.5 * np.pi),
    )

    resolved = model.resolve({"Delta_phase": 1.0}, {})
    assert resolved == {"Delta_phase": 1.0}


def test_two_images_bbh_matches_vendor_and_renames_at_the_call_site():
    model = TwoImagesBBH()
    parameters = {"lensing_delta_t": 0.037, "mu_rel": 0.42, "chirp_mass": 30.0}

    resolved = model.resolve(parameters, {})

    assert resolved == {"lensing_delta_t": 0.037, "mu_rel": 0.42, "Delta_phase": 0.5 * np.pi}
    assert parameters == {"chirp_mass": 30.0}  # lensing keys stripped, others untouched
    np.testing.assert_array_equal(
        model.compute(FREQUENCIES, resolved),
        geomoptics.two_images_BBH(FREQUENCIES, 0.42, 0.037, 0.5 * np.pi),
    )


def test_two_images_bbh_falls_back_to_lens_model_defaults():
    model = TwoImagesBBH()
    resolved = model.resolve({}, {"lensing_delta_t": 0.02, "mu_rel": 0.3})
    assert resolved["lensing_delta_t"] == 0.02
    assert resolved["mu_rel"] == 0.3


def test_two_images_bbh_prefers_sampled_over_lens_model_defaults():
    model = TwoImagesBBH()
    resolved = model.resolve(
        {"lensing_delta_t": 0.05}, {"lensing_delta_t": 0.02, "mu_rel": 0.3}
    )
    assert resolved["lensing_delta_t"] == 0.05
    assert resolved["mu_rel"] == 0.3


def test_fold_caustic_matches_vendor():
    model = FoldCaustic()
    resolved = model.resolve({"lensing_delta_t": 0.037}, {})
    np.testing.assert_array_equal(
        model.compute(FREQUENCIES, resolved),
        geomoptics.fold_caustic(FREQUENCIES, 0.037, 1.0),
    )


def test_cusp_caustic_matches_vendor_when_fully_sampled():
    model = CuspCaustic()
    resolved = model.resolve(
        {"Delta_t_10": 0.013, "Delta_t_20": 0.041, "mu_rel": 0.42}, {}
    )
    np.testing.assert_array_equal(
        model.compute(FREQUENCIES, resolved),
        geomoptics.cusp_caustic(FREQUENCIES, 0.013, 0.041, 0.42, 1.0),
    )


def test_cusp_caustic_falls_back_to_lensing_delta_t_for_image_delays():
    model = CuspCaustic()
    resolved = model.resolve({"lensing_delta_t": 0.037, "mu_rel": 0.42}, {})
    assert resolved["Delta_t_10"] == 0.037
    assert resolved["Delta_t_20"] == 0.037
    np.testing.assert_array_equal(
        model.compute(FREQUENCIES, resolved),
        geomoptics.cusp_caustic(FREQUENCIES, 0.037, 0.037, 0.42, 1.0),
    )


def test_cusp_caustic_real_config_shape_never_needs_lensing_delta_t():
    # Matches examples/dev_mode/waveform_dataset_settings_cusp_caustic.yaml:
    # Delta_t_10/Delta_t_20 are always sampled directly, lensing_delta_t is
    # never set at all.
    model = CuspCaustic()
    parameters = {"Delta_t_10": 0.01, "Delta_t_20": 0.03, "mu_rel": 0.5, "chirp_mass": 30.0}

    resolved = model.resolve(parameters, {})

    assert resolved["Delta_t_10"] == 0.01
    assert resolved["Delta_t_20"] == 0.03
    assert parameters == {"chirp_mass": 30.0}


def test_cusp_caustic_resolves_to_none_when_nothing_is_available():
    # Regression guard: must not crash when neither Delta_t_10/Delta_t_20
    # nor lensing_delta_t nor a lens_model_defaults entry provides a value.
    model = CuspCaustic()
    resolved = model.resolve({"mu_rel": 0.5}, {})
    assert resolved["Delta_t_10"] is None
    assert resolved["Delta_t_20"] is None


def test_pointlens_matches_pre_refactor_baseline():
    model = PointLens()
    resolved = model.resolve({"ML": 1700.0, "y": 0.15}, {})
    actual = model.compute(FREQUENCIES, resolved)

    assert actual.dtype == np.complex128
    assert hashlib.sha256(actual.tobytes()).hexdigest() == (
        "b2bd30a6a58e9db7de38a446d6e45887ecc24d2bd0216345f019ee20efc03a81"
    )


def test_pointlens_falls_back_to_lens_model_defaults():
    model = PointLens()
    resolved = model.resolve({}, {"ML": 1700.0, "y": 0.15})
    assert resolved == {"ML": 1700.0, "y": 0.15}


def test_pointlens_requires_ml_and_y():
    model = PointLens()
    with pytest.raises(ValueError, match="pointlens requires ML and y"):
        model.resolve({}, {})


def test_get_model_rejects_unknown_function():
    with pytest.raises(ValueError, match="Unsupported lensing amplification function"):
        get_model("other")


def test_get_model_returns_the_same_kind_of_model_each_time():
    assert isinstance(get_model("two_images_BBH"), TwoImagesBBH)
    assert isinstance(get_model("pointlens"), PointLens)


# --------------------------------------------------------------------------
# Loader
# --------------------------------------------------------------------------


def test_loader_rejects_unknown_lens_model_code():
    with pytest.raises(ValueError, match="Unsupported lens model code 'other'"):
        lens_code_loader.load_amplification_model("other", "two_images_BBH")


def test_loader_imports_and_caches(monkeypatch):
    lens_code_loader.load_amplification_model.cache_clear()
    expected_model = object()
    imported_modules = []

    def fake_import_module(module_name):
        imported_modules.append(module_name)
        return SimpleNamespace(get_model=lambda function: expected_model)

    monkeypatch.setitem(
        lens_code_loader._LENS_CODE_MODULES,
        "test_code",
        "test_package.amplification",
    )
    monkeypatch.setattr(lens_code_loader, "import_module", fake_import_module)

    try:
        first = lens_code_loader.load_amplification_model("test_code", "anything")
        second = lens_code_loader.load_amplification_model("test_code", "anything")
    finally:
        lens_code_loader.load_amplification_model.cache_clear()

    assert first is expected_model
    assert second is expected_model
    assert imported_modules == ["test_package.amplification"]


def test_loader_reports_import_and_interface_errors(monkeypatch):
    monkeypatch.setitem(
        lens_code_loader._LENS_CODE_MODULES,
        "missing_code",
        "missing_package.amplification",
    )

    def fail_import(module_name):
        raise ModuleNotFoundError(module_name)

    lens_code_loader.load_amplification_model.cache_clear()
    monkeypatch.setattr(lens_code_loader, "import_module", fail_import)
    with pytest.raises(ImportError, match="Install its required dependencies"):
        lens_code_loader.load_amplification_model("missing_code", "anything")

    lens_code_loader.load_amplification_model.cache_clear()
    monkeypatch.setattr(
        lens_code_loader,
        "import_module",
        lambda module_name: SimpleNamespace(get_model=None),
    )
    with pytest.raises(TypeError, match="must provide a callable get_model"):
        lens_code_loader.load_amplification_model("missing_code", "anything")
    lens_code_loader.load_amplification_model.cache_clear()


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


# --------------------------------------------------------------------------
# Generator integration
# --------------------------------------------------------------------------


def test_generator_requires_an_amplification_function(monkeypatch):
    monkeypatch.setattr(WaveformGenerator, "__init__", lambda self, *args, **kwargs: None)

    with pytest.raises(ValueError, match="Must specify amplification_factor_function"):
        LensedWaveformGenerator()


def test_generator_resolves_new_and_legacy_selectors(monkeypatch):
    monkeypatch.setattr(WaveformGenerator, "__init__", lambda self, *args, **kwargs: None)

    legacy = LensedWaveformGenerator(fdsm_function="fold_caustic")
    current = LensedWaveformGenerator(
        lens_model_code="modwaveforms",
        amplification_factor_function="cusp_caustic",
    )
    matching = LensedWaveformGenerator(
        fdsm_function="pointlens",
        amplification_factor_function="pointlens",
    )

    assert legacy.lens_model_code == "modwaveforms"
    assert isinstance(legacy._model, FoldCaustic)
    assert legacy.lens_model_defaults == {}
    assert legacy.amplification_factor_function == "fold_caustic"
    assert legacy.fdsm_function == "fold_caustic"
    assert isinstance(current._model, CuspCaustic)
    assert isinstance(matching._model, PointLens)

    with pytest.raises(ValueError, match="must match"):
        LensedWaveformGenerator(
            fdsm_function="fold_caustic",
            amplification_factor_function="cusp_caustic",
        )


def test_constructor_stores_lens_model_defaults(monkeypatch):
    monkeypatch.setattr(WaveformGenerator, "__init__", lambda self, *args, **kwargs: None)

    generator = LensedWaveformGenerator(
        amplification_factor_function="pointlens",
        lens_model_defaults={"ML": 1700.0, "y": 0.15},
    )

    assert generator.lens_model_defaults == {"ML": 1700.0, "y": 0.15}


def _make_bare_generator(model, lens_model_defaults=None):
    generator = object.__new__(LensedWaveformGenerator)
    generator._model = model
    generator.lens_model_defaults = lens_model_defaults or {}
    return generator


def test_resolve_lensing_parameters_delegates_to_the_model():
    generator = _make_bare_generator(PointLens())
    parameters = {"chirp_mass": 30.0, "ML": 1700.0, "y": 0.15}

    resolved = generator._resolve_lensing_parameters(parameters)

    assert resolved == {"ML": 1700.0, "y": 0.15}
    assert parameters == {"chirp_mass": 30.0}


def test_get_lensing_amplification_factor_delegates_to_the_model():
    received = {}

    class FakeModel:
        def compute(self, frequency_array, resolved):
            received["frequency_array"] = frequency_array
            received["resolved"] = resolved
            return "computed"

    generator = _make_bare_generator(FakeModel())
    result = generator._get_lensing_amplification_factor(FREQUENCIES, {"mu_rel": 0.5})

    assert result == "computed"
    assert received["frequency_array"] is FREQUENCIES
    assert received["resolved"] == {"mu_rel": 0.5}


def test_full_waveform_generation_only_applies_amplification(monkeypatch):
    generator = object.__new__(LensedWaveformGenerator)
    generator.domain = SimpleNamespace(sample_frequencies=FREQUENCIES)
    generator.dev_mode = False
    generator._current_plot_parameters = {"lensed": {"ML": 1700.0, "y": 0.15}}
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

    def fake_get_lensing_amplification_factor(frequency_array, resolved):
        received["resolved"] = resolved
        return factor

    monkeypatch.setattr(
        generator,
        "_get_lensing_amplification_factor",
        fake_get_lensing_amplification_factor,
    )

    lensed = generator.generate_lensed_FD_waveform((), lambda: None)

    np.testing.assert_array_equal(lensed["h_plus"], factor)
    np.testing.assert_array_equal(lensed["h_cross"], 2.0 * factor)
    assert received["resolved"] == {"ML": 1700.0, "y": 0.15}


def test_mode_generation_only_applies_amplification(monkeypatch):
    generator = _make_bare_generator(TwoImagesBBH())
    generator.domain = SimpleNamespace(sample_frequencies=FREQUENCIES)
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
    # Regression test for the original ML/y leak: generate_hplus_hcross_m
    # must strip ML/y from parameters before calling the base class, exactly
    # like generate_hplus_hcross already does. Exercised in practice by any
    # pointlens config that samples ML/y per-event (see
    # examples/dev_mode/waveform_dataset_settings_pointlens.yaml).
    generator = _make_bare_generator(PointLens())
    generator.domain = SimpleNamespace(sample_frequencies=FREQUENCIES)
    modes = {2: {"h_plus": np.ones(len(FREQUENCIES), dtype=np.complex128),
                 "h_cross": np.ones(len(FREQUENCIES), dtype=np.complex128)}}
    received = {}

    def fake_base_generate_hplus_hcross_m(self, parameters):
        received["parameters"] = dict(parameters)
        return modes

    monkeypatch.setattr(
        WaveformGenerator, "generate_hplus_hcross_m", fake_base_generate_hplus_hcross_m
    )

    def fake_get_lensing_amplification_factor(frequency_array, resolved):
        received["resolved"] = dict(resolved)
        return np.ones(len(FREQUENCIES), dtype=np.complex128)

    monkeypatch.setattr(
        generator,
        "_get_lensing_amplification_factor",
        fake_get_lensing_amplification_factor,
    )

    parameters = {"chirp_mass": 30.0, "ML": 1700.0, "y": 0.15}
    generator.generate_hplus_hcross_m(parameters)

    assert "ML" not in received["parameters"]
    assert "y" not in received["parameters"]
    assert received["parameters"] == {"chirp_mass": 30.0}
    assert received["resolved"]["ML"] == 1700.0
    assert received["resolved"]["y"] == 0.15


def test_dev_plot_output_dir_includes_lens_model_code():
    generator = object.__new__(LensedWaveformGenerator)
    generator.dev_plot_dir = Path("dev_plots")
    generator.lens_model_code = "modwaveforms"
    generator.amplification_factor_function = "two_images_BBH"
    generator.fdsm_function = "two_images_BBH"

    output_dir = generator._dev_plot_output_dir("waveform")

    assert output_dir == Path("dev_plots") / "modwaveforms" / "two_images_BBH" / "waveform"
