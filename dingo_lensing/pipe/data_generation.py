import os
import sys

import numpy as np
from bilby_pipe.main import parse_args
from bilby_pipe.utils import logger
from dingo.core.posterior_models.build_model import build_model_from_kwargs
from dingo.gw.data.event_dataset import EventDataset
from dingo.gw.domains import UniformFrequencyDomain, build_domain_from_model_metadata
from dingo.pipe.data_generation import (
    DataGenerationInput,
    create_generation_parser
)

from .multi_event import psd_file_name

logger.name = "dingo_lensing_pipe"

class LensedDataGenerationInput(DataGenerationInput):
    """DINGO's data generation, made safe for one config listing several events.

    Each job writes its PSDs to its own text files, named after the job like
    its event data file. DINGO writes <outdir>/data/<detector>_psd.txt for
    every event, so the last job to finish would overwrite the others'.
    """

    def save_hdf5(self):
        """
        Save frequency-domain strain and ASDs as DingoDataset HDF5 format.

        This method will also save the PSDs as .txt files in the data directory
        for easy reading by pesummary and Bilby, one file per detector named
        after this job (see psd_file_name). Otherwise identical to DINGO
        0.9.8's DataGenerationInput.save_hdf5.
        """

        try:
            model = build_model_from_kwargs(
                filename=self.model, device="meta", load_training_info=False
            )
        except RuntimeError:
            # 'meta' is not supported by older version of python / torch
            model = build_model_from_kwargs(
                filename=self.model, device="cpu", load_training_info=False
            )
        domain = build_domain_from_model_metadata(model.metadata, base=True)
        assert isinstance(domain, UniformFrequencyDomain)

        if self.save_bilby_data_dump:
            # this is needed because we want bilby to use the updated DINGO
            # prior
            self.waveform_arguments_dict = self.injection_waveform_arguments
            self.prior_dict = self.priors
            self.likelihood_type = "GravitationalWaveTransient"
            self.calibration_marginalization = False
            self.phase_marginalization = False
            self.time_marginalization = False
            self.distance_marginalization = False
            self.number_of_response_curves = 0
            self._distance_marginalization_lookup_table = None
            self.reference_frame = "sky"
            self.fiducial_parameters = None
            self.update_fiducial_parameters = None
            self.epsilon = None
            self.jitter_time = True
            self.save_data_dump()

        # PSD and strain data.
        data = {"waveform": {}, "asds": {}}  # TODO: Rename these keys.
        for ifo in self.interferometers:
            strain = ifo.strain_data.frequency_domain_strain
            frequency_array = ifo.strain_data.frequency_array
            asd = ifo.power_spectral_density.get_amplitude_spectral_density_array(
                frequency_array
            )

            # These arrays extend up to self.sampling_frequency / 2. Truncate them to
            # the model maximum frequency, and also set the ASD to 1.0 below model
            # minimum frequency.
            strain = domain.update_data(strain)
            asd = domain.update_data(asd, low_value=1.0)

            # Dingo expects data to have trigger time 0, so we apply a cyclic time shift
            # by the post-trigger duration.
            strain = domain.time_translate_data(strain, self.post_trigger_duration)

            # Note that the ASD estimated by the Bilby Interferometer differs ever so
            # slightly from the ASDs we computed before using pycbc. In addition,
            # there is no handling of NaNs in the strain data from which the ASD is
            # estimated.

            data["waveform"][ifo.name] = strain
            data["asds"][ifo.name] = asd

        # Data conditioning settings.
        settings = {
            "time_event": self.trigger_time,
            "time_buffer": self.post_trigger_duration,
            "detectors": self.detectors,
            "f_s": self.sampling_frequency,
            "T": self.duration,
            "window_type": "tukey",
            "roll_off": self.tukey_roll_off,
            "minimum_frequency": self.minimum_frequency_dict,
            "maximum_frequency": self.maximum_frequency_dict,
        }

        for k in [
            "psd_duration",
            "psd_dict",
            "psd_fractional_overlap",
            "psd_start_time",
            "psd_method",
            "channel_dict",
            "data_dict",
            "injection",
            "generation_seed",
            "gaussian_noise",
            "zero_noise",
            "numerical_relativity_file",
            "injection_waveform_approximant",
            "injection_frequency_domain_source_model",
        ]:
            try:
                v = getattr(self, k)
            except AttributeError:
                continue
            if v is not None and v is not False:
                settings[k] = v

        if self.injection:
            settings["injection_parameters"] = self.injection_parameters.copy()
            settings["dingo_injection"] = self.dingo_injection
            # Dingo and Bilby have different geocent_time conventions.
            settings["injection_parameters"]["geocent_time"] -= self.trigger_time
            settings["optimal_SNR"] = {
                k: (
                    v["optimal_SNR"].item()
                    if hasattr(v["optimal_SNR"], "item")
                    else v["optimal_SNR"]
                )
                for k, v in self.interferometers.meta_data.items()
            }
            settings["matched_filter_SNR"] = {
                k: (
                    v["matched_filter_SNR"].item()
                    if hasattr(v["matched_filter_SNR"], "item")
                    else v["matched_filter_SNR"]
                )
                for k, v in self.interferometers.meta_data.items()
            }

        dataset = EventDataset(
            dictionary={
                "data": data,
                "settings": settings,
            }
        )
        dataset.to_file(self.event_data_file)

        # also saving the psd as a .txt file which can be read in
        # easily by pesummary or bilby
        for ifo in self.interferometers:
            np.savetxt(
                os.path.join(self.data_directory, psd_file_name(self.label, ifo.name)),  # DINGO-Lensing: One file per job.
                np.vstack([domain(), data["asds"][ifo.name] ** 2]).T,
            )

def main():
    """Data generation main logic"""
    args, unknown_args = parse_args(sys.argv[1:], create_generation_parser())
    # log_version_information()
    data = LensedDataGenerationInput(args, unknown_args)
    data.save_hdf5()
    logger.info("Completed data generation")
