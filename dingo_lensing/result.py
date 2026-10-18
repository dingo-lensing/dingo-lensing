"""Lensed results using the current DINGO sampler context."""

from dingo.gw.result import Result as DingoGWResult

from .inference import LensedGWSamplerContext


class LensedGWResult(DingoGWResult):
    """Use upstream weights and I/O with a lens-aware context."""

    def __init__(self, *args, sampler_context=None, **kwargs):
        """Adapt live contexts as well as serialized result payloads."""
        if sampler_context is not None:
            sampler_context = LensedGWSamplerContext.from_context(
                sampler_context
            )
        super().__init__(*args, sampler_context=sampler_context, **kwargs)

    def _build_context(self):
        """Reuse upstream metadata migrations before adapting the context."""
        context = super()._build_context()
        if context is None:
            return None
        return LensedGWSamplerContext.from_context(context)
