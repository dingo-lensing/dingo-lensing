import os
import re
import dingo.gw.dataset

target_srcfile = os.path.join(
    '/'.join(dingo.gw.dataset.__file__.split('/')[:-1]),
    "generate_dataset.py"
)

if os.path.exists(target_srcfile):
    with open(target_srcfile, "r") as f:
        target_src = f.readlines()
else:
    print("FileNotExistError")

# Find out which line to inject the import statement
last_import_idx = None
first_def_idx = None

for i, line in enumerate(target_src):
    if re.match(r'^\s*(import|from)\s+', line):
        last_import_idx = i
    elif re.match(r'^\s*def\s+\w+', line) and first_def_idx is None:
        first_def_idx = i


if last_import_idx is not None:
    insert_idx = last_import_idx + 1
    if first_def_idx is not None and insert_idx > first_def_idx:
        insert_idx = first_def_idx
else:
    insert_idx = first_def_idx if first_def_idx is not None else 0

# NOTE This is just a hacky way of doing it
target_src.insert(insert_idx, "from dingo_lensing.waveform_generator import LensedWaveformGenerator as WaveformGenerator\n")

exec("".join(target_src))