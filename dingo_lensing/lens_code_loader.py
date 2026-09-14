from functools import cache
from importlib import import_module
from types import ModuleType
from typing import Any, Dict, Optional


_LENS_CODE_MODULES = {
    "modwaveforms": "dingo_lensing.modwaveforms_amplification",
}
# FIXME: To integrate another lensing code, add a package-specific
# <code>_amplification.py module exposing get_model(amplification_factor_function,
# **lens_model_settings), returning an object with resolve(parameters,
# lens_model_defaults) and compute(frequency_array, resolved) methods (see
# AmplificationModel in modwaveforms_amplification.py). Register its
# lens_model_code here, and set lens_model_code and
# amplification_factor_function in the YAML settings.


@cache
def _import_lens_code_module(lens_model_code: str) -> ModuleType:
    try:
        module_name = _LENS_CODE_MODULES[lens_model_code]
    except KeyError:
        available_codes = ", ".join(sorted(_LENS_CODE_MODULES))
        raise ValueError(
            f"Unsupported lens model code '{lens_model_code}'. "
            f"Available lens model codes are: {available_codes}."
        ) from None

    try:
        return import_module(module_name)
    except ImportError as exc:
        raise ImportError(
            f"Could not load lens model code '{lens_model_code}' from "
            f"'{module_name}'. Install its required dependencies."
        ) from exc


def load_amplification_model(
    lens_model_code: str,
    amplification_factor_function: str,
    lens_model_settings: Optional[Dict[str, Any]] = None,
) -> Any:
    """Construct the model for one amplification function.

    `lens_model_settings` carries fixed, generator-construction-time
    configuration a model may need beyond a per-sample resolvable value --
    e.g. a file path to load a lookup table or interpolator from once,
    rather than on every sample. Most models need none of this and accept
    no constructor arguments at all.

    Deliberately not cached: unlike a plain function lookup, two
    generators using the same amplification function with different
    settings (e.g. different lookup table files) must not end up sharing
    one model instance.
    """
    module = _import_lens_code_module(lens_model_code)
    get_model = getattr(module, "get_model", None)
    if not callable(get_model):
        raise TypeError(
            f"Lens model code '{lens_model_code}' must provide a callable get_model."
        )
    return get_model(amplification_factor_function, **(lens_model_settings or {}))
