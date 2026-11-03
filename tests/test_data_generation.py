import dingo.pipe.data_generation as dingo_data_generation
import pytest
from dingo.gw.injection import Injection
from dingo.pipe.data_generation import DataGenerationInput

from dingo_lensing.injection import LensedInjection
from dingo_lensing.pipe.data_generation import LensedDataGenerationInput


def test_inject_dingo_signal_uses_lensed_injection(monkeypatch):
    used = []

    def inject(self, args):
        used.append(dingo_data_generation.Injection)

    monkeypatch.setattr(DataGenerationInput, "_inject_dingo_signal", inject)
    data = object.__new__(LensedDataGenerationInput)
    data._inject_dingo_signal(None)
    assert used == [LensedInjection]
    assert dingo_data_generation.Injection is Injection


def test_injection_class_restored_after_error(monkeypatch):
    def inject(self, args):
        raise RuntimeError("injection failed")

    monkeypatch.setattr(DataGenerationInput, "_inject_dingo_signal", inject)
    data = object.__new__(LensedDataGenerationInput)
    with pytest.raises(RuntimeError):
        data._inject_dingo_signal(None)
    assert dingo_data_generation.Injection is Injection
