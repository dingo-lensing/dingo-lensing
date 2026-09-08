from functools import cache
from importlib import import_module
from typing import Callable


_LENS_CODE_MODULES = {
    "modwaveforms": "dingo_lensing.modwaveforms_amplification",
}


@cache
def load_amplification_factor(lens_model_code: str) -> Callable:
    try:
        module_name = _LENS_CODE_MODULES[lens_model_code]
    except KeyError:
        available_codes = ", ".join(sorted(_LENS_CODE_MODULES))
        raise ValueError(
            f"Unsupported lens model code '{lens_model_code}'. "
            f"Available lens model codes are: {available_codes}."
        ) from None

    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise ImportError(
            f"Could not load lens model code '{lens_model_code}' from "
            f"'{module_name}'. Install its required dependencies."
        ) from exc

    amplification_factor = getattr(module, "get_amplification_factor", None)
    if not callable(amplification_factor):
        raise TypeError(
            f"Lens model code '{lens_model_code}' must provide a callable "
            "get_amplification_factor."
        )
    return amplification_factor
