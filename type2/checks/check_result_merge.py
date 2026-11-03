import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

import dingo_lensing
from dingo_lensing.result import LensedGWResult

parser = argparse.ArgumentParser()
parser.add_argument("result")
parser.add_argument("--parts", type=int, default=4)
args = parser.parse_args()
print(f"dingo_lensing from {dingo_lensing.__file__}")

result = LensedGWResult(file_name=args.result)
parts = result.split(args.parts)
direct = LensedGWResult.merge(parts)

with tempfile.TemporaryDirectory() as tmp:
    files = []
    for i, part in enumerate(parts):
        file_name = str(Path(tmp) / f"part_{i}.hdf5")
        part.to_file(file_name)
        files.append(file_name)
    command = [sys.executable, "-m", "dingo_lensing.pipe.dingo_result", "--merge", "--outdir", tmp, "--label", "merged_merge", "--extension", "hdf5", "--result", *files]
    subprocess.run(command, check=True)
    merged = LensedGWResult(file_name=str(Path(tmp) / "merged.hdf5"))

pd.testing.assert_frame_equal(merged.samples, direct.samples)
pd.testing.assert_frame_equal(merged.samples, result.samples)
assert np.isclose(merged.log_evidence, direct.log_evidence, rtol=0, atol=1e-10)
assert np.isclose(merged.log_evidence, result.log_evidence, rtol=0, atol=1e-10)
print(f"merge ok: {len(merged.samples)} samples, log evidence {merged.log_evidence:.6f}")
