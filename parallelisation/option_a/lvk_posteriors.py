#!/usr/bin/env python3
"""Summarise the LVK's GWTC-4.0 analyses of T4's events, and check them against the models' prior.

Reads each event's file from the GWTC-4.0 parameter estimation release (Zenodo
16053483, public) and writes t4_lvk.json, which the T4 configs and analysis
use. From the LVK's IMRPhenomXPHM-SpinTaylor analysis (the waveform closest to
the models' IMRPhenomXPHM), per event: The trigger time and data settings the
LVK used (detectors, channels, frequency range, segment), the 5th, 50th and
95th percentiles of the parameters T4 compares, and the share of the LVK's
samples inside the production models' prior. Needs numpy, and h5py to read the
release files. On the cluster, in dingo_env (about 1.4 GB to download; nohup
keeps it going if the connection drops, and rerunning resumes partial files):

    nohup python -u lvk_posteriors.py ~/dingo-lensing-runs/gwtc4_pe --download > lvk.log 2>&1 &
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Dict, List

from t4_events import EVENTS

HERE = Path(__file__).resolve().parent
LABEL = "C00:IMRPhenomXPHM-SpinTaylor"
RELEASE_FILE = "IGWN-GWTC4p0-38214bd95_724-{name}-combined_PEDataRelease.hdf5"
# The release's latest version (2026-05-22): Each file's size in bytes and md5 there.
RELEASE_URL = "https://zenodo.org/records/17602505/files/{file}?download=1"
RELEASE_FILES = {
    "GW230628_231200": (159650500, "34e6cd5a50ef8908a3a3c1ee3e1c6260"),
    "GW230708_230935": (205603600, "96e15b4b9793e73b76e4a43708833dfb"),
    "GW230914_111401": (310927088, "51230a054c17048c9bed334f77e01645"),
    "GW230927_153832": (207474404, "802c1c28b6258427f7f311a870d0cf1c"),
    "GW231102_071736": (210699480, "68e9ff2eb83aa971bdf25311d22b2754"),
    "GW231206_233134": (131615660, "0c77f39e47b8a67bcc86ee7290fe4ec9"),
    "GW231206_233901": (189649148, "326d94a167fea38582079d0547aac8a1"),
}
ATTEMPTS = 30
TIMEOUT = 60  # Seconds without data before a transfer counts as dropped.
PROGRESS_EVERY = 30  # Seconds between progress lines.
# The production models' prior (model_info/lensed_model_ls.txt): Uniform in
# component masses for chirp mass (detector frame) and mass ratio, uniform in
# distance, spins up to 0.99. The time prior is relative to the trigger time.
PRIOR = {
    "chirp_mass": (10.0, 180.0),
    "mass_ratio": (0.125, 1.0),
    "luminosity_distance": (500.0, 10000.0),
    "a_1": (0.0, 0.99),
    "a_2": (0.0, 0.99),
}
TIME_PRIOR = 0.1
QUANTILES = (0.05, 0.5, 0.95)
COMPARED = ("chirp_mass", "mass_ratio", "luminosity_distance", "chi_eff", "network_matched_filter_snr")
# Config entries kept as the LVK wrote them, and those read per detector.
CONFIG_VALUES = ("trigger-time", "duration", "post-trigger-duration", "sampling-frequency", "detectors")
CONFIG_DICTS = ("channel-dict", "frame-type-dict", "minimum-frequency", "maximum-frequency")


def parse_loose_dict(raw: str) -> Dict[str, object]:
    """Parse bilby_pipe's '{ H1:40,L1:30, waveform: 13.33 }' form (numbers where possible).

    A bare value (no braces) is returned as {"all": value}.
    """
    text = raw.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return {"all": number_or_text(text)}
    entries = {}
    for item in text[1:-1].split(","):
        if not item.strip():
            continue
        key, separator, value = item.partition(":")
        if not separator:
            raise ValueError(f"Expected 'key:value' in {raw!r}, got {item!r}")
        entries[key.strip()] = number_or_text(value.strip())
    return entries


def number_or_text(value: str):
    try:
        return float(value)
    except ValueError:
        return value


def fraction_inside(values, low: float, high: float) -> float:
    import numpy as np

    values = np.asarray(values, dtype=float)
    return float(np.mean((values >= low) & (values <= high)))


def summarise_samples(samples: Dict[str, "object"], trigger_time: float) -> dict:
    """Percentiles of the compared parameters and the shares inside the models' prior."""
    import numpy as np

    quantiles = {
        name: [float(q) for q in np.quantile(np.asarray(samples[name], dtype=float), QUANTILES)]
        for name in COMPARED
        if name in samples
    }
    inside = {name: fraction_inside(samples[name], *bounds) for name, bounds in PRIOR.items()}
    offsets = np.asarray(samples["geocent_time"], dtype=float) - trigger_time
    every = np.ones(len(offsets), dtype=bool)
    for name, (low, high) in PRIOR.items():
        values = np.asarray(samples[name], dtype=float)
        every &= (values >= low) & (values <= high)
    every &= np.abs(offsets) <= TIME_PRIOR
    return {
        "samples": int(len(offsets)),
        "quantiles": quantiles,
        "geocent_time_offset": [float(q) for q in np.quantile(offsets, QUANTILES)],
        "inside_prior": {**inside, "geocent_time": float(np.mean(np.abs(offsets) <= TIME_PRIOR)), "all": float(np.mean(every))},
    }


