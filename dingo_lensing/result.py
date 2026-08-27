from typing import Optional
import numpy as np
from dingo.gw.result import Result as DingoGWResult
from dingo.gw.domains.build_domain import build_domain

from .likelihood import StationaryGaussianLensedGWLikelihood

class LensedGWResult(DingoGWResult):
    def _build_likelihood(self, **kwargs):
        super()._build_likelihood(**kwargs)
        self.likelihood.__class__ = StationaryGaussianLensedGWLikelihood
        waveform_settings = self.base_metadata["dataset_settings"][
            "waveform_generator"
        ]
        self.likelihood.reset_waveform_generator(waveform_settings)
