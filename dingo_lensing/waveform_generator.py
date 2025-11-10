from typing import Dict
import numpy as np
import modwaveforms
from dingo.gw.waveform_generator import WaveformGenerator
import lalsimulation as LS
import dingo.gw.waveform_generator.wfg_utils as wfg_utils

class LensedWaveformGenerator(WaveformGenerator):
    def generate_hplus_hcross(
            self, parameters: Dict[str, float], catch_waveform_errors=True
        ) -> Dict[str, np.ndarray]:

        lensing_delta_t = parameters.pop("lensing_delta_t", None)
        mu_rel = parameters.pop("mu_rel", None)

        polarizations = super().generate_hplus_hcross(parameters, catch_waveform_errors=catch_waveform_errors)
        amp_factor = modwaveforms.geomoptics.two_images_BBH(
            self.domain.sample_frequencies,
            mu_rel,
            lensing_delta_t,
            0.5*np.pi,
        )

        polarizations["h_plus"] *= amp_factor
        polarizations["h_cross"] *= amp_factor

        return polarizations

   
    def generate_hplus_hcross_m(
        self, parameters: Dict[str, float]
    ) -> Dict[tuple, Dict[str, np.ndarray]]:

        lensing_delta_t = parameters.pop("lensing_delta_t", None)
        mu_rel = parameters.pop("mu_rel", None)        

        pol_m = super().generate_hplus_hcross_m(parameters)
        amp_factor = modwaveforms.geomoptics.two_images_BBH(
            self.domain.sample_frequencies,
            mu_rel,
            lensing_delta_t,
            0.5*np.pi,
        )

        for h in pol_m.values():
            h["h_plus"] *= amp_factor
            h["h_cross"] *= amp_factor

        return pol_m

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