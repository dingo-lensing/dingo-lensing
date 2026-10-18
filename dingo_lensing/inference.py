"""Local adaptation of DINGO's event context without upstream patching."""

from copy import copy, deepcopy

from dingo.gw.inference.context import GWSamplerContext

from .waveform_generator import (
    LensedWaveformGenerator,
    split_waveform_settings,
)


class LensedGWSamplerContext(GWSamplerContext):
    """Reuse upstream event setup with a local lens generator."""

    @classmethod
    def from_context(cls, context):
        """Build an independent context retaining event and metadata."""
        return cls.from_model_metadata(
            context.model_metadata,
            context.event_data,
            context.event_metadata,
            device=context.device,
        )

    def likelihood(self, **kwargs):
        """Build a lensed likelihood while preserving upstream event policies.

        Only a private metadata copy loses lens-only constructor settings.
        The actual context and serialized result retain the full lens model.
        """
        settings = deepcopy(
            self.model_metadata["dataset_settings"]["waveform_generator"]
        )
        updates = kwargs.pop("wfg_updates", None) or {}
        settings.update(updates)
        cache_key = deepcopy((settings, kwargs))
        if cache_key == getattr(self, "_lensed_cache_key", None):
            return self._likelihood

        base, _ = split_waveform_settings(settings)
        delegate = copy(self)
        delegate.model_metadata = deepcopy(self.model_metadata)
        delegate.model_metadata["dataset_settings"]["waveform_generator"] = (
            base
        )
        delegate._likelihood = None
        delegate._likelihood_settings = None
        likelihood = GWSamplerContext.likelihood(delegate, **kwargs)
        likelihood.waveform_generator = LensedWaveformGenerator(
            domain=likelihood.waveform_generator.full_domain, **settings
        )
        self._likelihood = likelihood
        self._lensed_cache_key = cache_key
        return likelihood
