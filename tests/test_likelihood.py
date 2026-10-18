"""Compare local likelihood to an explicit Gaussian residual."""

import numpy as np
from dingo.gw.domains import build_domain

from dingo_lensing.likelihood import StationaryGaussianLensedGWLikelihood


def test_gaussian_residual(event):
    metadata, observation, theta = event
    settings = metadata["dataset_settings"]
    domain = build_domain(settings["domain"])
    likelihood = StationaryGaussianLensedGWLikelihood(
        wfg_kwargs=settings["waveform_generator"],
        wfg_domain=domain,
        data_domain=domain,
        event_data=observation,
        t_ref=metadata["train_settings"]["data"]["ref_time"],
    )
    signal = likelihood.signal(theta)["waveform"]
    expected = -0.5 * sum(
        np.sum(np.abs(likelihood.whitened_strains[k] - value) ** 2)
        for k, value in signal.items()
    )
    np.testing.assert_allclose(
        likelihood.log_likelihood(theta), expected, atol=1e-6, rtol=0
    )
