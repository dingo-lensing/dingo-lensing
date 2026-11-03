"""Results for lensed DINGO models."""

import dingo.gw.result as dingo_gw_result
from bilby.core.prior import Constraint, DeltaFunction, PriorDict
from dingo.gw.result import Result as DingoGWResult

from . import interpolation
from .likelihood import StationaryGaussianLensedGWLikelihood


class LensedGWResult(DingoGWResult):
    def _build_prior(self):
        """Build the prior, splitting off parameters that are not sampled.

        DINGO splits off the phase and time priors of networks that leave
        those parameters out. A lensed network may also leave out a lensing
        parameter, such as the Morse phase ``Delta_phase``. Its prior is kept
        in ``unsampled_priors`` until ``update_prior`` fixes it to one value,
        which selects a hypothesis, e.g.
        ``{"Delta_phase": 1.5707963267948966}`` for a type II image. A
        parameter whose prior is already a ``DeltaFunction`` is added to the
        samples at that value.
        """
        super()._build_prior()
        self.unsampled_priors = {}
        if self.samples is None:
            return
        for key, prior in list(self.prior.items()):
            if key in self.samples or isinstance(prior, Constraint):
                continue
            if isinstance(prior, DeltaFunction):
                self.samples[key] = prior.peak
            else:
                self.unsampled_priors[key] = self.prior.pop(key)

    def update_prior(self, prior_update):
        """Update the prior, fixing parameters that are not sampled.

        A parameter missing from the samples (see ``_build_prior``) can only
        be updated to a single value, which is then added to the samples, so
        that the likelihood is evaluated at it.

        Parameters
        ----------
        prior_update : dict
            Priors to update, of the form ``{key: prior_str}``, as in DINGO.

        Raises
        ------
        ValueError
            If a parameter missing from the samples is given a prior other
            than a ``DeltaFunction``.
        """
        fixed = PriorDict(
            {
                key: value
                for key, value in prior_update.items()
                if key in self.unsampled_priors
            }
        )
        for key, prior in fixed.items():
            if not isinstance(prior, DeltaFunction):
                raise ValueError(
                    f"{key} is not sampled, so it can only be fixed to one "
                    f"value, not given the prior {prior}."
                )
        super().update_prior(prior_update)
        for key, prior in fixed.items():
            self.samples[key] = prior.peak
            del self.unsampled_priors[key]

    def _build_likelihood(self, **kwargs):
        if self.unsampled_priors:
            raise ValueError(
                f"Not sampled: {', '.join(self.unsampled_priors)}. Fix each "
                "to one value with a prior update, e.g. "
                "{Delta_phase: 1.5707963267948966} for a type II image."
            )
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
