"""Results for lensed DINGO models."""

import dingo.gw.result as dingo_gw_result
from dingo.gw.result import Result as DingoGWResult

from . import interpolation
from .likelihood import StationaryGaussianLensedGWLikelihood


class LensedGWResult(DingoGWResult):
    def _build_likelihood(self, **kwargs):
        super()._build_likelihood(**kwargs)
        self.likelihood.__class__ = StationaryGaussianLensedGWLikelihood
        waveform_settings = self.base_metadata["dataset_settings"][
            "waveform_generator"
        ]
        self.likelihood.reset_waveform_generator(waveform_settings)

    def sample_synthetic_phase(self, synthetic_phase_kwargs, inverse=False):
        """Sample the synthetic phase with independent draws.

        Runs DINGO's ``sample_synthetic_phase`` with the draws from
        ``dingo_lensing.interpolation``, which take every uniform variate from
        the main process.

        Parameters
        ----------
        synthetic_phase_kwargs : dict
            Synthetic phase settings, passed on to DINGO.
        inverse : bool
            If True, evaluate the log prob of the existing phases instead of
            drawing new ones.
        """
        names = [
            "interpolated_sample_and_log_prob_multi",
            "interpolated_log_prob_multi",
        ]
        originals = {name: getattr(dingo_gw_result, name) for name in names}
        for name in names:
            setattr(dingo_gw_result, name, getattr(interpolation, name))
        try:
            super().sample_synthetic_phase(synthetic_phase_kwargs, inverse)
        finally:
            for name, func in originals.items():
                setattr(dingo_gw_result, name, func)