def read_release_file(path: Path) -> dict:
    """The XPHM-SpinTaylor analysis's config entries and posterior samples."""
    import h5py
    import numpy as np

    with h5py.File(path, "r") as file:
        analysis = file[LABEL]
        config = analysis["config_file"]["config"]

        def text(key):
            value = config[key][()]
            value = value[0] if np.ndim(value) else value
            return value.decode() if isinstance(value, bytes) else str(value)

        settings = {key: text(key) for key in (*CONFIG_VALUES, *CONFIG_DICTS) if key in config}
        records = analysis["posterior_samples"][()]
        names = set(records.dtype.names)
        wanted = {*COMPARED, *PRIOR, "geocent_time"}
        samples = {name: np.asarray(records[name], dtype=float) for name in wanted if name in names}
        missing = sorted(wanted - names - {"chi_eff", "network_matched_filter_snr"})
        if missing:
            raise ValueError(f"{path.name}: No {', '.join(missing)} in {LABEL}'s samples")
    return {"settings": settings, "samples": samples}


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(name: str, directory: Path, progress: Dict[str, int] = None) -> str:
    """Fetch one event's release file into directory until it matches Zenodo's size and md5.

    Zenodo drops long transfers, so each attempt resumes where the last stopped
    (an HTTP Range request); a file as long as Zenodo's but with the wrong md5,
    or longer, is fetched again from the start. Records the bytes on disk in
    progress[name]. Returns a line for the log.
    """
    size, checksum = RELEASE_FILES[name]
    path = directory / RELEASE_FILE.format(name=name)
    url = RELEASE_URL.format(file=path.name)
    progress = {} if progress is None else progress
    for _ in range(ATTEMPTS):
        have = path.stat().st_size if path.is_file() else 0
        progress[name] = have
        if have == size and md5(path) == checksum:
            return f"{name}: Done, {size / 1e6:.1f} MB, md5 matches Zenodo's"
        if have >= size:
            path.unlink()
            have = progress[name] = 0
        request = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                # A server that ignores the range sends the whole file again.
                mode = "ab" if have and response.status == 206 else "wb"
                written = have if mode == "ab" else 0
                with open(path, mode) as handle:
                    for block in iter(lambda: response.read(1 << 20), b""):
                        handle.write(block)
                        written += len(block)
                        progress[name] = written
        except (OSError, http.client.HTTPException):
            time.sleep(5)  # A dropped connection, a timeout or a server error: Resume next time.
    raise RuntimeError(f"{name}: No copy with Zenodo's size and md5 after {ATTEMPTS} attempts ({url})")


