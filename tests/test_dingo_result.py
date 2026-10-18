"""Exercise the merge CLI that previously executed the wrong source path."""

import sys

import numpy as np
import pandas as pd
from dingo.gw.inference.context import GWSamplerContext

from dingo_lensing.pipe.dingo_result import main
from dingo_lensing.result import LensedGWResult


def test_merge_cli(event, tmp_path, monkeypatch):
    metadata, observation, _ = event
    context = GWSamplerContext.from_model_metadata(metadata, observation)
    samples = pd.DataFrame(context.prior.sample(4))
    samples["log_prob"] = -np.log(0.02)
    result = LensedGWResult(dictionary={
        "settings": metadata, "samples": samples,
        "context": context.event_data,
        "event_metadata": context.event_metadata,
    })
    result.importance_sample(num_processes=1)
    first, second = tmp_path / "first.hdf5", tmp_path / "second.hdf5"
    result.to_file(first)
    result.to_file(second)
    monkeypatch.setattr(sys, "argv", [
        "dingo_lensing_result", "--merge", "--outdir", str(tmp_path),
        "--label", "toy_merge", "--result", str(first), str(second),
    ])
    main()
    merged = LensedGWResult(file_name=tmp_path / "toy.hdf5")
    assert merged.num_samples == 8
    assert merged.sampler_context is not None
