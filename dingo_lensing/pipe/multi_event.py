"""Helpers that make one config safe for several events (listed with --gps-file).

Standard library only, so they can be tested without DINGO.
"""


def psd_file_name(label, detector):
    """Name of a data-generation job's PSD text file: Its label, as for its event data file."""
    return "_".join([label, f"{detector}_psd.txt"])
