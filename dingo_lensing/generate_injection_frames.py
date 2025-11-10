import os
import argparse
import textwrap
import yaml
import numpy as np
import pandas as pd
from gwpy.timeseries import TimeSeries
import json
import importlib

from bilby.gw.waveform_generator import LALCBCWaveformGenerator
from bilby.gw.conversion import convert_to_lal_binary_black_hole_parameters
from .utils.inj_utils import inject_signal_gaussian_noise
from .utils.config_utils import (
    create_bilby_config_file,
    create_dingo_config_file
)

def resolve_callable(obj):
    if isinstance(obj, str) and "." in obj:
        mod, fn = obj.rsplit(".", 1)
        return getattr(importlib.import_module(mod), fn)
    return obj

def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """\
        Generate frame files based on a settings file.
        """
        ),
    )

    parser.add_argument(
        "--settings_file",
        type=str,
        default=None,
        help="Path to a settings file ",
    )
    parser.add_argument("--verbose", action="store_true")

    return parser.parse_args()

def generate_frame_file(args):
    """
    Creates and saves an frame file
    """
    
    settings_file = (
        args.settings_file
        if args.settings_file is not None
        else join(args.data_dir, "settings.yaml")
    )
    with open(settings_file, "r") as f:
        settings = yaml.safe_load(f)

    df_inj = pd.read_csv(settings['injection']['injection_file'])
    
    for index, row in df_inj.iterrows():
        os.makedirs(f"{settings['output_dir']}_{index}/frame_file_plot", exist_ok=True)
        os.makedirs(f"{settings['output_dir']}_{index}/gwf_files", exist_ok=True)
        output_dir = f"{settings['output_dir']}_{index}"

        params = row.to_dict()
        if "lensing_delta_t" in params:
            params["Delta_t"] = params.pop("lensing_delta_t")
            params["Delta_phase"] = np.pi/2
        params["geocent_time"] = settings["waveform_generator"]["start_time"]
        signal_start_time = settings["waveform_generator"]["start_time"] + settings["waveform_generator"]["post_trigger"] - (settings["waveform_generator"]["duration"]/2.)
        waveform_generator = LALCBCWaveformGenerator(frequency_domain_source_model=resolve_callable(settings["waveform_generator"]["frequency_domain_source_model"]),
                                                                    duration=settings["waveform_generator"]["duration"],
                                                                    parameter_conversion=convert_to_lal_binary_black_hole_parameters,
                                                                    start_time=signal_start_time,
                                                                    sampling_frequency=settings["waveform_generator"]["sampling_frequency"],
                                                                    waveform_arguments=settings["waveform_generator"]["waveform_arguments"])

        for ifo, psd_path in settings["injection"]["psd_dict"].items():
            det = inject_signal_gaussian_noise(ifo,
                                                        params,
                                                        output_dir,
                                                        waveform_generator=waveform_generator,
                                                        sampling_frequency=settings["waveform_generator"]["sampling_frequency"], 
                                                        duration=settings["waveform_generator"]["duration"], 
                                                        psd_file=psd_path, 
                                                        plot=(ifo == "H1"), 
                                                        i=index)

            det_gwpy = TimeSeries(det.time_domain_strain,
                                t0=det.time_array[0],
                                sample_rate=int(settings["waveform_generator"]["sampling_frequency"]),
                                name=f"{ifo}:injection")
            det_gwpy.write(f"{output_dir}/gwf_files/{ifo}.gwf")
            ts = TimeSeries.read(f"{output_dir}/gwf_files/{ifo}.gwf", 
                                f"{ifo}:injection", 
                                format="gwf.lalframe")
        
        with open(f"{output_dir}/params.json", "w") as f:
            json.dump(params, f, indent=4)

        if settings["config_files"]["generate_config"]:
            create_dingo_config_file(settings=settings,
                                    ifo_list=list(settings["injection"]["psd_dict"].keys()),
                                    output_dir=output_dir,
                                    i=index)
            create_bilby_config_file(settings=settings,
                                    ifo_list=list(settings["injection"]["psd_dict"].keys()),
                                    output_dir=output_dir,
                                    i=index)


def main() -> None:
    args = parse_args()
    generate_frame_file(args)

if __name__ == "__main__":
    main()