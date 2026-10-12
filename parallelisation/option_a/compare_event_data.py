#!/usr/bin/env python3
"""Explain how two DINGO event data files differ.

A diagnostic for when the analysis finds two copies of an event with different
event data: It lists the stored settings that differ, then, for each dataset,
how large the difference is and whether it is a pure time shift (the
frequency-domain strain of one equal to the other's times exp(-2 pi i f dt)).
Run inside the image (it needs h5py):

    apptainer exec --cleanenv --bind /home IMAGE /opt/dingo_env/bin/python -s \\
        compare_event_data.py FIRST.hdf5 SECOND.hdf5
"""
from __future__ import annotations

import argparse
from typing import Dict, Optional

import numpy as np


def time_shift(first: np.ndarray, second: np.ndarray, delta_f: float, f_min: float = 20.0) -> Optional[dict]:
    """Fit second = first * exp(-2 pi i f dt) over frequencies >= f_min.

    Returns the shift dt in seconds and the RMS phase residual of the fit
    (radians; near 0 for a pure time shift), or None if the arrays are not
    complex or share no usable frequencies.
    """
    if not (np.iscomplexobj(first) and np.iscomplexobj(second)) or first.shape != second.shape:
        return None
    frequencies = np.arange(len(first)) * delta_f
    usable = (frequencies >= f_min) & (np.abs(first) > 0) & (np.abs(second) > 0)
    if usable.sum() < 2:
        return None
    phase = np.unwrap(np.angle(second[usable] / first[usable]))
    slope, intercept = np.polyfit(frequencies[usable], phase, 1)
    residual = phase - (slope * frequencies[usable] + intercept)
    amplitude_ratio = np.abs(second[usable]) / np.abs(first[usable])
    return {
        "dt": float(-slope / (2 * np.pi)),
        "phase_offset": float(intercept),
        "phase_residual_rms": float(np.sqrt(np.mean(residual**2))),
        "amplitude_ratio_range": (float(amplitude_ratio.min()), float(amplitude_ratio.max())),
    }


def compare_arrays(first: np.ndarray, second: np.ndarray, delta_f: Optional[float]) -> dict:
    """How two arrays differ."""
    if first.shape != second.shape:
        return {"identical": False, "shapes": (first.shape, second.shape)}
    difference = np.abs(first - second)
    scale = np.abs(first)
    comparison = {
        "identical": bool(np.array_equal(first, second)),
        "differing_elements": int(np.count_nonzero(first != second)),
        "elements": int(first.size),
        "max_abs_difference": float(difference.max()) if first.size else 0.0,
        "relative_difference": float(np.linalg.norm(difference) / np.linalg.norm(scale)) if scale.any() else None,
    }
    if delta_f is not None and not comparison["identical"]:
        comparison["time_shift"] = time_shift(first, second, delta_f)
    return comparison


def read_file(path) -> Dict[str, object]:
    """{name: value} for every dataset and attribute in an event data file."""
    import h5py

    values = {}
    with h5py.File(path, "r") as file:
        for key, value in file.attrs.items():
            values[f"@{key}"] = value

        def visit(name, item):
            if isinstance(item, h5py.Dataset):
                values[name] = item[()]
            for key, value in item.attrs.items():
                values[f"{name}@{key}"] = value

        file.visititems(visit)
    return values


def same(first, second) -> bool:
    try:
        return bool(np.array_equal(np.asarray(first), np.asarray(second)))
    except Exception:
        return first == second


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("first", help="An event data file.")
    parser.add_argument("second", help="Another, of the same event.")
    args = parser.parse_args(argv)
    first, second = read_file(args.first), read_file(args.second)
    duration = first.get("settings/T")
    delta_f = 1.0 / float(duration) if duration is not None else None
    print(f"First:  {args.first}\nSecond: {args.second}\n")
    print("Stored values that differ, other than the data arrays:")
    differing = False
    for name in sorted(set(first) | set(second)):
        if name.startswith("data/"):
            continue
        if name not in first or name not in second or not same(first[name], second[name]):
            differing = True
            print(f"  {name}:\n    first:  {first.get(name)!r}\n    second: {second.get(name)!r}")
    if not differing:
        print("  none")
    print(f"\nData arrays (delta_f = {delta_f} Hz):")
    for name in sorted(n for n in set(first) | set(second) if n.startswith("data/")):
        if name not in first or name not in second:
            print(f"  {name}: only in {'first' if name in first else 'second'}")
            continue
        comparison = compare_arrays(np.asarray(first[name]), np.asarray(second[name]), delta_f)
        print(f"  {name}: {comparison}")


if __name__ == "__main__":
    main()
