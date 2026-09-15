import hashlib
import logging
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from dingo.gw.waveform_generator import WaveformGenerator
from modwaveforms import geomoptics

import dingo_lensing.lens_code_loader as lens_code_loader
import dingo_lensing.modwaveforms_amplification as modwaveforms_amplification
from dingo_lensing.modwaveforms_amplification import (
    AmplificationModel,
    CuspCaustic,
    FoldCaustic,
    OneImageBBH,
    PointLens,
    SUPPORTED_AMPLIFICATION_FUNCTIONS,
    TwoImagesBBH,
    get_model,
)
from dingo_lensing.waveform_generator import LensedWaveformGenerator


FREQUENCIES = np.array([0.0, 20.0, 64.0, 512.0, 1024.0], dtype=np.float64)


# --------------------------------------------------------------------------
# Base class contract
# --------------------------------------------------------------------------


def test_amplification_model_base_class_is_abstract():
    model = AmplificationModel()
    with pytest.raises(NotImplementedError):
        model.resolve({}, {})
    with pytest.raises(NotImplementedError):
        model.compute(FREQUENCIES, {})


def test_every_registered_model_declares_parameter_names():
    # Enforced structurally by lens_code_loader for anything loaded through
    # it (see the loader tests below); this just confirms the five real
    # models actually hold up their end of that contract.
    for model_class in modwaveforms_amplification._AMPLIFICATION_MODEL_CLASSES.values():
        assert isinstance(model_class().PARAMETER_NAMES, dict)


# --------------------------------------------------------------------------
# Fallback visibility: resolve() never silently makes up a value without a
# trace. Every place a model reaches for lens_model_defaults or a built-in
# default logs it (at DEBUG, so it's silent unless someone turns it on),
# which is what would surface a parameter name that doesn't actually match
# what a sample calls it -- the model looks for the name it was told to
# look for, doesn't find it, and this is where that becomes visible.
# --------------------------------------------------------------------------


def test_resolve_with_default_logs_when_falling_back(caplog):
    with caplog.at_level(logging.DEBUG, logger=modwaveforms_amplification.__name__):
        value = modwaveforms_amplification._resolve_with_default(
            "mu_rel", {}, {"mu_rel": 0.5}
        )

    assert value == 0.5
    assert any("mu_rel" in record.message for record in caplog.records)


def test_resolve_with_default_does_not_log_when_value_is_present(caplog):
    with caplog.at_level(logging.DEBUG, logger=modwaveforms_amplification.__name__):
        value = modwaveforms_amplification._resolve_with_default(
            "mu_rel", {"mu_rel": 0.9}, {"mu_rel": 0.5}
        )

    assert value == 0.9
    assert caplog.records == []


def test_pop_with_builtin_default_logs_when_falling_back(caplog):
    with caplog.at_level(logging.DEBUG, logger=modwaveforms_amplification.__name__):
        value = modwaveforms_amplification._pop_with_builtin_default(
            "Delta_phase", {}, 0.5 * np.pi
        )

    assert value == 0.5 * np.pi
    assert any("Delta_phase" in record.message for record in caplog.records)


def test_pop_with_builtin_default_does_not_log_when_value_is_present(caplog):
    with caplog.at_level(logging.DEBUG, logger=modwaveforms_amplification.__name__):
        value = modwaveforms_amplification._pop_with_builtin_default(
            "Delta_phase", {"Delta_phase": 1.0}, 0.5 * np.pi
        )

    assert value == 1.0
    assert caplog.records == []


def test_cusp_caustic_logs_when_borrowing_lensing_delta_t(caplog):
    # The bespoke Delta_t_10/Delta_t_20 fallback isn't routed through
    # _resolve_with_default, so it needs its own coverage here.
    model = CuspCaustic()
    with caplog.at_level(logging.DEBUG, logger=modwaveforms_amplification.__name__):
        model.resolve({"lensing_delta_t": 0.037, "mu_rel": 0.42}, {})

    messages = [record.message for record in caplog.records]
    assert any("Delta_t_10" in message for message in messages)
    assert any("Delta_t_20" in message for message in messages)


