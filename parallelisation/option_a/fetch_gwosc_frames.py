#!/usr/bin/env python3
"""Download the GWOSC frame files a config needs, and check they read correctly.

Takes everything from the config itself (trigger time, duration, post-trigger
duration, PSD length, data-dict, channel-dict, sampling frequency), so nothing
here can drift from what dingo_lensing_pipe will use. For each detector it finds
the single 4096 s GWOSC frame file covering the PSD stretch and the segment,
saves it under the path the config's data-dict gives (Condor transfers exactly
that path), and reads the whole window back with the config's channel name.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import urllib.request
from pathlib import Path

from pipe_config import data_window, parse_dict, read_pipe_ini


def channel_names_in(path, detector: str) -> list:
    """Names of a detector's channels in a GWF file, found in its raw bytes.

    GWF stores channel names as plain text, so this needs no frame library.
    It turns a wrong channel-dict entry into an error that names the fix.
    """
    pattern = re.compile(re.escape(detector.encode()) + rb":[A-Za-z0-9_\-]+")
    return sorted({name.decode() for name in pattern.findall(Path(path).read_bytes())})


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path, help="dingo_pipe ini file to fetch data for.")
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Directory the config's data-dict paths are relative to.",
    )
    args = parser.parse_args(argv)

    # Imported here so --help works without the cluster environment.
    import numpy as np
    from gwosc.locate import get_urls
    from gwpy.timeseries import TimeSeries

    config = read_pipe_ini(args.config)
    trigger_time = float(config["trigger-time"])
    duration = float(config["duration"])
    post_trigger_duration = float(config["post-trigger-duration"])
    sampling_frequency = int(float(config["sampling-frequency"]))
    start, end = data_window(
        trigger_time,
        duration,
        post_trigger_duration,
        int(config["psd-length"]),
        float(config.get("psd-maximum-duration", "1024")),
    )
    data_dict = parse_dict(config["data-dict"])
    channel_dict = parse_dict(config["channel-dict"])
    print(f"Data needed per detector: GPS {start} to {end} ({end - start:g} s)")

    for detector, relative_path in sorted(data_dict.items()):
        urls = [
            url
            for url in get_urls(
                detector,
                math.floor(start),
                math.ceil(end),
                sample_rate=sampling_frequency,
                format="gwf",
            )
            if "-4096." in url
        ]
        if len(urls) != 1:
            sys.exit(
                f"{detector}: Expected exactly one 4096 s GWOSC frame file covering "
                f"{start} to {end}, found {urls}"
            )
        destination = args.run_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        print(f"{detector}: Downloading {urls[0]}")
        urllib.request.urlretrieve(urls[0], destination)

        channel = f"{detector}:{channel_dict[detector]}"
        try:
            data = TimeSeries.read(str(destination), channel, start=start, end=end)
        except Exception as error:
            found = ", ".join(channel_names_in(destination, detector)) or "none"
            sys.exit(
                f"{detector}: Could not read {channel} from {destination}: {error}\n"
                f"{detector}: Channels in that file: {found}. Update channel-dict in "
                f"the T1 configs to match."
            )
        expected_samples = (end - start) * sampling_frequency
        if abs(len(data) - expected_samples) > 1:
            sys.exit(
                f"{detector}: Read {len(data)} samples, expected {expected_samples:g}"
            )
        if not np.all(np.isfinite(data.value)):
            sys.exit(f"{detector}: Data contains NaN or infinite values")
        print(f"{detector}: Read {len(data)} samples of {channel}, all finite")


if __name__ == "__main__":
    main()
