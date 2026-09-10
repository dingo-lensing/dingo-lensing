from typing import Dict, Tuple

import numpy as np
from scipy.special import loggamma
from modwaveforms import geomoptics, waveoptics


SUPPORTED_AMPLIFICATION_FUNCTIONS = (
    "one_image_BBH",
    "two_images_BBH",
    "fold_caustic",
    "cusp_caustic",
    "pointlens",
)

# Per-function sample parameters that are specific to this lens model code
# (as opposed to lensing_delta_t/mu_rel, which are shared across several
# amplification functions). LensedWaveformGenerator uses this registry to
# know which extra keys to pop out of a sample's parameters before they
# reach the base waveform generator, and which keys a `lens_model_defaults`
# setting may provide a generator-level fallback for.
MODEL_SPECIFIC_PARAMETERS: Dict[str, Tuple[str, ...]] = {
    "pointlens": ("ML", "y"),
}


def get_model_specific_parameter_names(
    amplification_factor_function: str,
) -> Tuple[str, ...]:
    return MODEL_SPECIFIC_PARAMETERS.get(amplification_factor_function, ())


def get_amplification_factor(
    amplification_factor_function: str,
    frequency_array: np.ndarray,
    parameters: Dict[str, float],
    lensing_delta_t: float | None = None,
    mu_rel: float | None = None,
) -> np.ndarray:
    if amplification_factor_function == "one_image_BBH":
        return geomoptics.one_image_BBH(
            frequency_array,
            parameters.get("Delta_phase", 0.5 * np.pi),
        )
    elif amplification_factor_function == "two_images_BBH":
        return geomoptics.two_images_BBH(
            frequency_array,
            mu_rel,
            lensing_delta_t,
            parameters.get("Delta_phase", 0.5 * np.pi),
        )
    elif amplification_factor_function == "fold_caustic":
        return geomoptics.fold_caustic(
            frequency_array,
            lensing_delta_t,
            parameters.get("positive_phase", 1.0),
        )
    elif amplification_factor_function == "cusp_caustic":
        return geomoptics.cusp_caustic(
            frequency_array,
            parameters.get("Delta_t_10", lensing_delta_t),
            parameters.get("Delta_t_20", lensing_delta_t),
            mu_rel,
            parameters.get("positive_phase", 1.0),
        )
    elif amplification_factor_function == "pointlens":
        pointlens_ML = parameters.get("ML")
        pointlens_y = parameters.get("y")
        if pointlens_ML is None or pointlens_y is None:
            raise ValueError(
                "pointlens requires ML and y either in the sampled parameters "
                "or in waveform_generator's lens_model_defaults setting."
            )
        return _pointlens_amplification_factor(
            frequency_array, pointlens_ML, pointlens_y
        )

    raise ValueError(
        f"Unsupported lensing amplification function "
        f"'{amplification_factor_function}'. Available functions are: "
        f"{', '.join(SUPPORTED_AMPLIFICATION_FUNCTIONS)}."
    )


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