# --------------------------------------------------------------------------
# PARAMETER_NAMES translation layer: proves the declared mapping actually
# drives which key resolve() looks up in a sample, rather than being
# documentation sitting next to a separately hardcoded string literal.
# --------------------------------------------------------------------------


def test_parameter_names_mapping_actually_drives_the_lookup_key(monkeypatch):
    model = TwoImagesBBH()
    # Point this model's internal "mu_rel" at a differently-named standard
    # parameter, as if the team had agreed on a different sample-facing
    # name for the same quantity.
    monkeypatch.setitem(model.PARAMETER_NAMES, "mu_rel", "relative_magnification")

    resolved = model.resolve(
        {"lensing_delta_t": 0.02, "relative_magnification": 0.77}, {}
    )

    assert resolved["mu_rel"] == 0.77


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


def test_two_images_bbh_mixed_fallback_is_per_parameter_not_all_or_nothing():
    # Mirror of the test above: here mu_rel is the sampled one and
    # lensing_delta_t is the one falling back, proving the two keys are
    # resolved independently rather than "any key missing -> use defaults
    # for everything".
    model = TwoImagesBBH()
    resolved = model.resolve(
        {"mu_rel": 0.9}, {"lensing_delta_t": 0.02, "mu_rel": 0.3}
    )
    assert resolved["mu_rel"] == 0.9
    assert resolved["lensing_delta_t"] == 0.02


def test_fold_caustic_matches_vendor():
    model = FoldCaustic()
    resolved = model.resolve({"lensing_delta_t": 0.037}, {})
    np.testing.assert_array_equal(
        model.compute(FREQUENCIES, resolved),
        geomoptics.fold_caustic(FREQUENCIES, 0.037, 1.0),
    )


def test_fold_caustic_falls_back_to_lens_model_defaults():
    model = FoldCaustic()
    resolved = model.resolve({}, {"lensing_delta_t": 0.02})
    assert resolved["lensing_delta_t"] == 0.02
    assert resolved["positive_phase"] == 1.0


