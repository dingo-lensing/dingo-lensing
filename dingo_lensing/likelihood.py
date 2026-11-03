"""Likelihood for lensed DINGO models."""

import numpy as np
from dingo.gw.likelihood import (
    StationaryGaussianGWLikelihood,
    inner_product,
    inner_product_complex,
)

from .waveform_generator import LensedWaveformGenerator


class StationaryGaussianLensedGWLikelihood(StationaryGaussianGWLikelihood):
    def reset_waveform_generator(self, waveform_settings):
        """Rebuild the waveform generator with initialized lensing state."""
        waveform_domain = self.waveform_generator.full_domain
        self.waveform_generator = LensedWaveformGenerator(
            domain=waveform_domain,
            **waveform_settings,
        )

    def phase_grid_terms(self, theta):
        """Compute the phase-independent terms of the phase-grid likelihood.

        The signal at phase 0 is split into contributions ``mu_m`` that
        transform as ``exp(-i m phase)``. With whitened data ``d``, the terms
        of ``log L = log_Zn + kappa2 - rho2opt / 2`` at a given phase are then

        ``rho2opt = rho2opt_const + sum_{m<n} Re[c_mn exp(-i (n - m) phase)]``
        and ``kappa2 = sum_m Re[k_m exp(-i m phase)]``.

        Parameters
        ----------
        theta : dict
            Signal parameters. The phase is ignored.

        Returns
        -------
        rho2opt_const : float
            Sum over m of the inner products ``(mu_m, mu_m)``.
        rho2opt_crossterms : dict
            Complex ``c_mn = 2 (mu_m, mu_n)`` for each pair ``(m, n)``, m < n.
        kappa2_modes : dict
            Complex ``k_m = (d, mu_m)`` for each m.
        """
        d = self.whitened_strains
        pol_m = self.signal_m({**theta, "phase": 0})
        pol_m = {k: pol["waveform"] for k, pol in pol_m.items()}
        min_idx = self.data_domain.min_idx
        m_vals = sorted(pol_m.keys())

        rho2opt_const = 0
        rho2opt_crossterms = {}
        for idx, m in enumerate(m_vals):
            mu_m = pol_m[m]
            rho2opt_const += sum(
                [
                    inner_product(mu_ifo, mu_ifo, min_idx)
                    for mu_ifo in mu_m.values()
                ]
            )
            for n in m_vals[idx + 1:]:
                mu_n = pol_m[n]
                rho2opt_crossterms[(m, n)] = 2 * sum(
                    [
                        inner_product_complex(mu_m_ifo, mu_n_ifo, min_idx)
                        for mu_m_ifo, mu_n_ifo in zip(
                            mu_m.values(), mu_n.values()
                        )
                    ]
                )

        kappa2_modes = {}
        for m in m_vals:
            kappa2_modes[m] = sum(
                [
                    inner_product_complex(d_ifo, mu_ifo, min_idx)
                    for d_ifo, mu_ifo in zip(d.values(), pol_m[m].values())
                ]
            )
        return rho2opt_const, rho2opt_crossterms, kappa2_modes

    def _log_likelihood_phase_grid_mode_decomposed(self, theta, phases=None):
        """Compute the log likelihood on a grid of phases.

        Same result as DINGO 0.9.8, which evaluates the grid in a Python loop
        over the phases, but with the grid evaluated as array operations on
        the terms from ``phase_grid_terms``.

        Parameters
        ----------
        theta : dict
            Signal parameters. The phase is ignored.
        phases : numpy.ndarray, optional
            Phases at which to evaluate the likelihood. Defaults to
            ``self.phase_grid``.

        Returns
        -------
        numpy.ndarray
            Log likelihood at each phase.

        Raises
        ------
        ValueError
            If the likelihood is phase marginalized or
            ``spin_conversion_phase`` is not 0.
        NotImplementedError
            If the likelihood is time marginalized.
        """
        if self.phase_marginalization:
            raise ValueError(
                "Can't compute likelihood on a phase grid for "
                "phase-marginalized posteriors"
            )
        if self.time_marginalization:
            raise NotImplementedError(
                "log_likelihood on phase grid not yet implemented."
            )
        if self.waveform_generator.spin_conversion_phase != 0:
            raise ValueError(
                f"The log likelihood on a phase grid assumes "
                f"WaveformGenerator.spin_conversion_phase = 0, "
                f"got {self.waveform_generator.spin_conversion_phase}."
            )
        if phases is None:
            phases = self.phase_grid
        phases = np.asarray(phases)

        rho2opt_const, rho2opt_crossterms, kappa2_modes = (
            self.phase_grid_terms(theta)
        )
        rho2opt = np.full(phases.shape, float(rho2opt_const))
        for (m, n), c in rho2opt_crossterms.items():
            rho2opt += (c * np.exp(-1j * (n - m) * phases)).real
        kappa2 = np.zeros(phases.shape)
        for m, k in kappa2_modes.items():
            kappa2 += (k * np.exp(-1j * m * phases)).real
        return self.log_Zn + kappa2 - 1 / 2.0 * rho2opt
