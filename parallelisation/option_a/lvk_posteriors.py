#!/usr/bin/env python3
"""Summarise the LVK's GWTC-4.0 analyses of T4's events, and check them against the models' prior.

Reads each event's file from the GWTC-4.0 parameter estimation release (Zenodo
16053483, public) and writes t4_lvk.json, which the T4 configs and analysis
use. From the LVK's IMRPhenomXPHM-SpinTaylor analysis (the waveform closest to
the models' IMRPhenomXPHM), per event: The trigger time and data settings the
LVK used (detectors, channels, frequency range, segment), the 5th, 50th and
95th percentiles of the parameters T4 compares, and the share of the LVK's
samples inside the production models' prior. Needs numpy, and h5py to read the
release files. On the cluster, in dingo_env (about 1.4 GB to download):

    python lvk_posteriors.py ~/dingo-lensing-runs/gwtc4_pe --download
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List

from t4_events import EVENTS

HERE = Path(__file__).resolve().parent
LABEL = "C00:IMRPhenomXPHM-SpinTaylor"
RELEASE_FILE = "IGWN-GWTC4p0-38214bd95_724-{name}-combined_PEDataRelease.hdf5"
# The release's latest version (2026-05-22) and each file's md5 there.
RELEASE_URL = "https://zenodo.org/records/17602505/files/{file}?download=1"
RELEASE_MD5 = {
    "GW230628_231200": "34e6cd5a50ef8908a3a3c1ee3e1c6260",
    "GW230708_230935": "96e15b4b9793e73b76e4a43708833dfb",
    "GW230914_111401": "51230a054c17048c9bed334f77e01645",
    "GW230927_153832": "802c1c28b6258427f7f311a870d0cf1c",
    "GW231102_071736": "68e9ff2eb83aa971bdf25311d22b2754",
    "GW231206_233134": "0c77f39e47b8a67bcc86ee7290fe4ec9",
    "GW231206_233901": "326d94a167fea38582079d0547aac8a1",
}
ATTEMPTS = 30
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


def download(name: str, directory: Path) -> str:
    """Fetch one event's release file into directory until its md5 matches Zenodo's.

    Zenodo drops long transfers, so each attempt resumes where the last stopped
    (an HTTP Range request); a file that fails the md5 check is fetched again
    from the start. Returns a line for the log.
    """
    path = directory / RELEASE_FILE.format(name=name)
    url = RELEASE_URL.format(file=path.name)
    for _ in range(ATTEMPTS):
        if path.is_file() and md5(path) == RELEASE_MD5[name]:
            return f"{name}: {path} ({path.stat().st_size / 1e6:.1f} MB, md5 matches Zenodo's)"
        start = path.stat().st_size if path.is_file() else 0
        request = urllib.request.Request(url, headers={"Range": f"bytes={start}-"} if start else {})
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                # A server that ignores the range sends the whole file again.
                mode = "ab" if start and response.status == 206 else "wb"
                with open(path, mode) as handle:
                    for block in iter(lambda: response.read(1 << 20), b""):
                        handle.write(block)
        except urllib.error.HTTPError as error:
            if error.code == 416:
                path.unlink()  # As long as Zenodo's file or longer, yet wrong: Start again.
            time.sleep(5)
            continue
        except (OSError, http.client.HTTPException):
            time.sleep(5)  # A dropped connection or a timeout: Resume next time.
            continue
        if md5(path) != RELEASE_MD5[name]:
            path.unlink()  # Complete but wrong: Fetch it again from the start.
    raise RuntimeError(f"{name}: No copy with Zenodo's md5 after {ATTEMPTS} attempts ({url})")


def download_all(directory: Path) -> None:
    """Fetch every T4 event's release file, several at once."""
    directory.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=len(EVENTS)) as pool:
        for line in pool.map(lambda event: download(event.name, directory), EVENTS):
            print(line)


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
            f"f_min {summary.get('minimum_frequency')}, {100 * inside:.2f}% of samples inside the models' prior"
        )
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Written: {args.output}")
    if failed:
        sys.exit("\n".join(failed))


if __name__ == "__main__":
    main()
