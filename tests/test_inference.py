"""Lens-aware context regression tests."""

from copy import deepcopy

import numpy as np

from dingo_lensing.inference import LensedGWSamplerContext


def test_context_preserves_metadata_and_caches(event):
    metadata, observation, theta = event
    original = deepcopy(metadata)
    context = LensedGWSamplerContext.from_model_metadata(metadata, observation)
    likelihood = context.likelihood()
    assert context.likelihood() is likelihood
    assert metadata == original
    assert np.isfinite(likelihood.log_likelihood(theta))
    changed = context.likelihood(wfg_updates={"f_ref": 25.0})
    assert changed is not likelihood
    assert changed.waveform_generator.f_ref == 25.0
