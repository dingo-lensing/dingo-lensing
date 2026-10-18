from dingo.gw.likelihood import StationaryGaussianGWLikelihood

from .waveform_generator import (
    LensedWaveformGenerator,
    split_waveform_settings,
)

class StationaryGaussianLensedGWLikelihood(StationaryGaussianGWLikelihood):
    def __init__(self, wfg_kwargs, *args, **kwargs):
        """Initialize the likelihood with separate lens constructor keys."""
        base, _ = split_waveform_settings(wfg_kwargs)
        super().__init__(base, *args, **kwargs)
        self.reset_waveform_generator(wfg_kwargs)

    def reset_waveform_generator(self, waveform_settings):
        """Rebuild the waveform generator with initialized lensing state."""
        waveform_domain = self.waveform_generator.full_domain
        self.waveform_generator = LensedWaveformGenerator(
            domain=waveform_domain,
            **waveform_settings,
        )
