#!/usr/bin/env python3
"""Download the GWOSC frame files a config needs, and check they read correctly.

Takes everything from the config itself (trigger time, duration, post-trigger
duration, PSD length, data-dict, channel-dict), so nothing here can drift from
what the pipeline will use. For each detector it finds the 4096 s GWOSC frame
files covering the PSD stretch and the segment (usually one, two if the stretch
crosses a file boundary), saves them under the paths the config's data-dict
gives (Condor transfers exactly those paths), and reads the whole window back
with the config's channel name. If the data-dict entry lists several events'
frames, each file goes to the listed path with GWOSC's name (see destination).

GWOSC's files are 4096 Hz whatever the config's sampling-frequency: The jobs
resample them to the model's rate.
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
from typing import List

from pipe_config import data_window, parse_dict, read_pipe_ini

GWOSC_SAMPLE_RATE = 4096
FILE_DURATION = 4096
# GWOSC's file names follow LIGO-T010150: <observatory>-<tag>-<GPS start>-<duration>.gwf.
FRAME_NAME = re.compile(r"^[A-Za-z0-9]+-.+-(?P<start>\d+)-(?P<duration>\d+)\.gwf$")


def channel_names_in(path, detector: str) -> list:
    """Names of a detector's channels in a GWF file, found in its raw bytes.

    GWF stores channel names as plain text, so this needs no frame library.
    It turns a wrong channel-dict entry into an error that names the fix.
    """
    pattern = re.compile(re.escape(detector.encode()) + rb":[A-Za-z0-9_\-]+")
    return sorted({name.decode() for name in pattern.findall(Path(path).read_bytes())})


def frames_for_window(urls, start: float, end: float) -> List[str]:
    """The URLs of the 4096 s GWOSC frame files that hold GPS start to end, in time order.

    GWOSC also lists 32 s event files, and can list one file under both an
    event's and the run's URL; this keeps one URL per 4096 s file and checks
    that the files it keeps cover the window without a gap.
    """
    files = {}
    for url in urls:
        name = posixpath.basename(url)
        match = FRAME_NAME.match(name)
        if match and int(match.group("duration")) == FILE_DURATION:
            files.setdefault(name, url)
    spans = sorted((int(FRAME_NAME.match(name).group("start")), name) for name in files)
    chosen = [(first, name) for first, name in spans if first < end and start < first + FILE_DURATION]
    covered = start
    for first, _ in chosen:
        if first > covered:
            break
        covered = max(covered, first + FILE_DURATION)
    if not chosen or chosen[0][0] > start or covered < end:
        raise ValueError(
            f"GWOSC's 4096 s frame files {sorted(files)} do not cover GPS {start} to {end} without a gap"
        )
    return [files[name] for _, name in chosen]


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


def destinations(entry, urls, run_dir: Path) -> List[Path]:
    """Where each of a detector's frame files goes: One distinct path per file."""
    paths = [destination(entry, url, run_dir) for url in urls]
    if len(set(paths)) != len(paths):
        raise ValueError(
            f"The data-dict entry {entry!r} names one path for the {len(urls)} files the data need; "
            "list each file's path instead"
        )
    return paths


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path, help="dingo_pipe ini file to fetch data for.")
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Directory the config's data-dict paths are relative to.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Keep a frame file already at its destination (fetched for another config) instead of downloading it again.",
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
        found = get_urls(
            detector, math.floor(start), math.ceil(end), sample_rate=GWOSC_SAMPLE_RATE, format="gwf"
        )
        try:
            urls = frames_for_window(found, start, end)
            paths = destinations(entry, urls, args.run_dir)
        except ValueError as error:
            sys.exit(f"{detector}: {error}")
        for url, path in zip(urls, paths):
            if args.skip_existing and path.is_file():
                print(f"{detector}: {path} already fetched")
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"{detector}: Downloading {url} to {path}")
            urllib.request.urlretrieve(url, path)

        channel = f"{detector}:{channel_dict[detector]}"
        source = str(paths[0]) if len(paths) == 1 else [str(path) for path in paths]
        try:
            data = TimeSeries.read(source, channel, start=start, end=end)
        except Exception as error:
            found_channels = ", ".join(channel_names_in(paths[0], detector)) or "none"
            sys.exit(
                f"{detector}: Could not read {channel} from {source}: {error}\n"
                f"{detector}: Channels in {paths[0]}: {found_channels}. Update channel-dict in "
                f"the config to match."
            )
        rate = data.sample_rate.value
        if rate != GWOSC_SAMPLE_RATE:
            sys.exit(f"{detector}: {source} holds {rate:g} Hz data, expected GWOSC's {GWOSC_SAMPLE_RATE} Hz")
        expected_samples = (end - start) * rate
        if abs(len(data) - expected_samples) > 1:
            sys.exit(f"{detector}: Read {len(data)} samples, expected {expected_samples:g}")
        if not np.all(np.isfinite(data.value)):
            sys.exit(f"{detector}: Data contains NaN or infinite values")
        print(f"{detector}: Read {len(data)} samples of {channel} from {len(paths)} file(s), all finite")


if __name__ == "__main__":
    main()
