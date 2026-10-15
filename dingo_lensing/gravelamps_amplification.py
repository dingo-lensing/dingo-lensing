import importlib
import logging
from typing import Dict

import numpy as np

from gravelamps.core.conversion import (
    frequency_to_dimensionless_frequency,
    lens_mass_source_to_lens_mass,
    solar_mass_to_natural_mass,
)
from gravelamps.interpolator.interpolator import (
    generate_complex_interpolator,
    read_and_validate_interpolator_files,
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------------

def _resolve_with_default(
    name: str,
    parameters: Dict[str, float],
    lens_model_defaults: Dict[str, float],
    *,
    pop: bool = True,
):
    """Resolve a parameter from the sample, falling back to model defaults."""
    if pop:
        value = parameters.pop(name, None)
    else:
        value = parameters.get(name, None)

    if value is None:
        value = lens_model_defaults.get(name)
        logger.debug(
            "Parameter '%s' not found in sample parameters; "
            "falling back to lens_model_defaults value %r.",
            name,
            value,
        )

    return value


def _require_resolved(
    name: str,
    value,
    *,
    model_name: str,
):
    """Raise a useful error for a missing required Gravelamps parameter."""
    if value is None:
        raise ValueError(
            f"There is no '{name}' parameter needed for {model_name}. "
            "Provide it in the sampled parameters or in "
            "lens_model_defaults."
        )
    return value


# -----------------------------------------------------------------------------
# Base class for physical Gravelamps lens models
# -----------------------------------------------------------------------------

class GravelampsBaseModel:
    """Base wrapper for physical lens models implemented by Gravelamps.

    The point-mass model uses the same DINGO-Lensing standard
    parameters:

        lens_mass
        lens_fractional_distance
        source_position
        luminosity_distance

    ``lens_mass`` is interpreted as the source-frame lens mass. It is converted
    to the detector-frame/redshifted lens mass using Gravelamps' standard
    distance conversion before the frequency is converted to dimensionless
    frequency.
    """

    PARAMETER_NAMES = {
        "lens_mass": "lens_mass",
        "lens_fractional_distance": "lens_fractional_distance",
        "source_position": "source_position",
        "luminosity_distance": "luminosity_distance",
    }

    gravelamps_module_name: str

    def __init__(
        self,
        gravelamps_module_name: str,
        **lens_model_settings,
    ):
        self.gravelamps_module_name = gravelamps_module_name
        self.lens_model_settings = lens_model_settings

        module_path = f"gravelamps.models.{gravelamps_module_name}"
        self.lens_module = importlib.import_module(module_path)

    def resolve(
        self,
        parameters: Dict[str, float],
        lens_model_defaults: Dict[str, float],
    ) -> Dict[str, float]:
        names = self.PARAMETER_NAMES
        resolved = {}

        # luminosity_distance is needed elsewhere by DINGO-Lensing, so retain
        # it in the input parameter dictionary.
        for internal_name, standard_name in names.items():
            value = _resolve_with_default(
                standard_name,
                parameters,
                lens_model_defaults,
                pop=(standard_name != "luminosity_distance"),
            )

            resolved[internal_name] = _require_resolved(
                standard_name,
                value,
                model_name=self.__class__.__name__,
            )

        return resolved

    def _dimensionless_frequency(
        self,
        frequency_array: np.ndarray,
        resolved: Dict[str, float],
    ) -> np.ndarray:
        # Convert source-frame lens mass to
        # detector-frame/redshifted lens mass.
        redshifted_lens_mass = lens_mass_source_to_lens_mass(
            resolved["lens_mass"],
            resolved["lens_fractional_distance"],
            resolved["luminosity_distance"],
        )
        redshifted_lens_mass_natural = solar_mass_to_natural_mass(
            redshifted_lens_mass
        )

        # Gravelamps physical lens models use dimensionless frequency. Allow a
        # model-specific converter when one is supplied, otherwise use the
        # standard Gravelamps converter.
        frequency_converter = getattr(
            self.lens_module,
            "frequency_to_dimensionless_frequency",
            frequency_to_dimensionless_frequency,
        )
        return frequency_converter(
            frequency_array,
            redshifted_lens_mass_natural,
        )

    def compute(
        self,
        frequency_array: np.ndarray,
        resolved: Dict[str, float],
    ) -> np.ndarray:
        dimensionless_frequencies = self._dimensionless_frequency(
            frequency_array, resolved
        )

        amplification_function = getattr(
            self.lens_module,
            "amplification",
        )

        return amplification_function(
            dimensionless_frequencies,
            resolved["source_position"],
        )


class GravelampsPointLens(GravelampsBaseModel):
    """Gravelamps isolated point-mass lens model.

    ``geo_switch`` and ``precision`` are fixed model settings used by the
    direct Gravelamps calculation. ``interpolator_files`` optionally points
    to the four files produced by Gravelamps' interpolation tooling. The
    interpolator is constructed once when the model is instantiated and then
    reused for every sample.
    """

    def __init__(
        self,
        geo_switch: int = 1000,
        precision: int = 2048,
        interpolator_files=None,
        **lens_model_settings,
    ):
        super().__init__(
            "isolated_point",
            **lens_model_settings,
        )

        self._geo_switch = geo_switch
        self._precision = precision
        self._interpolator = None

        if interpolator_files is not None:
            grids = read_and_validate_interpolator_files(interpolator_files)
            self._interpolator = generate_complex_interpolator(
                grids["dimensionless_frequency"],
                grids["source_position"],
                grids["amplification_factor_real"],
                grids["amplification_factor_imag"],
            )

    def compute(
        self,
        frequency_array: np.ndarray,
        resolved: Dict[str, float],
    ) -> np.ndarray:
        dimensionless_frequencies = self._dimensionless_frequency(
            frequency_array, resolved
        )

        if self._interpolator is not None:
            return self._interpolator(
                dimensionless_frequencies,
                resolved["source_position"],
            )

        return self.lens_module.amplification(
            dimensionless_frequencies,
            resolved["source_position"],
            geo_switch=self._geo_switch,
            precision=self._precision,
        )


# -----------------------------------------------------------------------------
# Phenomenological millilensing model
# -----------------------------------------------------------------------------

class GravelampsPhenom:
    """Wrapper for Gravelamps' phenomenological millilensing model.

    The model supports up to ``max_num_images`` images. The actual number
    of images, ``num_images``, is sampled for each event.

    For a given ``num_images = N``, the active lensing parameters are

        n0
        mu_rel1, dt1, n1
        ...
        mu_rel{N-1}, dt{N-1}, n{N-1}

    Parameters for images >= ``num_images`` are sampled by the outer
    inference framework but are ignored by the waveform model.
    """

    PARAMETER_NAMES = {}

    def __init__(
        self,
        max_num_images: int = 6,
        **lens_model_settings,
    ):

        max_num_images = int(max_num_images)
        if max_num_images < 1:
            raise ValueError("GravelampsPhenom requires max_num_images >= 1.")

        self.max_num_images = max_num_images
        self.lens_model_settings = lens_model_settings
        self.lens_module = importlib.import_module(
            "gravelamps.models.phenomenological_millilensing"
        )

        # Keep the mapping explicit and inspectable. These are the native
        # parameter names expected by Gravelamps' phenomenological module.
        self.PARAMETER_NAMES = {"num_images": "num_images",
                                "morse_index_0": "n0"}
        for image in range(1, self.max_num_images):
            self.PARAMETER_NAMES[f"relative_magnification_{image}"] = (
                f"mu_rel{image}"
                )
            self.PARAMETER_NAMES[f"time_delay_{image}"] = (
                f"dt{image}"
                )
            self.PARAMETER_NAMES[f"morse_index_{image}"] = (
                f"n{image}"
                )

    def resolve(
        self,
        parameters: Dict[str, float],
        lens_model_defaults: Dict[str, float],
    ) -> Dict[str, object]:

        # ------------------------------------------------------------
        # Resolve number of images
        # ------------------------------------------------------------
        num_images = _resolve_with_default(
            "num_images",
            parameters,
            lens_model_defaults,
            pop=True,
        )

        num_images = int(
            _require_resolved(
                "num_images",
                num_images,
                model_name=self.__class__.__name__,
            )
        )

        if not 1 <= num_images <= self.max_num_images:
            raise ValueError(
                f"num_images must be between 1 and "
                f"{self.max_num_images}, got {num_images}."
            )

        # ------------------------------------------------------------
        # Resolve primary image
        # ------------------------------------------------------------
        n0 = _resolve_with_default(
            "n0",
            parameters,
            lens_model_defaults,
            pop=True,
        )

        n0 = _require_resolved(
            "n0",
            n0,
            model_name=self.__class__.__name__,
        )

        resolved = {
            "num_images": num_images,
            "morse_indices": [n0],
            "magnifications": [1.0],
            "time_delays": [0.0],
        }

        # ------------------------------------------------------------
        # Resolve active images only
        # ------------------------------------------------------------
        for image in range(1, num_images):

            mu_name = f"mu_rel{image}"
            dt_name = f"dt{image}"
            n_name = f"n{image}"

            mu = _resolve_with_default(
                mu_name,
                parameters,
                lens_model_defaults,
                pop=True,
            )

            dt = _resolve_with_default(
                dt_name,
                parameters,
                lens_model_defaults,
                pop=True,
            )

            n = _resolve_with_default(
                n_name,
                parameters,
                lens_model_defaults,
                pop=True,
            )

            resolved["magnifications"].append(
                _require_resolved(
                    mu_name,
                    mu,
                    model_name=self.__class__.__name__,
                )
            )

            resolved["time_delays"].append(
                _require_resolved(
                    dt_name,
                    dt,
                    model_name=self.__class__.__name__,
                )
            )

            resolved["morse_indices"].append(
                _require_resolved(
                    n_name,
                    n,
                    model_name=self.__class__.__name__,
                )
            )
        # ------------------------------------------------------------
        # Remove inactive image parameters from the input dictionary.
        # These parameters are still present in the dictionary,
        # but they must not be passed to the unlensed waveform generator.
        # ------------------------------------------------------------
        for image in range(num_images, self.max_num_images):

            parameters.pop(f"mu_rel{image}", None)
            parameters.pop(f"dt{image}", None)
            parameters.pop(f"n{image}", None)

        return resolved

    def compute(
        self,
        frequency_array: np.ndarray,
        resolved: Dict[str, object],
    ) -> np.ndarray:
        # Unlike the physical point-mass/SIS models,
        # the phenomenological model takes physical frequencies directly.
        amplification_function = getattr(
            self.lens_module,
            "amplification",
        )

        return amplification_function(
            np.asarray(frequency_array),
            resolved["num_images"],
            np.asarray(resolved["magnifications"]),
            np.asarray(resolved["time_delays"]),
            np.asarray(resolved["morse_indices"]),
        )


# -----------------------------------------------------------------------------
# Convenience factory
# -----------------------------------------------------------------------------

_GRAVELAMPS_MODEL_CLASSES = {
    "gravelamps_pointlens": GravelampsPointLens,
    "gravelamps_phenom": GravelampsPhenom,
}

SUPPORTED_GRAVELAMPS_MODELS = tuple(_GRAVELAMPS_MODEL_CLASSES)


def get_model(model_name: str, **lens_model_settings):
    """Construct one of the standalone Gravelamps wrapper models."""
    try:
        model_class = _GRAVELAMPS_MODEL_CLASSES[model_name]
    except KeyError:
        raise ValueError(
            f"Unsupported Gravelamps model '{model_name}'. Available models: "
            f"{', '.join(SUPPORTED_GRAVELAMPS_MODELS)}."
        ) from None

    return model_class(**lens_model_settings)
