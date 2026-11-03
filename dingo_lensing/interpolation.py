"""Synthetic phase draws with independent random streams.

In DINGO 0.9.8 the synthetic phase is drawn inside forked pool workers, which
all start from the same random state, so the draws repeat from one worker to
the next. Its density is also sampled piecewise constant but evaluated
piecewise linear. The functions here draw all uniform variates in the main
process and sample and evaluate the same piecewise-constant density, as DINGO
does from version 0.10.1.
"""

from functools import partial
from itertools import starmap
from multiprocessing import Pool

import bilby
import numpy as np
from scipy.stats import rv_histogram
from threadpoolctl import threadpool_limits


def interpolated_sample_and_log_prob_multi(
    sample_points, values, num_processes=1
):
    """Draw one sample from each of several gridded densities.

    Parameters
    ----------
    sample_points : numpy.ndarray, shape (N,)
        Grid points, in increasing order.
    values : numpy.ndarray, shape (B, N)
        Unnormalised density of each of the B distributions on the grid.
    num_processes : int
        Number of processes.

    Returns
    -------
    sample : numpy.ndarray, shape (B,)
        One sample from each distribution.
    log_prob : numpy.ndarray, shape (B,)
        Log density of each sample.
    """
    uniforms = bilby.core.utils.random.rng.uniform(size=len(values))
    task = partial(interpolated_sample_and_log_prob, sample_points)
    result = _starmap(task, zip(values, uniforms), num_processes)
    sample, log_prob = np.array(result).T
    return sample, log_prob


def interpolated_sample_and_log_prob(sample_points, values, uniform):
    """Map a uniform variate to a sample of a gridded density.

    Parameters
    ----------
    sample_points : numpy.ndarray, shape (N,)
        Grid points, in increasing order.
    values : numpy.ndarray, shape (N,)
        Unnormalised density on the grid.
    uniform : float
        Uniform variate on [0, 1).

    Returns
    -------
    sample : float
        The sample, from the inverse CDF.
    log_prob : float
        Log density of the sample.
    """
    density = _cell_mean_histogram(sample_points, values)
    sample = density.ppf(uniform)
    return sample, density.logpdf(sample)


def interpolated_log_prob_multi(
    sample_points, values, evaluation_points, num_processes=1
):
    """Evaluate each of several gridded densities at one point.

    Parameters
    ----------
    sample_points : numpy.ndarray, shape (N,)
        Grid points, in increasing order.
    values : numpy.ndarray, shape (B, N)
        Unnormalised density of each of the B distributions on the grid.
    evaluation_points : numpy.ndarray, shape (B,)
        Point at which to evaluate each distribution.
    num_processes : int
        Number of processes.

    Returns
    -------
    numpy.ndarray, shape (B,)
        Log density of each distribution at its point.
    """
    task = partial(interpolated_log_prob, sample_points)
    result = _starmap(task, zip(values, evaluation_points), num_processes)
    return np.array(result)


def interpolated_log_prob(sample_points, values, evaluation_point):
    """Evaluate a gridded density at one point.

    Parameters
    ----------
    sample_points : numpy.ndarray, shape (N,)
        Grid points, in increasing order.
    values : numpy.ndarray, shape (N,)
        Unnormalised density on the grid.
    evaluation_point : float
        Point at which to evaluate the density.

    Returns
    -------
    float
        Log density at the point.
    """
    density = _cell_mean_histogram(sample_points, values)
    return density.logpdf(evaluation_point)


def _cell_mean_histogram(sample_points, values):
    """Build the piecewise-constant density of a grid.

    The height in each grid cell is the mean of the values at its two ends,
    so each cell keeps the mass the trapezoid rule gives it.

    Parameters
    ----------
    sample_points : numpy.ndarray, shape (N,)
        Grid points, in increasing order.
    values : numpy.ndarray, shape (N,)
        Unnormalised density on the grid.

    Returns
    -------
    scipy.stats.rv_histogram
        The normalised density.
    """
    values = np.asarray(values)
    heights = (values[:-1] + values[1:]) / 2
    return rv_histogram((heights, np.asarray(sample_points)), density=True)


def _starmap(func, arguments, num_processes):
    """Apply a function to argument tuples, in parallel if requested.

    Parameters
    ----------
    func : callable
        Function to apply.
    arguments : iterable of tuple
        Arguments of each call.
    num_processes : int
        Number of processes.

    Returns
    -------
    list
        The results, in order.
    """
    with threadpool_limits(limits=1, user_api="blas"):
        if num_processes > 1:
            with Pool(processes=num_processes) as pool:
                return pool.starmap(func, arguments)
        return list(starmap(func, arguments))
