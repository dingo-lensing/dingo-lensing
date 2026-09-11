import inspect
from typing import Dict, Tuple

import numpy as np
from scipy.special import loggamma
from modwaveforms import geomoptics, waveoptics


def _one_image_BBH(
    frequency_array: np.ndarray,
    Delta_phase: float = 0.5 * np.pi,
) -> np.ndarray:
    return geomoptics.one_image_BBH(frequency_array, Delta_phase)


def _two_images_BBH(
    frequency_array: np.ndarray,
    lensing_delta_t: float | None = None,
    mu_rel: float | None = None,
    Delta_phase: float = 0.5 * np.pi,
) -> np.ndarray:
    # The vendor geomoptics.two_images_BBH names its time-delay argument
    # Delta_t; we call it lensing_delta_t everywhere else in this package
    # (matching the sampled/YAML parameter name), so the rename happens
    # here at the call site.
    return geomoptics.two_images_BBH(
        frequency_array, mu_rel, lensing_delta_t, Delta_phase
    )


def _fold_caustic(
    frequency_array: np.ndarray,
    lensing_delta_t: float | None = None,
    positive_phase: float = 1.0,
) -> np.ndarray:
    return geomoptics.fold_caustic(frequency_array, lensing_delta_t, positive_phase)


def _cusp_caustic(
    frequency_array: np.ndarray,
    lensing_delta_t: float | None = None,
    mu_rel: float | None = None,
    Delta_t_10: float | None = None,
    Delta_t_20: float | None = None,
    positive_phase: float = 1.0,
) -> np.ndarray:
    if Delta_t_10 is None:
        Delta_t_10 = lensing_delta_t
    if Delta_t_20 is None:
        Delta_t_20 = lensing_delta_t
    return geomoptics.cusp_caustic(
        frequency_array, Delta_t_10, Delta_t_20, mu_rel, positive_phase
    )


def _pointlens(
    frequency_array: np.ndarray,
    ML: float | None = None,
    y: float | None = None,
) -> np.ndarray:
    if ML is None or y is None:
        raise ValueError(
            "pointlens requires ML and y either in the sampled parameters "
            "or in waveform_generator's lens_model_defaults setting."
        )
    return _pointlens_amplification_factor(frequency_array, ML, y)


# Registering a new amplification function here (and nowhere else) is
# enough to make it available: SUPPORTED_AMPLIFICATION_FUNCTIONS,
# get_amplification_factor and get_model_specific_parameter_names are all
# derived from this dict, not maintained separately. A parameter defaulting
# to None is treated as needing a value, resolved either from the sampled
# parameters or from a generator-level lens_model_defaults fallback; a
# parameter with any other default (e.g. Delta_phase) is a local default
# that never needs generator-level resolution.
_AMPLIFICATION_FUNCTIONS = {
    "one_image_BBH": _one_image_BBH,
    "two_images_BBH": _two_images_BBH,
    "fold_caustic": _fold_caustic,
    "cusp_caustic": _cusp_caustic,
    "pointlens": _pointlens,
}

SUPPORTED_AMPLIFICATION_FUNCTIONS: Tuple[str, ...] = tuple(_AMPLIFICATION_FUNCTIONS)


def get_model_specific_parameter_names(
    amplification_factor_function: str,
) -> Tuple[str, ...]:
    func = _AMPLIFICATION_FUNCTIONS.get(amplification_factor_function)
    if func is None:
        return ()

    return tuple(
        name
        for name, param in inspect.signature(func).parameters.items()
        if name != "frequency_array"
        and param.kind
        not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        and param.default is None
    )


def get_amplification_factor(
    amplification_factor_function: str,
    frequency_array: np.ndarray,
    parameters: Dict[str, float],
) -> np.ndarray:
    try:
        func = _AMPLIFICATION_FUNCTIONS[amplification_factor_function]
    except KeyError:
        raise ValueError(
            f"Unsupported lensing amplification function "
            f"'{amplification_factor_function}'. Available functions are: "
            f"{', '.join(SUPPORTED_AMPLIFICATION_FUNCTIONS)}."
        ) from None

    kwargs = {
        name: parameters[name]
        for name in inspect.signature(func).parameters
        if name != "frequency_array" and name in parameters
    }
    return func(frequency_array, **kwargs)


def _pointlens_amplification_factor(
    frequency_array: np.ndarray,
    ML: float,
    y: float,
) -> np.ndarray:
    frequency_array = np.asarray(frequency_array)
    w = 2.0 * np.pi * (4.0 * waveoptics.TSUN * ML) * frequency_array
    amplification = _pointlens_geometric_factor(frequency_array, ML, y)

    nonzero = w != 0.0
    exact = np.ones_like(amplification, dtype=complex)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        laguerre = np.array(
            waveoptics.vlaguerre(
                -0.5j * w[nonzero], 0, 0.5j * w[nonzero] * y**2
            ),
            dtype=complex,
        )
        log_amplification = (
            (1.0 + 0.5j * w[nonzero]) * np.log(-0.5j)
            + (1.0 + 0.5j * w[nonzero]) * np.log(w[nonzero])
            + loggamma(-0.5j * w[nonzero])
            + np.log(laguerre)
        )
        exact[nonzero] = np.exp(log_amplification)
        exact[nonzero] *= np.exp(
            -1j
            * waveoptics.pm.t_delay_geom_plus(y)
            * waveoptics.pm.t_ref(ML)
            * 2.0
            * np.pi
            * frequency_array[nonzero]
        )
        exact = np.conjugate(exact)

    finite = np.isfinite(exact.real) & np.isfinite(exact.imag)
    amplification[finite] = exact[finite]
    return amplification


def _pointlens_geometric_factor(
    frequency_array: np.ndarray,
    ML: float,
    y: float,
) -> np.ndarray:
    delta_t = waveoptics.pm.Delta_t(ML, y)
    mu_plus = waveoptics.pm.mu_plus(y)
    mu_minus = abs(waveoptics.pm.mu_minus(y))
    amplification = np.sqrt(mu_plus) - 1j * np.sqrt(mu_minus) * np.exp(
        2j * np.pi * frequency_array * delta_t
    )
    return np.conjugate(amplification)