def download_all(directory: Path) -> None:
    """Fetch every T4 event's release file, all at once, with a progress line every PROGRESS_EVERY s.

    Each file downloads in a background thread, so Ctrl-C stops them all at
    once; partial files stay, and the next run resumes them.
    """
    directory.mkdir(parents=True, exist_ok=True)
    total = sum(RELEASE_FILES[event.name][0] for event in EVENTS)
    # Every key exists before the threads start, so they only change values.
    progress: Dict[str, int] = {event.name: 0 for event in EVENTS}
    results: Dict[str, object] = {}
    lock = threading.Lock()

    def work(name):
        try:
            outcome = download(name, directory, progress)
        except Exception as error:  # Reported below, with the other files' outcomes.
            outcome = error
        with lock:
            results[name] = outcome

    print(
        f"Downloading {len(EVENTS)} files ({total / 1e9:.2f} GB) from Zenodo into {directory}; a line every "
        f"{PROGRESS_EVERY} s. Ctrl-C stops; running again resumes.",
        flush=True,
    )
    threads = [threading.Thread(target=work, args=(event.name,), daemon=True) for event in EVENTS]
    for thread in threads:
        thread.start()
    reported = set()
    next_line = time.monotonic() + PROGRESS_EVERY
    try:
        while True:
            alive = any(thread.is_alive() for thread in threads)
            with lock:
                finished = dict(results)
            for name in sorted(set(finished) - reported):
                print(f"  {finished[name]}", flush=True)
                reported.add(name)
            if not alive:
                break
            if time.monotonic() >= next_line:
                done = sum(progress.values())
                print(
                    f"{time.strftime('%H:%M:%S')}  {done / 1e6:.0f} of {total / 1e6:.0f} MB "
                    f"({100 * done / total:.0f}%), {len(finished)} of {len(EVENTS)} files finished",
                    flush=True,
                )
                next_line += PROGRESS_EVERY
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit("Stopped. The partial files stay; running again resumes them.")
    failed = [f"{name}: {result}" for name, result in sorted(results.items()) if isinstance(result, Exception)]
    if failed:
        sys.exit("\n".join(failed))


def summarise_event(path: Path) -> dict:
    content = read_release_file(path)
    settings = content["settings"]
    trigger_time = float(settings["trigger-time"])
    summary = {
        "file": path.name,
        "md5": md5(path),
        "analysis": LABEL,
        "trigger_time": trigger_time,
        "trigger_time_text": settings["trigger-time"],
        "detectors": re.findall(r"[A-Z][0-9]", settings.get("detectors", "")),
        "duration": float(settings["duration"]),
        "post_trigger_duration": float(settings["post-trigger-duration"]),
        "sampling_frequency": float(settings["sampling-frequency"]),
    }
    for key in CONFIG_DICTS:
        if key in settings:
            summary[key.replace("-", "_")] = parse_loose_dict(settings[key])
    summary.update(summarise_samples(content["samples"], trigger_time))
    return summary


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path, help="Folder holding the release files.")
    parser.add_argument("--output", type=Path, default=HERE / "t4_lvk.json")
    parser.add_argument(
        "--download", action="store_true", help="First fetch the release files into the folder (about 1.4 GB)."
    )
    args = parser.parse_args(argv)
    if args.download:
        download_all(args.directory)
    report = {}
    failed: List[str] = []
    for event in EVENTS:
        path = args.directory / RELEASE_FILE.format(name=event.name)
        if not path.is_file():
            failed.append(f"{event.name}: {path} not found")
            continue
        summary = summarise_event(path)
        report[event.name] = summary
        inside = summary["inside_prior"]["all"]
        print(
            f"{event.name}: LVK trigger {summary['trigger_time_text']}, detectors {summary['detectors']}, "
            f"f_min {summary.get('minimum_frequency')}, {100 * inside:.2f}% of samples inside the models' prior",
            flush=True,
        )
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Written: {args.output}", flush=True)
    if failed:
        sys.exit("\n".join(failed))


if __name__ == "__main__":
    main()
