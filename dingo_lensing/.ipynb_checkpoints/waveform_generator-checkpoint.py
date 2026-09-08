from typing import Dict, Tuple, Callable
from pathlib import Path
import numpy as np
from dingo.gw.waveform_generator import WaveformGenerator
import lalsimulation as LS
import dingo.gw.waveform_generator.wfg_utils as wfg_utils
from dingo_lensing.dev_mode import plot_amplification_factor, plot_waveform_overlay
from dingo_lensing.lens_code_loader import load_amplification_factor

class LensedWaveformGenerator(WaveformGenerator):
    def __init__(
        self,
        *args,
        dev_mode: bool = False,
        dev_plot_dir: str = "dev_plots",
        fdsm_function: str | None = None,
        lens_model_code: str = "modwaveforms",
        amplification_factor_function: str | None = None,
        ML: float | None = None,
        y: float | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.dev_mode = dev_mode
        self.dev_plot_dir = Path(dev_plot_dir)
        if (
            fdsm_function is not None
            and amplification_factor_function is not None
            and fdsm_function != amplification_factor_function
        ):
            raise ValueError(
                "fdsm_function and amplification_factor_function must match when "
                "both are specified."
            )
        self.lens_model_code = lens_model_code
        self.amplification_factor_function = (
            amplification_factor_function or fdsm_function or "two_images_BBH"
        )
        self.fdsm_function = self.amplification_factor_function
        self._amplification_factor = load_amplification_factor(
            self.lens_model_code
        )
        self.pointlens_ML = ML
        self.pointlens_y = y
        self._current_sample_index = None
        self._current_plot_parameters = None

    @property
    def fdsm_function(self) -> str:
        return self.amplification_factor_function

    @fdsm_function.setter
    def fdsm_function(self, value: str) -> None:
        self.amplification_factor_function = value

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
        # FIXME: To integrate another lensing code, add a package-specific
        # <code>_amplification.py module, register its lens_model_code in
        # lens_code_loader.py, and set lens_model_code and
        # amplification_factor_function in the YAML settings.
        return self._amplification_factor(
            self.amplification_factor_function,
            frequency_array,
            parameters,
            lensing_delta_t=lensing_delta_t,
            mu_rel=mu_rel,
            ML=self.pointlens_ML,
            y=self.pointlens_y,
        )

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
