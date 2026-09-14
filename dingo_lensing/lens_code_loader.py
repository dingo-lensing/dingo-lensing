from functools import cache
from importlib import import_module
from types import ModuleType
from typing import Any


_LENS_CODE_MODULES = {
    "modwaveforms": "dingo_lensing.modwaveforms_amplification",
}
# FIXME: To integrate another lensing code, add a package-specific
# <code>_amplification.py module exposing get_model(amplification_factor_function),
# returning an object with resolve(parameters, lens_model_defaults) and
# compute(frequency_array, resolved) methods (see AmplificationModel in
# modwaveforms_amplification.py). Register its lens_model_code here, and
# set lens_model_code and amplification_factor_function in the YAML
# settings.


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


@cache
def load_amplification_model(
    lens_model_code: str, amplification_factor_function: str
) -> Any:
    module = _import_lens_code_module(lens_model_code)
    get_model = getattr(module, "get_model", None)
    if not callable(get_model):
        raise TypeError(
            f"Lens model code '{lens_model_code}' must provide a callable get_model."
        )
    return get_model(amplification_factor_function)
