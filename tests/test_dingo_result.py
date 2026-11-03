import importlib
import sys
from pathlib import Path


def test_module_imports_and_has_main():
    module = importlib.import_module("dingo_lensing.pipe.dingo_result")
    assert callable(module.main)


def test_merge_writes_combined_result(monkeypatch, tmp_path):
    module = importlib.import_module("dingo_lensing.pipe.dingo_result")
    calls = {}

    class FakeResult:
        def __init__(self, file_name):
            self.file_name = file_name

        @classmethod
        def merge(cls, parts):
            calls["parts"] = [part.file_name for part in parts]
            return cls(file_name="merged")

        def print_summary(self):
            calls["summary"] = True

        def to_file(self, file_name):
            calls["output"] = Path(file_name)

    argv = [
        "dingo_lensing_result",
        "--merge",
        "--outdir",
        str(tmp_path),
        "--label",
        "event_merge",
        "--extension",
        "hdf5",
        "--result",
        "part_0.hdf5",
        "part_1.hdf5",
    ]
    monkeypatch.setattr(module, "LensedGWResult", FakeResult)
    monkeypatch.setattr(sys, "argv", argv)
    module.main()
    assert calls == {
        "parts": ["part_0.hdf5", "part_1.hdf5"],
        "summary": True,
        "output": tmp_path / "event.hdf5",
    }