def test_fold_caustic_positive_phase_can_be_overridden():
    model = FoldCaustic()
    resolved = model.resolve({"lensing_delta_t": 0.01, "positive_phase": -1.0}, {})
    assert resolved["positive_phase"] == -1.0
    np.testing.assert_array_equal(
        model.compute(FREQUENCIES, resolved),
        geomoptics.fold_caustic(FREQUENCIES, 0.01, -1.0),
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


def test_cusp_caustic_partial_image_delay_fallback_is_independent_per_key():
    # Only Delta_t_10 is sampled; Delta_t_20 must fall back on its own,
    # rather than both falling back just because one of them was missing.
    model = CuspCaustic()
    resolved = model.resolve(
        {"Delta_t_10": 0.005, "lensing_delta_t": 0.02, "mu_rel": 0.4}, {}
    )
    assert resolved["Delta_t_10"] == 0.005
    assert resolved["Delta_t_20"] == 0.02


def test_cusp_caustic_mu_rel_falls_back_to_lens_model_defaults():
    model = CuspCaustic()
    resolved = model.resolve(
        {"Delta_t_10": 0.01, "Delta_t_20": 0.02}, {"mu_rel": 0.6}
    )
    assert resolved["mu_rel"] == 0.6


def test_cusp_caustic_positive_phase_can_be_overridden():
    model = CuspCaustic()
    resolved = model.resolve(
        {"Delta_t_10": 0.01, "Delta_t_20": 0.02, "mu_rel": 0.4, "positive_phase": -1.0},
        {},
    )
    assert resolved["positive_phase"] == -1.0


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


def test_pointlens_partial_fallback_ml_sampled_y_from_default():
    model = PointLens()
    resolved = model.resolve({"ML": 2000.0}, {"y": 0.1})
    assert resolved == {"ML": 2000.0, "y": 0.1}


def test_pointlens_partial_fallback_y_sampled_ml_from_default():
    model = PointLens()
    resolved = model.resolve({"y": 0.2}, {"ML": 1500.0})
    assert resolved == {"ML": 1500.0, "y": 0.2}


def test_pointlens_requires_ml_and_y():
    model = PointLens()
    with pytest.raises(ValueError, match="pointlens requires ML and y"):
        model.resolve({}, {})


def test_pointlens_requires_ml_and_y_even_when_only_one_is_available():
    model = PointLens()
    with pytest.raises(ValueError, match="pointlens requires ML and y"):
        model.resolve({"ML": 1700.0}, {})
    with pytest.raises(ValueError, match="pointlens requires ML and y"):
        model.resolve({"y": 0.15}, {})


# --------------------------------------------------------------------------
# get_model / registration
# --------------------------------------------------------------------------


def test_supported_amplification_functions_lists_all_five_real_models():
    assert set(SUPPORTED_AMPLIFICATION_FUNCTIONS) == {
        "one_image_BBH",
        "two_images_BBH",
        "fold_caustic",
        "cusp_caustic",
        "pointlens",
    }


def test_get_model_rejects_unknown_function():
    with pytest.raises(ValueError, match="Unsupported lensing amplification function"):
        get_model("other")


def test_get_model_error_message_lists_every_supported_function():
    with pytest.raises(ValueError) as exc_info:
        get_model("other")
    message = str(exc_info.value)
    for name in SUPPORTED_AMPLIFICATION_FUNCTIONS:
        assert name in message


def test_get_model_returns_the_same_kind_of_model_each_time():
    assert isinstance(get_model("two_images_BBH"), TwoImagesBBH)
    assert isinstance(get_model("pointlens"), PointLens)


def test_get_model_rejects_unexpected_settings_for_models_that_take_none():
    # None of the five real models take constructor arguments; passing a
    # settings key they don't recognise should fail loudly (a plain
    # TypeError from the constructor call), not be silently swallowed.
    with pytest.raises(TypeError):
        get_model("two_images_BBH", bogus_setting=1)


def test_get_model_forwards_construction_time_settings_to_the_model_class():
    # None of the five real models here take constructor arguments, but
    # get_model must still forward whatever it's given straight through to
    # the model class -- e.g. a future lookup-table-backed model taking a
    # file path to load once, rather than on every sample.
    captured = {}

    class LookupTableModel(modwaveforms_amplification.AmplificationModel):
        PARAMETER_NAMES = {}

        def __init__(self, lookup_table_path=None):
            captured["lookup_table_path"] = lookup_table_path

        def resolve(self, parameters, lens_model_defaults):
            return {}

        def compute(self, frequency_array, resolved):
            return frequency_array

    original = dict(modwaveforms_amplification._AMPLIFICATION_MODEL_CLASSES)
    modwaveforms_amplification._AMPLIFICATION_MODEL_CLASSES["lookup_table_model"] = (
        LookupTableModel
    )
    try:
        model = get_model("lookup_table_model", lookup_table_path="/data/table.h5")
    finally:
        modwaveforms_amplification._AMPLIFICATION_MODEL_CLASSES.clear()
        modwaveforms_amplification._AMPLIFICATION_MODEL_CLASSES.update(original)

    assert isinstance(model, LookupTableModel)
    assert captured["lookup_table_path"] == "/data/table.h5"


# --------------------------------------------------------------------------
# Loader
# --------------------------------------------------------------------------


def test_loader_rejects_unknown_lens_model_code():
    with pytest.raises(ValueError, match="Unsupported lens model code 'other'"):
        lens_code_loader.load_amplification_model("other", "two_images_BBH")


def test_loader_imports_the_module_only_once(monkeypatch):
    lens_code_loader._import_lens_code_module.cache_clear()
    expected_model = SimpleNamespace(PARAMETER_NAMES={})
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
        lens_code_loader._import_lens_code_module.cache_clear()

    assert first is expected_model
    assert second is expected_model
    # the module is only imported once, even though load_amplification_model
    # itself isn't cached (a model may need fresh construction-time settings
    # on each call)
    assert imported_modules == ["test_package.amplification"]


def test_loader_forwards_lens_model_settings_to_the_model_constructor(monkeypatch):
    lens_code_loader._import_lens_code_module.cache_clear()
    received = {}

    class FakeModel:
        PARAMETER_NAMES = {}

        def __init__(self, **settings):
            received["settings"] = settings

    monkeypatch.setitem(
        lens_code_loader._LENS_CODE_MODULES,
        "test_code",
        "test_package.amplification",
    )
    monkeypatch.setattr(
        lens_code_loader,
        "import_module",
        lambda module_name: SimpleNamespace(get_model=lambda function, **s: FakeModel(**s)),
    )

    try:
        lens_code_loader.load_amplification_model(
            "test_code", "anything", lens_model_settings={"lookup_table_path": "/tmp/table.h5"}
        )
    finally:
        lens_code_loader._import_lens_code_module.cache_clear()

    assert received["settings"] == {"lookup_table_path": "/tmp/table.h5"}


def test_loader_two_generators_do_not_share_a_model_instance(monkeypatch):
    # Regression guard for load_amplification_model deliberately not being
    # cached: two generators using the same function with different
    # construction-time settings (e.g. different lookup table files) must
    # not end up sharing one model instance.
    lens_code_loader._import_lens_code_module.cache_clear()

    class FakeModel:
        PARAMETER_NAMES = {}

        def __init__(self, **settings):
            self.settings = settings

    monkeypatch.setitem(
        lens_code_loader._LENS_CODE_MODULES,
        "test_code",
        "test_package.amplification",
    )
    monkeypatch.setattr(
        lens_code_loader,
        "import_module",
        lambda module_name: SimpleNamespace(get_model=lambda function, **s: FakeModel(**s)),
    )

    try:
        first = lens_code_loader.load_amplification_model(
            "test_code", "anything", lens_model_settings={"path": "a.h5"}
        )
        second = lens_code_loader.load_amplification_model(
            "test_code", "anything", lens_model_settings={"path": "b.h5"}
        )
    finally:
        lens_code_loader._import_lens_code_module.cache_clear()

    assert first is not second
    assert first.settings == {"path": "a.h5"}
    assert second.settings == {"path": "b.h5"}


def test_loader_reports_import_and_interface_errors(monkeypatch):
    monkeypatch.setitem(
        lens_code_loader._LENS_CODE_MODULES,
        "missing_code",
        "missing_package.amplification",
    )

    def fail_import(module_name):
        raise ModuleNotFoundError(module_name)

    lens_code_loader._import_lens_code_module.cache_clear()
    monkeypatch.setattr(lens_code_loader, "import_module", fail_import)
    with pytest.raises(ImportError, match="Install its required dependencies"):
        lens_code_loader.load_amplification_model("missing_code", "anything")

    lens_code_loader._import_lens_code_module.cache_clear()
    monkeypatch.setattr(
        lens_code_loader,
        "import_module",
        lambda module_name: SimpleNamespace(get_model=None),
    )
    with pytest.raises(TypeError, match="must provide a callable get_model"):
        lens_code_loader.load_amplification_model("missing_code", "anything")
    lens_code_loader._import_lens_code_module.cache_clear()


def test_loader_rejects_a_model_missing_parameter_names(monkeypatch):
    # Enforcement point for the PARAMETER_NAMES contract: a model with no
    # declared mapping fails at load time, not with a confusing failure
    # somewhere downstream once resolve() is actually called.
    lens_code_loader._import_lens_code_module.cache_clear()

    class ModelWithoutParameterNames:
        pass

    monkeypatch.setitem(
        lens_code_loader._LENS_CODE_MODULES,
        "test_code",
        "test_package.amplification",
    )
    monkeypatch.setattr(
        lens_code_loader,
        "import_module",
        lambda module_name: SimpleNamespace(
            get_model=lambda function: ModelWithoutParameterNames()
        ),
    )

    try:
        with pytest.raises(TypeError, match="must declare a PARAMETER_NAMES"):
            lens_code_loader.load_amplification_model("test_code", "anything")
    finally:
        lens_code_loader._import_lens_code_module.cache_clear()


def test_loader_accepts_a_model_with_an_explicitly_empty_parameter_names(monkeypatch):
    # An explicit empty dict means "this model reads nothing from a
    # sample", a deliberate declaration, not a missing one, so it must be
    # accepted rather than rejected alongside the case above.
    lens_code_loader._import_lens_code_module.cache_clear()

    class ModelWithNoSampleParameters:
        PARAMETER_NAMES = {}

    monkeypatch.setitem(
        lens_code_loader._LENS_CODE_MODULES,
        "test_code",
        "test_package.amplification",
    )
    monkeypatch.setattr(
        lens_code_loader,
        "import_module",
        lambda module_name: SimpleNamespace(
            get_model=lambda function: ModelWithNoSampleParameters()
        ),
    )

    try:
        model = lens_code_loader.load_amplification_model("test_code", "anything")
    finally:
        lens_code_loader._import_lens_code_module.cache_clear()

    assert isinstance(model, ModelWithNoSampleParameters)


def test_loader_real_modwaveforms_integration_returns_correct_model():
    # Unlike the tests above (which fake out import_module entirely), this
    # exercises the real registered "modwaveforms" entry end to end: the
    # actual module gets imported and its actual get_model() is called.
    lens_code_loader._import_lens_code_module.cache_clear()
    try:
        model = lens_code_loader.load_amplification_model("modwaveforms", "pointlens")
    finally:
        lens_code_loader._import_lens_code_module.cache_clear()
    assert isinstance(model, PointLens)


def test_loader_real_modwaveforms_forwards_settings_end_to_end():
    # Same real (non-mocked) path as above, but proving lens_model_settings
    # reaches a model's constructor through the *real* module, not a fake
    # one -- this is the exact mechanism a new lens code (e.g. Gravelamps'
    # lookup-table-backed models, see REFACTORING_GUIDE.md) would rely on.
    captured = {}

    class LookupTableModel(modwaveforms_amplification.AmplificationModel):
        PARAMETER_NAMES = {}  # reads nothing from a sample; lookup_table_path
        # is a construction-time setting, not a per-sample value.

        def __init__(self, lookup_table_path=None):
            captured["lookup_table_path"] = lookup_table_path

        def resolve(self, parameters, lens_model_defaults):
            return {}

        def compute(self, frequency_array, resolved):
            return frequency_array

    original = dict(modwaveforms_amplification._AMPLIFICATION_MODEL_CLASSES)
    modwaveforms_amplification._AMPLIFICATION_MODEL_CLASSES["lookup_table_model"] = (
        LookupTableModel
    )
    lens_code_loader._import_lens_code_module.cache_clear()
    try:
        model = lens_code_loader.load_amplification_model(
            "modwaveforms",
            "lookup_table_model",
            lens_model_settings={"lookup_table_path": "/data/table.h5"},
        )
    finally:
        modwaveforms_amplification._AMPLIFICATION_MODEL_CLASSES.clear()
        modwaveforms_amplification._AMPLIFICATION_MODEL_CLASSES.update(original)
        lens_code_loader._import_lens_code_module.cache_clear()

    assert isinstance(model, LookupTableModel)
    assert captured["lookup_table_path"] == "/data/table.h5"


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


def test_fdsm_function_property_setter_updates_amplification_factor_function():
    generator = object.__new__(LensedWaveformGenerator)
    generator.amplification_factor_function = "pointlens"

    generator.fdsm_function = "cusp_caustic"

    assert generator.amplification_factor_function == "cusp_caustic"
    assert generator.fdsm_function == "cusp_caustic"


def test_constructor_stores_lens_model_defaults(monkeypatch):
    monkeypatch.setattr(WaveformGenerator, "__init__", lambda self, *args, **kwargs: None)

    generator = LensedWaveformGenerator(
        amplification_factor_function="pointlens",
        lens_model_defaults={"ML": 1700.0, "y": 0.15},
    )

    assert generator.lens_model_defaults == {"ML": 1700.0, "y": 0.15}


def test_constructor_forwards_lens_model_settings_to_the_loader(monkeypatch):
    monkeypatch.setattr(WaveformGenerator, "__init__", lambda self, *args, **kwargs: None)
    received = {}

    def fake_load_amplification_model(lens_model_code, amplification_factor_function, lens_model_settings):
        received["lens_model_settings"] = lens_model_settings
        return PointLens()

    monkeypatch.setattr(
        "dingo_lensing.waveform_generator.load_amplification_model",
        fake_load_amplification_model,
    )

    LensedWaveformGenerator(
        amplification_factor_function="pointlens",
        lens_model_settings={"lookup_table_path": "/data/table.h5"},
    )

    assert received["lens_model_settings"] == {"lookup_table_path": "/data/table.h5"}


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


def test_generate_hplus_hcross_manages_sample_index_and_plot_state(monkeypatch):
    # Exercises generate_hplus_hcross itself (not generate_lensed_FD_waveform
    # or generate_hplus_hcross_m): sample_index is popped out of parameters
    # before it reaches the base class, _current_sample_index and
    # _current_plot_parameters are populated for the duration of the call
    # (for dev-mode plotting), and both are reset to None afterwards.
    generator = _make_bare_generator(TwoImagesBBH())
    generator.domain = SimpleNamespace(sample_frequencies=FREQUENCIES)
    captured = {}

    def fake_super_generate_hplus_hcross(self, parameters, catch_waveform_errors=True):
        captured["sample_index"] = self._current_sample_index
        captured["plot_parameters"] = {
            key: dict(value) for key, value in self._current_plot_parameters.items()
        }
        captured["parameters_passed"] = dict(parameters)
        return {
            "h_plus": np.zeros(len(FREQUENCIES)),
            "h_cross": np.zeros(len(FREQUENCIES)),
        }

    monkeypatch.setattr(
        WaveformGenerator, "generate_hplus_hcross", fake_super_generate_hplus_hcross
    )

    parameters = {
        "sample_index": 7,
        "chirp_mass": 30.0,
        "lensing_delta_t": 0.037,
        "mu_rel": 0.42,
    }

    generator.generate_hplus_hcross(parameters)

    assert captured["sample_index"] == 7
    assert captured["parameters_passed"] == {"chirp_mass": 30.0}
    assert captured["plot_parameters"]["nonlensed"] == {"chirp_mass": 30.0}
    assert captured["plot_parameters"]["lensed"] == {
        "chirp_mass": 30.0,
        "lensing_delta_t": 0.037,
        "mu_rel": 0.42,
        "Delta_phase": 0.5 * np.pi,
    }
    # State is scoped to the call: gone once generate_hplus_hcross returns.
    assert generator._current_sample_index is None
    assert generator._current_plot_parameters is None


def test_generate_hplus_hcross_resets_state_even_if_generation_fails(monkeypatch):
    generator = _make_bare_generator(PointLens())
    generator.domain = SimpleNamespace(sample_frequencies=FREQUENCIES)

    def failing_super_generate_hplus_hcross(self, parameters, catch_waveform_errors=True):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        WaveformGenerator, "generate_hplus_hcross", failing_super_generate_hplus_hcross
    )

    with pytest.raises(RuntimeError, match="boom"):
        generator.generate_hplus_hcross({"ML": 1700.0, "y": 0.15})

    assert generator._current_sample_index is None
    assert generator._current_plot_parameters is None


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


