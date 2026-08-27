from dingo.gw.likelihood import StationaryGaussianGWLikelihood

from .waveform_generator import LensedWaveformGenerator

class StationaryGaussianLensedGWLikelihood(StationaryGaussianGWLikelihood):
    def reset_waveform_generator(self, waveform_settings):
        """Rebuild the waveform generator with initialized lensing state."""
        waveform_domain = self.waveform_generator.full_domain
        self.waveform_generator = LensedWaveformGenerator(
            domain=waveform_domain,
            **waveform_settings,
        )
