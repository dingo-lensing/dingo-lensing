#!/usr/bin/env python3
"""Check this branch can rebuild each model's lensed waveform generator.

The tutorial ran Juno's older code; T1 and T2 run our branch. Importance
sampling rebuilds a LensedWaveformGenerator from the waveform settings saved
inside the model, so a model written by older code could fail there, after the
run has queued and sampled. This builds the generator from those settings and
generates one waveform from a prior draw, on the submit node, in seconds.
"""
from __future__ import annotations

import sys

import numpy as np
import torch
from dingo.gw.domains import build_domain
from dingo.gw.prior import build_prior_with_defaults
from dingo_lensing.waveform_generator import LensedWaveformGenerator


def load_metadata(path: str) -> dict:
    """Load only what's needed: mmap avoids reading a 4.5 GB model's weights."""
    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=False, mmap=True)
    except (TypeError, RuntimeError):
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    return checkpoint["metadata"]


def check_model(path: str) -> None:
    settings = load_metadata(path)["dataset_settings"]
    generator = LensedWaveformGenerator(
        domain=build_domain(settings["domain"]), **settings["waveform_generator"]
    )
    parameters = build_prior_with_defaults(settings["intrinsic_prior"]).sample()
    polarizations = generator.generate_hplus_hcross(dict(parameters))
    for name, waveform in polarizations.items():
        if not np.all(np.isfinite(waveform)):
            raise ValueError(f"{name} contains NaN or infinite values")
    print(
        f"OK  {path}\n"
        f"    lens model: {generator.lens_model_code}/"
        f"{generator.amplification_factor_function}, approximant "
        f"{settings['waveform_generator']['approximant']}, one prior draw generated"
    )


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(f"usage: {sys.argv[0]} MODEL [MODEL ...]")
    failed = False
    for path in sys.argv[1:]:
        try:
            check_model(path)
        except Exception as error:
            failed = True
            print(f"FAILED  {path}\n    {type(error).__name__}: {error}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
