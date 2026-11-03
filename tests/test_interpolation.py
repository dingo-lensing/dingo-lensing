import bilby
import numpy as np
import pytest

from dingo_lensing.interpolation import (
    interpolated_log_prob_multi,
    interpolated_sample_and_log_prob_multi,
)

POINTS = np.linspace(0, 2 * np.pi, 1001)


def densities(n):
    centres = np.random.default_rng(0).uniform(0, 2 * np.pi, size=n)
    angles = POINTS[None, :] - centres[:, None]
    return np.exp(3 * np.cos(angles)) + 0.01


def test_draws_differ_across_workers():
    values = np.tile(densities(1), (64, 1))
    sample, _ = interpolated_sample_and_log_prob_multi(POINTS, values, 4)
    assert len(np.unique(sample)) == len(sample)


def test_draws_do_not_depend_on_num_processes():
    values = densities(40)
    bilby.core.utils.random.seed(3)
    serial = interpolated_sample_and_log_prob_multi(POINTS, values, 1)
    bilby.core.utils.random.seed(3)
    parallel = interpolated_sample_and_log_prob_multi(POINTS, values, 4)
    np.testing.assert_array_equal(serial[0], parallel[0])
    np.testing.assert_array_equal(serial[1], parallel[1])


def test_log_prob_is_cell_mean_density():
    values = densities(20)
    sample, log_prob = interpolated_sample_and_log_prob_multi(POINTS, values)
    for row, x, lp in zip(values, sample, log_prob):
        heights = (row[:-1] + row[1:]) / 2
        norm = np.sum(heights * np.diff(POINTS))
        cell = np.searchsorted(POINTS, x, side="right") - 1
        assert lp == pytest.approx(np.log(heights[cell] / norm), rel=1e-10)


def test_log_prob_matches_inverse_evaluation():
    values = densities(20)
    sample, log_prob = interpolated_sample_and_log_prob_multi(POINTS, values)
    log_prob_inverse = interpolated_log_prob_multi(POINTS, values, sample, 4)
    np.testing.assert_allclose(log_prob_inverse, log_prob, rtol=1e-12)


def test_draws_follow_the_density():
    values = densities(1)
    bilby.core.utils.random.seed(5)
    rows = np.tile(values, (20000, 1))
    sample, _ = interpolated_sample_and_log_prob_multi(POINTS, rows, 4)
    edges = POINTS[::50]
    counts, _ = np.histogram(sample, bins=edges)
    heights = (values[0, :-1] + values[0, 1:]) / 2
    mass = np.add.reduceat(heights * np.diff(POINTS), np.arange(0, 1000, 50))
    expected = len(sample) * mass / mass.sum()
    chi2 = np.sum((counts - expected) ** 2 / expected)
    assert chi2 < 60
