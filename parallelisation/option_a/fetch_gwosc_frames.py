#!/usr/bin/env python3
"""Download the GWOSC frame files a config needs, and check they read correctly.

Takes everything from the config itself (trigger time, duration, post-trigger
duration, PSD length, data-dict, channel-dict, sampling frequency), so nothing
here can drift from what dingo_lensing_pipe will use. For each detector it finds
the single 4096 s GWOSC frame file covering the PSD stretch and the segment,
saves it under the path the config's data-dict gives (Condor transfers exactly
that path), and reads the whole window back with the config's channel name.
If the data-dict entry lists several events' frames, the file goes to the
listed path with GWOSC's name (see destination).
"""
from __future__ import annotations

import argparse
import fnmatch
import math
import posixpath
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


def destination(entry, url: str, run_dir: Path) -> Path:
    """Where a downloaded frame file goes, for one data-dict entry.

    A plain path is used as it is. For a list (several events' frames), the
    file goes to the listed path with GWOSC's file name, which must be listed;
    for a glob, it keeps GWOSC's name in the glob's folder and must match.
    """
    name = posixpath.basename(url)
    if isinstance(entry, list):
        matches = [item for item in entry if posixpath.basename(item) == name]
        if len(matches) != 1:
            raise ValueError(f"GWOSC's file {name} is not listed (once) in the data-dict entry {entry}")
        return run_dir / matches[0]
    if not isinstance(entry, str):
        raise ValueError(f"Expected a path, list or glob for each detector, got {entry!r}")
    if "*" not in entry:
        return run_dir / entry
    folder, pattern = posixpath.split(entry)
    if not fnmatch.fnmatch(name, pattern):
        raise ValueError(f"GWOSC's file {name} does not match the data-dict glob {entry}")
    return run_dir / folder / name


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

    for detector, entry in sorted(data_dict.items()):
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
        path = destination(entry, urls[0], args.run_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"{detector}: Downloading {urls[0]} to {path}")
        urllib.request.urlretrieve(urls[0], path)

        channel = f"{detector}:{channel_dict[detector]}"
        try:
            data = TimeSeries.read(str(path), channel, start=start, end=end)
        except Exception as error:
            found = ", ".join(channel_names_in(path, detector)) or "none"
            sys.exit(
                f"{detector}: Could not read {channel} from {path}: {error}\n"
                f"{detector}: Channels in that file: {found}. Update channel-dict in "
                f"the config to match."
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
