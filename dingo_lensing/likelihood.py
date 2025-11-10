from dingo.gw.likelihood import StationaryGaussianGWLikelihood

from .waveform_generator import LensedWaveformGenerator

class StationaryGaussianLensedGWLikelihood(StationaryGaussianGWLikelihood):
    def reset_waveform_generator(self):
        self.waveform_generator.__class__ = LensedWaveformGenerator
