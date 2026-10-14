"""T4's events: Seven O4a events the LVK followed up as possible strongly lensed images.

Each was in at least one of the 50 event pairs that reached the last tier of the
LVK's O4a strong-lensing search (GWTC-4.0 lensing paper, arXiv:2512.16347,
Figure 3); none favoured lensing. Chosen because both LIGO detectors have GWOSC
data over the whole stretch each analysis reads, their GWTC-4.0 parameters lie
inside the production model's prior, and the LVK did not need to subtract
glitches from their data (Zenodo 16857059 lists the events that did).

Trigger times are to be the LVK's own, from the run configs in the GWTC-4.0
parameter estimation release (Zenodo 16053483), so each segment is the LVK's
segment: lvk_posteriors.py reads them into t4_lvk.json, and the unit tests
compare the two. Until then, all but GW231206_233134's are GWOSC's event times
(rounded to 0.1 s). Standard library only.
"""
from __future__ import annotations

from typing import List, NamedTuple

GWOSC_FILE_DURATION = 4096
DETECTORS = ("H1", "L1")


class Event(NamedTuple):
    letter: str  # T4<letter> analyses this event alone, T4u<letter> with the unlensed model.
    name: str  # GWTC-4.0 name.
    trigger_time: float  # The LVK's trigger time.


# In GPS order, which is also their order in T4m's gps-file.
EVENTS = [
    Event("a", "GW230628_231200", 1372029138.4),
    Event("b", "GW230708_230935", 1372892993.5),
    Event("c", "GW230914_111401", 1378725259.7),
    Event("d", "GW230927_153832", 1379864330.9),
    Event("e", "GW231102_071736", 1382944674.4),
    Event("f", "GW231206_233134", 1385940712.527832),
    Event("g", "GW231206_233901", 1385941159.5),
]


def frame_starts(start: float, end: float) -> List[int]:
    """GPS starts of the 4096 s GWOSC files holding start to end: GWOSC's O4a
    files start at multiples of 4096 s."""
    first = int(start // GWOSC_FILE_DURATION) * GWOSC_FILE_DURATION
    starts = []
    while first < end:
        starts.append(first)
        first += GWOSC_FILE_DURATION
    return starts


def frame_path(detector: str, start: int) -> str:
    """Where a GWOSC O4a 4 kHz frame file goes in the run folder, under GWOSC's own name."""
    return f"gwosc/{detector[0]}-{detector}_GWOSC_O4a_4KHZ_R1-{start}-{GWOSC_FILE_DURATION}.gwf"
