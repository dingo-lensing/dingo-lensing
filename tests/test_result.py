"""Reload lensed results and verify unchanged upstream importance weights."""

import numpy as np
import pandas as pd
from dingo.gw.inference.context import GWSamplerContext

from dingo_lensing.result import LensedGWResult
from dingo_lensing.toy_two_image import check_weights


def test_result_roundtrip_and_weights(event, tmp_path):
    metadata, observation, _ = event
    context = GWSamplerContext.from_model_metadata(metadata, observation)
    samples = pd.DataFrame(context.prior.sample(16))
    samples["log_prob"] = -np.log(0.02)
    # Include an out-of-prior draw to exercise zero-weight handling.
    samples.loc[0, "mu_rel"] = -0.1
    result = LensedGWResult(
        dictionary={
            "settings": metadata,
            "samples": samples,
            "context": context.event_data,
            "event_metadata": context.event_metadata,
        },
        sampler_context=context,
    )
    path = tmp_path / "proposal.hdf5"
    result.to_file(path)
    restored = LensedGWResult(file_name=path)
    restored.importance_sample(num_processes=1)
    assert restored.samples.loc[0, "weights"] == 0
    assert check_weights(restored)["weight_formula_verified"]
    restored.to_file(tmp_path / "importance.hdf5")
