#!/usr/bin/env python3
"""Write T4's configs and GPS file from t4_events.py; see ../test_log.md.

T4 analyses seven O4a events through Juno's production models: Each alone with
the lensed model (T4a to T4g), all seven in one config (T4m, option A), and
each alone with the matching unlensed model (T4ua to T4ug), which plain
dingo_pipe runs. The configs differ only where they must, which the unit tests
check. Run from anywhere; --check compares instead of writing. Standard library
only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

from pipe_config import data_window, segment_start
from t4_events import DETECTORS, EVENTS, Event, frame_path, frame_starts

HERE = Path(__file__).resolve().parent
IMAGE = "osdf:///igwn/cit/staging/kailibryan.doney/containers/dingo-lensing_1d7c4771b4_recipe-ff6622d_cpu.sif"
# Exercise 3's models: A lensed one (two_images_BBH) and its unlensed twin, trained
# on the same noise spectra with the same data settings and priors.
LENSED_MODEL = "/home/chun-lung.chan/dingo_lensing_team/tutorial_20260828/ex3_dingo_lensing_application/models/model_lensed.pt"
UNLENSED_MODEL = "/home/kailibryan.doney/dingo_lensing_tutorial/materials/ex3_dingo_lensing_application/models/model_nonlensed.pt"
# The models' data settings.
DURATION = 8.0
POST_TRIGGER_DURATION = 2.0
PSD_LENGTH = 32
PSD_MAXIMUM_DURATION = 1024.0
CHANNELS = {"H1": "GWOSC-4KHZ_R1_STRAIN", "L1": "GWOSC-4KHZ_R1_STRAIN"}
MULTI_CONFIG = "T4m_all.ini"
GPS_FILE = "T4m_gps.txt"
RULE = "#" * 80


def section(title: str) -> str:
    return f"{RULE}\n## {title}\n{RULE}\n\n"


def header(about: str) -> str:
    return (
        f"{about}#\n"
        "# T4 runs seven O4a events the LVK followed up as possible strongly lensed\n"
        "# images: Each alone through Juno's production lensed model (T4a to T4g), all\n"
        "# seven in one config (T4m), and each through the matching unlensed model\n"
        "# (T4ua to T4ug) for a lensing Bayes factor. Written by make_t4_configs.py from\n"
        "# t4_events.py: Change those and rerun it, rather than editing this file.\n"
    )


def jobs() -> str:
    return section("Job submission") + (
        "local = False\n"
        "accounting = ligo.dev.o4.cbc.explore.test\n"
        "scheduler = condor\n"
        "# CIT's execute nodes no longer see /home, so every job runs inside this image\n"
        "# (see ../container/), and conda-env names the environment inside it.\n"
        f"container = {IMAGE}\n"
        "conda-env = /opt/dingo_env\n"
        "# DINGO sends the image to sampling and importance-sampling jobs (and the\n"
        "# model to sampling jobs) only in osg mode, which also limits those jobs to\n"
        "# remote-pool (IS_GLIDEIN) slots. The extra line replaces every job's\n"
        "# requirements with the image's own, so all jobs stay on CIT's pool.\n"
        "osg = True\n"
        "extra-lines = [requirements = (HAS_SINGULARITY=?=True)]\n"
        "# Sized from T2's measurements with this model (test_log.md): Sampling used 11\n"
        "# to 19 of the 32 cores it asked for, and waited over two hours for a slot that\n"
        "# size; importance sampling used 28 to 30 of 32 cores and at most 3.2 GB; data\n"
        "# generation and plotting used under 0.5 GB. Sampling keeps room for the 4.5 GB\n"
        "# model.\n"
        "request-cpus = 16\n"
        "request-memory = 16\n"
        "request-memory-generation = 8\n"
        "request-cpus-importance-sampling = 32\n"
        "request-memory-importance-sampling = 8\n"
        "# Data-generation and sampling jobs receive the 4.5 GB model and the 0.8 GB\n"
        "# image, and data generation the frame files too (about 1.5 GB in T4m).\n"
        "request-disk = 12\n"
    )


def sampler(model: str) -> str:
    return section("Model and sampler") + (
        f"model = {model}\n"
        "device = cpu\n"
        "num-samples = 50000\n"
        "batch-size = 5000\n"
        "recover-log-prob = false\n"
        "importance-sample = true\n"
    )


def data(events: List[Event]) -> str:
    return (
        "# The models' data settings: 8 s segments ending 2 s after the trigger, both\n"
        "# LIGO detectors, 1024 Hz, 20 to 448 Hz.\n"
        f"duration = {DURATION}\n"
        f"post-trigger-duration = {POST_TRIGGER_DURATION}\n"
        "detectors = [H1, L1]\n"
        "sampling-frequency = 1024\n"
        "minimum-frequency = 20.0\n"
        "maximum-frequency = 448.0\n"
        "reference-frequency = 20.0\n"
        "# GWOSC's O4a 4 kHz frames under GWOSC's own names, which launch.sh fetches.\n"
        "# Listed, not globbed: DINGO sets data-dict before transfer-files, so bilby_pipe\n"
        "# would not expand a glob at build time and no frame would reach the jobs.\n"
        f"data-dict = {frames(events)!r}\n"
        f"channel-dict = {CHANNELS!r}\n"
        "# Each event's PSD comes from its own data: 32 x 8 s just before its segment.\n"
        f"psd-length = {PSD_LENGTH}\n"
        f"psd-maximum-duration = {PSD_MAXIMUM_DURATION:g}\n"
        "psd-method = median\n"
        "psd-fractional-overlap = 0.5\n"
        "tukey-roll-off = 1.0\n"
        "resampling-method = lal\n"
        "ignore-gwpy-data-quality-check = True\n"
    )


def output() -> str:
    return section("Output") + "plot-corner = True\nplot-weights = False\n"


def window(event: Event):
    """GPS (start, end) of the strain the event's data-generation job reads."""
    return data_window(event.trigger_time, DURATION, POST_TRIGGER_DURATION, PSD_LENGTH, PSD_MAXIMUM_DURATION)