def test_save_dev_plot_skips_when_sample_index_is_none():
    # Guard clause: with no active sample (e.g. called outside a
    # generate_hplus_hcross scope), _save_dev_plot must return immediately
    # rather than touching any dev-plot state, which isn't set up here.
    generator = object.__new__(LensedWaveformGenerator)
    generator._current_sample_index = None

    generator._save_dev_plot({}, {}, np.array([1.0]))  # must not raise


def test_generate_lensed_fd_waveform_triggers_dev_plot_when_dev_mode_enabled(monkeypatch):
    generator = _make_bare_generator(PointLens())
    generator.domain = SimpleNamespace(
        sample_frequencies=FREQUENCIES, f_min=20.0, f_max=1024.0
    )
    generator.dev_mode = True
    generator.dev_plot_dir = Path("dev_plots")
    generator.lens_model_code = "modwaveforms"
    generator.amplification_factor_function = "pointlens"
    generator.fdsm_function = "pointlens"
    generator._current_sample_index = 3
    generator._current_plot_parameters = {
        "nonlensed": {"chirp_mass": 30.0},
        "lensed": {"chirp_mass": 30.0, "ML": 1700.0, "y": 0.15},
    }

    unlensed = {"h_plus": np.ones(len(FREQUENCIES), dtype=np.complex128)}
    monkeypatch.setattr(
        WaveformGenerator, "generate_FD_waveform", lambda self, p, t: unlensed
    )
    monkeypatch.setattr(
        generator,
        "_get_lensing_amplification_factor",
        lambda f, r: np.full(len(FREQUENCIES), 2.0),
    )

    calls = {}
    monkeypatch.setattr(
        "dingo_lensing.waveform_generator.plot_waveform_overlay",
        lambda **kwargs: calls.setdefault("waveform", kwargs),
    )
    monkeypatch.setattr(
        "dingo_lensing.waveform_generator.plot_amplification_factor",
        lambda **kwargs: calls.setdefault("amplification_factor", kwargs),
    )

    generator.generate_lensed_FD_waveform((), lambda: None)

    assert calls["waveform"]["sample_index"] == 3
    assert calls["waveform"]["output_dir"] == (
        Path("dev_plots") / "modwaveforms" / "pointlens" / "waveform"
    )
    assert calls["amplification_factor"]["output_dir"] == (
        Path("dev_plots") / "modwaveforms" / "pointlens" / "amplification_factor"
    )


