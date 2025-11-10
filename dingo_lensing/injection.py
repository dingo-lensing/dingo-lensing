from dingo.gw.injection import Injection
from .waveform_generator import LensedWaveformGenerator

class LensedInjection(Injection):
    def __init__(self, prior, **gwsignal_kwargs):

        super().__init__(prior, **gwsignal_kwargs)
        self.waveform_generator.__class__ = LensedWaveformGenerator