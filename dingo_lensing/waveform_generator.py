from typing import Dict, Tuple, Callable
from pathlib import Path
import numpy as np
from scipy.special import loggamma
from dingo.gw.waveform_generator import WaveformGenerator
import lalsimulation as LS
import dingo.gw.waveform_generator.wfg_utils as wfg_utils
from modwaveforms import geomoptics, waveoptics
from dingo_lensing.dev_mode import plot_amplification_factor, plot_waveform_overlay

class LensedWaveformGenerator(WaveformGenerator):
    def __init__(
        self,
        *args,
        dev_mode: bool = False,
        dev_plot_dir: str = "dev_plots",
        fdsm_function: str = "two_images_BBH",
        ML: float | None = None,
        y: float | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.dev_mode = dev_mode
        self.dev_plot_dir = Path(dev_plot_dir)
        self.fdsm_function = fdsm_function
        self.pointlens_ML = ML
        self.pointlens_y = y
        self._current_sample_index = None
        self._current_plot_parameters = None

    def generate_hplus_hcross(
            self, parameters: Dict[str, float], catch_waveform_errors=True
        ) -> Dict[str, np.ndarray]:

        sample_index = parameters.pop("sample_index", None)
        lensing_delta_t = parameters.pop("lensing_delta_t", None)
        mu_rel = parameters.pop("mu_rel", None)
        ML = parameters.pop("ML", None)
        y = parameters.pop("y", None)
        if ML is None:
            ML = self.pointlens_ML
        if y is None:
            y = self.pointlens_y
        self._current_sample_index = sample_index
        self._current_plot_parameters = {
            "nonlensed": parameters.copy(),
            "lensed": {
                **parameters,
                "lensing_delta_t": lensing_delta_t,
                "mu_rel": mu_rel,
                "ML": ML,
                "y": y,
            },
        }

        self.generate_FD_waveform = lambda parameters_lal, target_function: self.generate_lensed_FD_waveform(
            parameters_lal,
            target_function,
            lensing_delta_t,
            mu_rel,
        )

        try:
            return super().generate_hplus_hcross(parameters, catch_waveform_errors)
        finally:
            self._current_sample_index = None
            self._current_plot_parameters = None

    def generate_lensed_FD_waveform(
        self,
        parameters_lal: Tuple,
        target_function: Callable,
        lensing_delta_t: float,
        mu_rel: float,
    ) -> Dict[str, np.ndarray]:

        unlensed_polarizations = super().generate_FD_waveform(
            parameters_lal, target_function
        )
        amplification_factor = self._get_lensing_amplification_factor(
            self.domain.sample_frequencies,
            self._current_plot_parameters["lensed"],
            lensing_delta_t=lensing_delta_t,
            mu_rel=mu_rel,
        )
        FD_polarizations = {
            polarization: waveform * amplification_factor
            for polarization, waveform in unlensed_polarizations.items()
        }

        if getattr(self, "dev_mode", False):
            self._save_dev_plot(
                unlensed_polarizations,
                FD_polarizations,
                amplification_factor,
            )

        return FD_polarizations

    def generate_hplus_hcross_m(
        self, parameters: Dict[str, float]
    ) -> Dict[tuple, Dict[str, np.ndarray]]:

        lensing_delta_t = parameters.pop("lensing_delta_t", None)
        mu_rel = parameters.pop("mu_rel", None)        

        pol_m = super().generate_hplus_hcross_m(parameters)
        amp_factor = self._get_lensing_amplification_factor(
            self.domain.sample_frequencies,
            parameters,
            lensing_delta_t=lensing_delta_t,
            mu_rel=mu_rel,
        )

        for h in pol_m.values():
            h["h_plus"] *= amp_factor
            h["h_cross"] *= amp_factor

        return pol_m

    def _get_lensing_amplification_factor(
        self,
        frequency_array: np.ndarray,
        parameters: Dict[str, float],
        lensing_delta_t: float | None = None,
        mu_rel: float | None = None,
    ) -> np.ndarray:
        if self.fdsm_function == "one_image_BBH":
            return geomoptics.one_image_BBH(
                frequency_array,
                parameters.get("Delta_phase", 0.5 * np.pi),
            )
        elif self.fdsm_function == "two_images_BBH":
            return geomoptics.two_images_BBH(
                frequency_array,
                mu_rel,
                lensing_delta_t,
                parameters.get("Delta_phase", 0.5 * np.pi),
            )
        elif self.fdsm_function == "fold_caustic":
            return geomoptics.fold_caustic(
                frequency_array,
                lensing_delta_t,
                parameters.get("positive_phase", 1.0),
            )
        elif self.fdsm_function == "cusp_caustic":
            return geomoptics.cusp_caustic(
                frequency_array,
                parameters.get("Delta_t_10", lensing_delta_t),
                parameters.get("Delta_t_20", lensing_delta_t),
                mu_rel,
                parameters.get("positive_phase", 1.0),
            )
        elif self.fdsm_function == "pointlens":
            ML = parameters.get("ML", self.pointlens_ML)
            y = parameters.get("y", self.pointlens_y)
            if ML is None or y is None:
                raise ValueError(
                    "pointlens requires ML and y either in the sampled parameters "
                    "or in waveform_generator settings."
                )
            return self._pointlens_amplification_factor(frequency_array, ML, y)

        raise ValueError(
            f"Unsupported lensing amplification function '{self.fdsm_function}'. "
            "Available functions are: one_image_BBH, two_images_BBH, "
            "fold_caustic, cusp_caustic, pointlens."
        )

    @staticmethod
    def _pointlens_amplification_factor(
        frequency_array: np.ndarray,
        ML: float,
        y: float,
    ) -> np.ndarray:
        frequency_array = np.asarray(frequency_array)
        w = 2.0 * np.pi * (4.0 * waveoptics.TSUN * ML) * frequency_array
        amplification = LensedWaveformGenerator._pointlens_geometric_factor(
            frequency_array, ML, y
        )

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

    @staticmethod
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

    def _save_dev_plot(
        self,
        unlensed_polarizations: Dict[str, np.ndarray],
        lensed_polarizations: Dict[str, np.ndarray],
        amplification_factor: np.ndarray,
    ) -> None:
        sample_index = self._current_sample_index
        if sample_index is None:
            return

        plot_waveform_overlay(
            sample_index=int(sample_index),
            frequencies=np.asarray(self.domain.sample_frequencies),
            nonlensed_waveform=unlensed_polarizations,
            lensed_waveform=lensed_polarizations,
            nonlensed_parameters=self._current_plot_parameters["nonlensed"],
            lensed_parameters=self._current_plot_parameters["lensed"],
            output_dir=self._dev_plot_output_dir("waveform"),
            x_min=self.domain.f_min,
            x_max=self.domain.f_max,
        )
        plot_amplification_factor(
            sample_index=int(sample_index),
            frequencies=np.asarray(self.domain.sample_frequencies),
            amplification_factor=amplification_factor,
            output_dir=self._dev_plot_output_dir("amplification_factor"),
            x_min=self.domain.f_min,
            x_max=self.domain.f_max,
        )

    def _dev_plot_output_dir(self, plot_type: str) -> Path:
        return self.dev_plot_dir / self.fdsm_function / plot_type

    def generate_TD_modes_L0(self, parameters):
        # Bless both SEOBNRv4PHM and NRSur7dq4
        if self.approximant in [int(LS.SEOBNRv4PHM), int(LS.NRSur7dq4)]:
            parameters_lal_td_modes, iota = self._convert_parameters(
                {**parameters, "f_ref": self.f_ref},
                target_function="SimInspiralChooseTDModes",
            )
            hlm_td = LS.SimInspiralChooseTDModes(*parameters_lal_td_modes)
            return wfg_utils.linked_list_modes_to_dict_modes(hlm_td), iota
        else:
            raise NotImplementedError(
                f"Approximant {LS.GetApproximantFromString(self.approximant)} not "
                f"implemented. When adding this approximant to this method, make sure "
                f"the the output dict hlm_td contains the TD modes in the *L0 frame*. "
                f"In particular, adding an approximant that is implemented in the same "
                f"domain and frame as one of the approximants should just be a matter of "
                f"adding the approximant number (here: {self.approximant}) to the "
                f"corresponding if statement. However, when doing this please make sure "
                f"to test that this works as intended! Ideally, add some unit tests."
            )
