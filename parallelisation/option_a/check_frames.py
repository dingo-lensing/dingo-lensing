#!/usr/bin/env python3
"""Read a config's frame files the way its data-generation job will.

launch.sh runs this inside the image, so it tests the GWF reader the jobs will
use. For each detector it reads the configured channel from whole files, as
bilby_pipe does for data-dict files, then checks the data cover the stretch the
job needs (pipe_config.needed_window) with no NaN or infinite values. When the
data-dict entry names several files (a list or a glob), it reads the ones
DINGO-Lensing's data generation would choose for this event.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from pipe_config import data_dict_files, needed_window, parse_dict, read_pipe_ini

# The GWF libraries gwpy can read with, in the order it tries them.
GWF_LIBRARIES = (
    ("frameCPP", "LDAStools.frameCPP"),
    ("FrameL", "framel"),
    ("LALFrame", "lalframe"),
)


def covers(span_start: float, span_end: float, start: float, end: float, sample_rate: float) -> bool:
    """True if data from span_start to span_end include start to end.

    Allows half a sample at each end, for GPS times that floating point can't
    represent exactly.
    """
    tolerance = 0.5 / sample_rate
    return span_start <= start + tolerance and span_end >= end - tolerance


def gwf_library() -> str:
    """Name of the GWF library gwpy will read with, or 'none'."""
    for name, module in GWF_LIBRARIES:
        try:
            importlib.import_module(module)
        except ImportError:
            continue
        return name
    return "none"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path, help="Single-event dingo_pipe ini file.")
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Directory the config's data-dict paths are relative to.",
    )
    args = parser.parse_args(argv)

    # Imported here so the unit tests can import this file without gwpy.
    import numpy as np
    from gwpy.timeseries import TimeSeries

    config = read_pipe_ini(args.config)
    channels = parse_dict(config["channel-dict"])
    print(f"GWF library: {gwf_library()}")
    failed = False
    for detector, value in sorted(parse_dict(config["data-dict"]).items()):
        files = data_dict_files(value, args.run_dir)
        channel = f"{detector}:{channels[detector]}"
        start, end = needed_window(config, detector)
        if len(files) > 1:
            # Chosen as the jobs choose (dingo_lensing.pipe.multi_event, in the image).
            from dingo_lensing.pipe.multi_event import frames_overlapping

            chosen = frames_overlapping(files, start, end)
            print(f"{detector}: {len(chosen)} of {len(files)} frame files overlap the data needed: {chosen}")
            if not chosen:
                print(f"FAILED  {detector}: None of {files} overlaps GPS {start:.3f} to {end:.3f}")
                failed = True
                continue
            files = chosen
        paths = [str(args.run_dir / name) for name in files]
        path = paths[0] if len(paths) == 1 else paths
        try:
            data = TimeSeries.read(path, channel)
        except Exception as error:
            print(f"FAILED  {detector}: Could not read {channel} from {path}: {type(error).__name__}: {error}")
            failed = True
            continue
        rate = data.sample_rate.value
        span_start, span_end = float(data.span[0]), float(data.span[1])
        if not covers(span_start, span_end, start, end, rate):
            print(
                f"FAILED  {detector}: {path} holds GPS {span_start:.3f} to {span_end:.3f}, "
                f"but the job needs {start:.3f} to {end:.3f}"
            )
            failed = True
            continue
        if not np.all(np.isfinite(data.crop(start, end).value)):
            print(f"FAILED  {detector}: NaN or infinite values between GPS {start:.3f} and {end:.3f}")
            failed = True
            continue
        print(
            f"OK  {detector}: {channel} from {path}\n"
            f"    holds GPS {span_start:.3f} to {span_end:.3f} at {rate:g} Hz; the job "
            f"needs {start:.3f} to {end:.3f} ({end - start:g} s), all finite"
        )
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
