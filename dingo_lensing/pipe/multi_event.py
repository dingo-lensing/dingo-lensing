"""Helpers that make one config safe for several events (listed with --gps-file).

Standard library only, so they can be tested without DINGO.
"""
import os
import re

# Frame file names in the standard <observatory>-<tag>-<GPS start>-<duration>.gwf
# form (LIGO-T010150), e.g. H-H1_LOSC_4_V1-1126256640-4096.gwf.
FRAME_NAME = re.compile(
    r"^(?P<observatory>[A-Za-z0-9]+)-(?P<tag>.+)-(?P<start>\d+(?:\.\d+)?)-(?P<duration>\d+(?:\.\d+)?)\.gwf$"
)


def psd_file_name(label, detector):
    """Name of a data-generation job's PSD text file: Its label, as for its event data file."""
    return "_".join([label, f"{detector}_psd.txt"])


def frame_span(path):
    """(GPS start, GPS end) of a frame file from its name, or None if the name
    is not in the standard form."""
    match = FRAME_NAME.match(os.path.basename(path))
    if match is None:
        return None
    start = float(match.group("start"))
    return start, start + float(match.group("duration"))


def frames_overlapping(paths, start_time, end_time):
    """The frame files whose time span overlaps [start_time, end_time).

    If any name is not in the standard form, the time spans are unknown, so
    every file is returned, as before.
    """
    spans = [frame_span(path) for path in paths]
    if any(span is None for span in spans):
        return list(paths)
    return [path for path, (start, end) in zip(paths, spans) if start < end_time and end > start_time]
