from functools import partial
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    plt = None


def normalize_dev_mode_settings(settings: Dict, settings_file: str | None = None) -> Dict:
    settings = dict(settings)
    waveform_generator_settings = dict(settings.get("waveform_generator", {}))

    if "dev_mode" in settings:
        dev_mode = bool(settings.get("dev_mode", False))
    elif "dev_mode" in waveform_generator_settings:
        dev_mode = bool(waveform_generator_settings["dev_mode"])
    else:
        dev_mode = False

    if "dev_plot_dir" in settings:
        dev_plot_dir = Path(settings["dev_plot_dir"])
    elif "dev_plot_dir" in waveform_generator_settings:
        dev_plot_dir = Path(waveform_generator_settings["dev_plot_dir"])
    elif settings_file is not None:
        dev_plot_dir = Path(settings_file).resolve().parent / "dev_plots" / "waveform"
    else:
        dev_plot_dir = Path.cwd() / "dev_plots" / "waveform"

    waveform_generator_settings["dev_mode"] = dev_mode
    waveform_generator_settings["dev_plot_dir"] = str(dev_plot_dir)
    settings["waveform_generator"] = waveform_generator_settings
    return settings


def generate_waveforms_task_func(
    args: Tuple, waveform_generator
) -> Dict[str, np.ndarray]:
    sample_index, sample = args
    parameters = sample.to_dict()
    parameters["sample_index"] = sample_index
    return waveform_generator.generate_hplus_hcross(parameters)


def generate_waveforms_parallel(
    waveform_generator,
    parameter_samples: pd.DataFrame,
    pool: Pool = None,
) -> Dict[str, np.ndarray]:
    task_func = partial(
        generate_waveforms_task_func, waveform_generator=waveform_generator
    )
    task_data = parameter_samples.iterrows()

    if pool is not None:
        polarizations_list = pool.map(task_func, task_data)
    else:
        polarizations_list = list(map(task_func, task_data))

    return {
        pol: np.stack([wf[pol] for wf in polarizations_list])
        for pol in polarizations_list[0].keys()
    }


def plot_waveform_overlay(
    sample_index,
    frequencies: np.ndarray,
    nonlensed_waveform: Dict[str, np.ndarray],
    lensed_waveform: Dict[str, np.ndarray],
    nonlensed_parameters: Dict[str, float] | None = None,
    lensed_parameters: Dict[str, float] | None = None,
    output_dir: Path | None = None,
    x_min: float | None = None,
    x_max: float | None = None,
) -> None:
    if plt is None:
        raise ImportError("matplotlib is required when dev_mode is enabled.")

    if output_dir is None:
        output_dir = Path.cwd() / "dev_plots" / "waveform"
    output_dir.mkdir(parents=True, exist_ok=True)

    frequencies = np.asarray(frequencies)
    nonlensed_amplitude = _waveform_amplitude(nonlensed_waveform)
    lensed_amplitude = _waveform_amplitude(lensed_waveform)
    valid = frequencies > 0
    frequencies = frequencies[valid]
    nonlensed_amplitude = nonlensed_amplitude[valid]
    lensed_amplitude = lensed_amplitude[valid]

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(frequencies, nonlensed_amplitude, label="nonlensed", linewidth=1.5)
    ax.plot(frequencies, lensed_amplitude, label="lensed", linewidth=1.5)
    ax.set_xscale("log")
    ax.set_yscale("log")
    if x_min is not None or x_max is not None:
        ax.set_xlim(left=x_min, right=x_max)
    ax.set_xlabel("Frequency [Hz]")
    ax.set_ylabel("Strain amplitude")
    ax.set_title(f"Waveform comparison for sample {sample_index}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    parameter_text = _format_parameter_text(
        nonlensed_parameters=nonlensed_parameters,
        lensed_parameters=lensed_parameters,
    )
    if parameter_text:
        fig.text(
            0.72,
            0.5,
            parameter_text,
            va="center",
            ha="left",
            fontsize=9,
            family="monospace",
            bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.9},
        )
        fig.tight_layout(rect=(0.0, 0.0, 0.7, 1.0))
    else:
        fig.tight_layout()
    fig.savefig(output_dir / f"waveform_sample_{sample_index:06d}.png", dpi=150)
    plt.close(fig)


def _waveform_amplitude(waveform: Dict[str, np.ndarray]) -> np.ndarray:
    h_plus = np.abs(np.asarray(waveform["h_plus"]))
    h_cross = np.abs(np.asarray(waveform["h_cross"]))
    return np.sqrt(h_plus**2 + h_cross**2)


def _format_parameter_text(
    nonlensed_parameters: Dict[str, float] | None,
    lensed_parameters: Dict[str, float] | None,
) -> str:
    sections = []
    if nonlensed_parameters:
        sections.append(
            "Nonlensed parameters\n" + _format_parameter_lines(nonlensed_parameters)
        )
    if lensed_parameters:
        sections.append(
            "Lensed parameters\n" + _format_parameter_lines(lensed_parameters)
        )
    return "\n\n".join(section for section in sections if section.strip())


def _format_parameter_lines(parameters: Dict[str, float]) -> str:
    lines = []
    for key, value in parameters.items():
        if value is None:
            continue
        if isinstance(value, (float, np.floating)):
            formatted_value = f"{float(value):.6g}"
        else:
            formatted_value = str(value)
        lines.append(f"{key}: {formatted_value}")
    return "\n".join(lines)
