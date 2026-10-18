"""Every installed command must import with the supported DINGO release."""

from importlib import import_module
from importlib.metadata import distribution, version


def test_cli_imports():
    assert version("dingo-gw") == "0.10.3"
    for entry in distribution("dingo_lensing").entry_points:
        if entry.group == "console_scripts":
            module, symbol = entry.value.split(":")
            assert callable(getattr(import_module(module), symbol))