def frames(events: List[Event]) -> Dict[str, List[str]]:
    """{detector: [frame paths]} holding the data of every event listed, in time order."""
    starts = sorted({start for event in events for start in frame_starts(*window(event))})
    return {detector: [frame_path(detector, start) for start in starts] for detector in DETECTORS}


def label(event: Event, unlensed: bool = False) -> str:
    return f"T4{'u' if unlensed else ''}{event.letter}"


def single_name(event: Event, unlensed: bool = False) -> str:
    return f"{label(event, unlensed)}_{event.name.lower()}.ini"


def single_config(event: Event, unlensed: bool = False) -> str:
    name = label(event, unlensed)
    if unlensed:
        about = (
            f"# {name}: {event.name} alone, through the unlensed model, for the lensing\n"
            f"# Bayes factor with T4{event.letter}. dingo_pipe builds it: dingo_lensing_pipe\n"
            "# can't run an unlensed model (finding 11).\n"
        )
    else:
        about = f"# {name}: {event.name} alone, through the lensed model.\n"
    events = f"label = {name}\noutdir = {name}\ntrigger-time = {event.trigger_time!r}\n"
    return "\n".join(
        [
            header(about),
            jobs(),
            sampler(UNLENSED_MODEL if unlensed else LENSED_MODEL),
            section("Event and data") + events + data([event]),
            output(),
        ]
    )


def multi_config() -> str:
    about = (
        "# T4m: All seven events in one config (option A), through the lensed model.\n"
        "# No trigger-time, since that would make bilby_pipe ignore the gps-file. Each\n"
        "# data-generation job reads only the frame files overlapping its own event\n"
        "# (dingo_lensing/pipe/multi_event.py).\n"
    )
    events = f"label = T4m\noutdir = T4m\ngps-file = {GPS_FILE}\n"
    return "\n".join(
        [
            header(about),
            jobs(),
            sampler(LENSED_MODEL),
            section("Events and data") + events + data(EVENTS),
            output(),
        ]
    )


def gps_file() -> str:
    lines = [
        "# T4m's events: Segment start times (trigger time - (duration - post-trigger",
        "# duration)), not trigger times. Written by make_t4_configs.py.",
    ]
    lines += [f"# {event.name}: Trigger time {event.trigger_time!r}" for event in EVENTS]
    lines += [repr(segment_start(event.trigger_time, DURATION, POST_TRIGGER_DURATION)) for event in EVENTS]
    return "\n".join(lines) + "\n"


def files() -> Dict[str, str]:
    """{file name: content} of every T4 config and the GPS file."""
    written = {single_name(event): single_config(event) for event in EVENTS}
    written[MULTI_CONFIG] = multi_config()
    written[GPS_FILE] = gps_file()
    written.update({single_name(event, True): single_config(event, True) for event in EVENTS})
    return written


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="Report files that differ instead of writing.")
    args = parser.parse_args(argv)
    stale = []
    for name, content in files().items():
        path = HERE / name
        if args.check:
            if not path.is_file() or path.read_bytes().replace(b"\r\n", b"\n") != content.encode():
                stale.append(name)
        else:
            path.write_bytes(content.encode())
            print(f"Wrote {path}")
    if stale:
        sys.exit(f"Out of date with t4_events.py: {', '.join(stale)}; run make_t4_configs.py")


if __name__ == "__main__":
    main()
