from functools import cache
from importlib import import_module
from types import ModuleType
from typing import Callable


_LENS_CODE_MODULES = {
    "modwaveforms": "dingo_lensing.modwaveforms_amplification",
}
# FIXME: To integrate another lensing code, add a package-specific
# <code>_amplification.py module exposing get_amplification_factor,
# register its lens_model_code here, and set lens_model_code and
# amplification_factor_function in the YAML settings.


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
def load_amplification_factor(lens_model_code: str) -> Callable:
    module = _import_lens_code_module(lens_model_code)
    amplification_factor = getattr(module, "get_amplification_factor", None)
    if not callable(amplification_factor):
        raise TypeError(
            f"Lens model code '{lens_model_code}' must provide a callable "
            "get_amplification_factor."
        )
    return amplification_factor


@cache
def load_model_specific_parameter_names(lens_model_code: str) -> Callable:
    """Load the given lens model code's model-specific-parameter-name lookup.

    A lens code module is not required to define
    `get_model_specific_parameter_names`; if it doesn't, every
    amplification function it provides is assumed to need no extra,
    model-specific sample parameters beyond the shared lensing_delta_t/
    mu_rel.
    """
    module = _import_lens_code_module(lens_model_code)
    return getattr(
        module, "get_model_specific_parameter_names", lambda function: ()
    )
