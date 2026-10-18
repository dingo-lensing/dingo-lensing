"""Lensed dataset generation using reusable DINGO building blocks."""

from copy import deepcopy
from functools import partial
from multiprocessing import Pool

import numpy as np
import pandas as pd
import yaml
from dingo.core.utils.misc import call_func_strict_output_dim
from dingo.gw.dataset.generate_dataset import (
    generate_parameters_and_polarizations as upstream_generate_parameters,
)
from dingo.gw.dataset.generate_dataset import (
    parse_args,
    train_svd_basis,
)
from dingo.gw.dataset.waveform_dataset import WaveformDataset
from dingo.gw.domains import build_domain
from dingo.gw.prior import build_prior_with_defaults
from dingo.gw.SVD import ApplySVD, SVDBasis
from dingo.gw.transforms import HeterodynePhase, WhitenFixedASD
from threadpoolctl import threadpool_limits
from torchvision.transforms import Compose

from .dev_mode import generate_waveforms_parallel, normalize_dev_mode_settings
from .waveform_generator import LensedWaveformGenerator


def generate_parameters_and_polarizations(
    waveform_generator, prior, num_samples, num_processes
):
    """Reuse failure filtering and retain indices for dev plots."""
    if not waveform_generator.dev_mode:
        return upstream_generate_parameters(
            waveform_generator, prior, num_samples, num_processes
        )
    parameters = pd.DataFrame(prior.sample(num_samples))
    with threadpool_limits(limits=1, user_api="blas"):
        if num_processes > 1:
            with Pool(num_processes) as pool:
                polarizations = generate_waveforms_parallel(
                    waveform_generator, parameters, pool
                )
        else:
            polarizations = generate_waveforms_parallel(
                waveform_generator, parameters
            )
    valid = np.all(np.isfinite(polarizations["h_plus"]), axis=1)
    return parameters.loc[valid], {
        k: v[valid] for k, v in polarizations.items()
    }


def generate_dataset(settings, num_processes=1):
    """Build a lensed dataset, preserving whitening and SVD compression.

    Only orchestration lives here: sampling, waveform evaluation, dataset I/O,
    compression transforms, and basis construction use existing helpers.
    """
    settings = normalize_dev_mode_settings(deepcopy(settings))
    prior = build_prior_with_defaults(settings["intrinsic_prior"])
    domain = build_domain(settings["domain"])
    generator = LensedWaveformGenerator(
        domain=domain, **settings["waveform_generator"]
    )
    draw = partial(
        generate_parameters_and_polarizations,
        generator,
        prior,
        num_processes=num_processes,
    )
    compression = settings.get("compression") or {}
    transforms = []
    dataset = {"settings": settings}
    if "whitening" in compression:
        transforms.append(
            WhitenFixedASD(
                domain, asd_file=compression["whitening"], inverse=False
            )
        )
    if "phase_heterodyning" in compression:
        if generator._domain_transform is not None:
            raise NotImplementedError(
                "Phase heterodyning requires generation on the dataset domain."
            )
        transforms.append(
            HeterodynePhase(
                domain, inverse=False, **compression["phase_heterodyning"]
            )
        )
    if "svd" in compression:
        svd = compression["svd"]
        if "file" in svd:
            basis = SVDBasis(file_name=svd["file"])
        else:
            generator.transform = Compose(transforms)
            n_train = svd["num_training_samples"]
            n_test = svd.get("num_validation_samples", 0)
            parameters, polarizations = call_func_strict_output_dim(
                draw, n_train + n_test
            )
            basis_settings = deepcopy(settings)
            basis_settings["num_samples"] = len(parameters)
            del basis_settings["compression"]["svd"]
            basis_dataset = WaveformDataset(
                dictionary={
                    "settings": basis_settings,
                    "parameters": parameters,
                    "polarizations": polarizations,
                }
            )
            basis, _, _ = train_svd_basis(basis_dataset, svd["size"], n_train)
        dataset["svd"] = basis.to_dictionary()
        transforms.append(ApplySVD(basis))
    generator.transform = Compose(transforms)
    parameters, polarizations = call_func_strict_output_dim(
        draw, settings["num_samples"]
    )
    settings["num_samples"] = len(parameters)
    dataset.update(parameters=parameters, polarizations=polarizations)
    return WaveformDataset(dictionary=dataset)


def main():
    """Generate and save a dataset with the existing DINGO CLI arguments."""
    args = parse_args()
    with open(args.settings_file) as stream:
        settings = normalize_dev_mode_settings(
            yaml.safe_load(stream), args.settings_file
        )
    generate_dataset(settings, args.num_processes).to_file(args.out_file)


if __name__ == "__main__":
    main()