def test_generate_lensed_fd_waveform_skips_dev_plot_when_disabled(monkeypatch):
    generator = _make_bare_generator(PointLens())
    generator.domain = SimpleNamespace(sample_frequencies=FREQUENCIES)
    generator.dev_mode = False
    generator._current_plot_parameters = {"lensed": {"ML": 1700.0, "y": 0.15}}

    unlensed = {"h_plus": np.ones(len(FREQUENCIES), dtype=np.complex128)}
    monkeypatch.setattr(
        WaveformGenerator, "generate_FD_waveform", lambda self, p, t: unlensed
    )
    monkeypatch.setattr(
        generator,
        "_get_lensing_amplification_factor",
        lambda f, r: np.full(len(FREQUENCIES), 2.0),
    )

    called = {"any": False}
    monkeypatch.setattr(
        "dingo_lensing.waveform_generator.plot_waveform_overlay",
        lambda **kwargs: called.__setitem__("any", True),
    )
    monkeypatch.setattr(
        "dingo_lensing.waveform_generator.plot_amplification_factor",
        lambda **kwargs: called.__setitem__("any", True),
    )

    generator.generate_lensed_FD_waveform((), lambda: None)

    assert called["any"] is False


def test_dev_plot_output_dir_includes_lens_model_code():
    generator = object.__new__(LensedWaveformGenerator)
    generator.dev_plot_dir = Path("dev_plots")
    generator.lens_model_code = "modwaveforms"
    generator.amplification_factor_function = "two_images_BBH"
    generator.fdsm_function = "two_images_BBH"

    output_dir = generator._dev_plot_output_dir("waveform")

    assert output_dir == Path("dev_plots") / "modwaveforms" / "two_images_BBH" / "waveform"
