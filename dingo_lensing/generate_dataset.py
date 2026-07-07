import os
import re
import copy
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
target_src.insert(insert_idx + 1, "from dingo_lensing.dev_mode import generate_waveforms_parallel, normalize_dev_mode_settings\n")

settings_load_idx = None
for i, line in enumerate(target_src):
    if "settings = yaml.safe_load(f)" in line:
        settings_load_idx = i
        break

if settings_load_idx is not None:
    target_src.insert(settings_load_idx + 1, "    settings = normalize_dev_mode_settings(settings, settings_file)\n")

exec("".join(target_src))


_original_generate_dataset = generate_dataset


def generate_dataset(settings, num_processes):
    settings = copy.deepcopy(settings)
    waveform_settings = settings.setdefault("waveform_generator", {})
    waveform_settings.setdefault("dev_mode", settings.get("dev_mode", False))
    waveform_settings.setdefault("dev_plot_dir", settings.get("dev_plot_dir", "dev_plots"))
    return _original_generate_dataset(settings, num_processes)


def generate_waveforms_task_func(args, waveform_generator):
    sample_index, row = args
    parameters = row.to_dict()
    parameters["sample_index"] = int(sample_index)
    return waveform_generator.generate_hplus_hcross(parameters)
