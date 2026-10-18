from dingo.gw.injection import Injection
from .waveform_generator import (
    LensedWaveformGenerator,
    split_waveform_settings,
)

class LensedInjection(Injection):
    def __init__(self, prior, **gwsignal_kwargs):
        """Initialize projection, noise, and a complete lens generator."""
        settings = dict(gwsignal_kwargs["wfg_kwargs"])
        base, _ = split_waveform_settings(settings)
        gwsignal_kwargs["wfg_kwargs"] = base
        super().__init__(prior, **gwsignal_kwargs)
        self.waveform_generator = LensedWaveformGenerator(
            domain=gwsignal_kwargs["wfg_domain"], **settings
        )
