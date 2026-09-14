from typing import Dict, Tuple

import numpy as np
from scipy.special import loggamma
from modwaveforms import geomoptics, waveoptics


class AmplificationModel:
    """Base class for a single lens model's amplification factor.

    A model owns its own parameter resolution completely: resolve() pops
    and consumes whatever it needs from a sample's parameters (falling
    back to lens_model_defaults, and applying any model-specific fallback
    logic, e.g. cusp_caustic borrowing lensing_delta_t), and compute()
    turns the already-resolved values into the actual amplification
    factor. There is no shared table or signature-inspection machinery:
    adding a new model means implementing these two methods and nothing
    else, and a mistake in one model's resolve()/compute() cannot affect
    any other model's behaviour.

    A model that needs fixed, generator-construction-time configuration
    beyond a per-sample resolvable value -- e.g. a lookup table or
    interpolator loaded once from a file, rather than on every sample --
    just declares it as an ordinary __init__ parameter. get_model() below
    forwards a generator's lens_model_settings straight through to the
    constructor, so this needs no special support from resolve()/compute()
    at all.
    """

    def resolve(
        self, parameters: Dict[str, float], lens_model_defaults: Dict[str, float]
    ) -> Dict[str, float]:
        raise NotImplementedError

    def compute(
        self, frequency_array: np.ndarray, resolved: Dict[str, float]
    ) -> np.ndarray:
        raise NotImplementedError


def _resolve_with_default(name, parameters, lens_model_defaults):
    value = parameters.pop(name, None)
    if value is None:
        value = lens_model_defaults.get(name)
    return value


class OneImageBBH(AmplificationModel):
    def resolve(self, parameters, lens_model_defaults):
        return {"Delta_phase": parameters.pop("Delta_phase", 0.5 * np.pi)}

    def compute(self, frequency_array, resolved):
        return geomoptics.one_image_BBH(frequency_array, resolved["Delta_phase"])


class TwoImagesBBH(AmplificationModel):
    def resolve(self, parameters, lens_model_defaults):
        return {
            "lensing_delta_t": _resolve_with_default(
                "lensing_delta_t", parameters, lens_model_defaults
            ),
            "mu_rel": _resolve_with_default("mu_rel", parameters, lens_model_defaults),
            "Delta_phase": parameters.pop("Delta_phase", 0.5 * np.pi),
        }

    def compute(self, frequency_array, resolved):
        # The vendor geomoptics.two_images_BBH names its time-delay argument
        # Delta_t; we call it lensing_delta_t everywhere else in this
        # package (matching the sampled/YAML parameter name), so the
        # rename happens here, at the one place that calls the vendor code.
        return geomoptics.two_images_BBH(
            frequency_array,
            resolved["mu_rel"],
            resolved["lensing_delta_t"],
            resolved["Delta_phase"],
        )


class FoldCaustic(AmplificationModel):
    def resolve(self, parameters, lens_model_defaults):
        return {
            "lensing_delta_t": _resolve_with_default(
                "lensing_delta_t", parameters, lens_model_defaults
            ),
            "positive_phase": parameters.pop("positive_phase", 1.0),
        }

    def compute(self, frequency_array, resolved):
        return geomoptics.fold_caustic(
            frequency_array, resolved["lensing_delta_t"], resolved["positive_phase"]
        )


class CuspCaustic(AmplificationModel):
    def resolve(self, parameters, lens_model_defaults):
        lensing_delta_t = _resolve_with_default(
            "lensing_delta_t", parameters, lens_model_defaults
        )
        Delta_t_10 = parameters.pop("Delta_t_10", None)
        if Delta_t_10 is None:
            Delta_t_10 = lensing_delta_t
        Delta_t_20 = parameters.pop("Delta_t_20", None)
        if Delta_t_20 is None:
            Delta_t_20 = lensing_delta_t
        return {
            "Delta_t_10": Delta_t_10,
            "Delta_t_20": Delta_t_20,
            "mu_rel": _resolve_with_default("mu_rel", parameters, lens_model_defaults),
            "positive_phase": parameters.pop("positive_phase", 1.0),
        }

    def compute(self, frequency_array, resolved):
        return geomoptics.cusp_caustic(
            frequency_array,
            resolved["Delta_t_10"],
            resolved["Delta_t_20"],
            resolved["mu_rel"],
            resolved["positive_phase"],
        )


class PointLens(AmplificationModel):
    def resolve(self, parameters, lens_model_defaults):
        ML = _resolve_with_default("ML", parameters, lens_model_defaults)
        y = _resolve_with_default("y", parameters, lens_model_defaults)
        if ML is None or y is None:
            raise ValueError(
                "pointlens requires ML and y either in the sampled parameters "
                "or in waveform_generator's lens_model_defaults setting."
            )
        return {"ML": ML, "y": y}

    def compute(self, frequency_array, resolved):
        return _pointlens_amplification_factor(
            frequency_array, resolved["ML"], resolved["y"]
        )


# Registering a new amplification function means adding one entry here,
# nothing else. Each model's resolve()/compute() pair is fully
# self-contained, there is no shared table or introspection step that a
# new model needs to interact with correctly.
_AMPLIFICATION_MODEL_CLASSES: Dict[str, type] = {
    "one_image_BBH": OneImageBBH,
    "two_images_BBH": TwoImagesBBH,
    "fold_caustic": FoldCaustic,
    "cusp_caustic": CuspCaustic,
    "pointlens": PointLens,
}

SUPPORTED_AMPLIFICATION_FUNCTIONS: Tuple[str, ...] = tuple(_AMPLIFICATION_MODEL_CLASSES)


def get_model(
    amplification_factor_function: str, **lens_model_settings
) -> AmplificationModel:
    """Construct the model for one amplification function.

    `**lens_model_settings` is forwarded straight to the model class's
    constructor, so a model needing fixed, construction-time configuration
    (e.g. a lookup table file path to load once) can just declare it as a
    normal __init__ parameter. None of the models here need any, so their
    constructors take no arguments and this is a no-op for them.
    """
    try:
        model_class = _AMPLIFICATION_MODEL_CLASSES[amplification_factor_function]
    except KeyError:
        raise ValueError(
            f"Unsupported lensing amplification function "
            f"'{amplification_factor_function}'. Available functions are: "
            f"{', '.join(SUPPORTED_AMPLIFICATION_FUNCTIONS)}."
        ) from None
    return model_class(**lens_model_settings)


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
