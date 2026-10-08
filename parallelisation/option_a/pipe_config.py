"""Small helpers for reading dingo_pipe configs and GPS files.

Shared by the option A scripts and their unit tests, so the arithmetic behind
the desk-check traps (segment start times in --gps-file, how much data a PSD
estimate needs) lives in one tested place. Standard library only: It has to
run both on the cluster and on a machine without DINGO installed.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Tuple


def read_pipe_ini(path) -> Dict[str, str]:
    """Read a dingo_pipe ini file into {key: raw value string}.

    These files are flat "key = value" lines with '#' comment lines; any
    '[section]' header is ignored. Keys are normalised to hyphens, since
    bilby_pipe accepts both "trigger-time" and "trigger_time". A key given
    twice is an error rather than letting one value silently win.
    """
    entries = {}
    for number, line in enumerate(Path(path).read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "[")):
            continue
        if "=" not in stripped:
            raise ValueError(f"{path}:{number}: Expected 'key = value', got {line!r}")
        key, _, value = stripped.partition("=")
        key = key.strip().replace("_", "-")
        if key in entries:
            raise ValueError(f"{path}:{number}: Duplicate key {key!r}")
        entries[key] = value.strip()
    return entries


def is_unset(entries: Dict[str, str], key: str) -> bool:
    """True if a key is absent or given as None, as bilby_pipe treats both."""
    return entries.get(key, "None").strip() in ("None", "none", "")


def parse_dict(raw: str) -> dict:
    """Parse a dict-valued entry such as data-dict or channel-dict."""
    value = ast.literal_eval(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a dict, got {raw!r}")
    return value


def read_gps_file(path) -> List[float]:
    """Read a --gps-file the way bilby_pipe does.

    bilby_pipe uses np.loadtxt(..., delimiter=",") and keeps the first
    column, skipping '#' comments.
    """
    times = []
    for line in Path(path).read_text().splitlines():
        content = line.split("#", 1)[0].strip()
        if content:
            times.append(float(content.split(",")[0]))
    return times


def segment_start(
    trigger_time: float, duration: float, post_trigger_duration: float
) -> float:
    """GPS start of an event's analysis segment: What --gps-file must list."""
    return trigger_time + post_trigger_duration - duration


def trigger_time_from_start(
    start: float, duration: float, post_trigger_duration: float
) -> float:
    """Inverse of segment_start, as DINGO's get_trigger_time_list computes it."""
    return start + duration - post_trigger_duration


def data_window(
    trigger_time: float,
    duration: float,
    post_trigger_duration: float,
    psd_length: int,
    psd_maximum_duration: float = 1024.0,
) -> Tuple[float, float]:
    """GPS (start, end) of all the strain one event needs without a psd-dict.

    bilby_pipe estimates the PSD from min(psd_length * duration,
    psd_maximum_duration) seconds immediately before the segment (its default
    psd-start-time), so the data must cover that stretch plus the segment.
    """
    start = segment_start(trigger_time, duration, post_trigger_duration)
    psd_duration = min(psd_length * duration, psd_maximum_duration)
    return start - psd_duration, start + duration


def needed_window(entries: Dict[str, str], detector: str) -> Tuple[float, float]:
    """GPS (start, end) of the strain a single-event config's job reads for a detector.

    bilby_pipe's data generation reads the analysis segment, plus the PSD
    stretch before it unless psd-dict gives that detector's PSD as a file.
    """
    if is_unset(entries, "trigger-time"):
        raise ValueError("Needs a single-event config, with a trigger-time")
    if not is_unset(entries, "psd-start-time"):
        raise ValueError("A custom psd-start-time is not supported")
    trigger_time = float(entries["trigger-time"])
    duration = float(entries["duration"])
    post_trigger_duration = float(entries["post-trigger-duration"])
    psd_files = {} if is_unset(entries, "psd-dict") else parse_dict(entries["psd-dict"])
    if psd_files.get(detector) not in (None, "None"):
        start = segment_start(trigger_time, duration, post_trigger_duration)
        return start, start + duration
    return data_window(
        trigger_time,
        duration,
        post_trigger_duration,
        int(entries["psd-length"]),
        float(entries.get("psd-maximum-duration", "1024")),
    )
