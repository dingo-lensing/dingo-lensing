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


def configure_dev_plot_style() -> None:
    if plt is None:
        return

    plt.rcParams.update(
        {
            "font.size": 14,
            "axes.labelsize": 16,
            "axes.titlesize": 16,
            "legend.fontsize": 13,
            "xtick.labelsize": 14,
            "ytick.labelsize": 14,
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "font.family": "serif",
            "mathtext.fontset": "cm",
        }
    )


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
        dev_plot_dir = Path(settings_file).resolve().parent / "dev_plots"
    else:
        dev_plot_dir = Path.cwd() / "dev_plots"

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
    configure_dev_plot_style()

    if output_dir is None:
        output_dir = Path.cwd() / "dev_plots" / "waveform"
    output_dir.mkdir(parents=True, exist_ok=True)

    frequencies = np.asarray(frequencies)
    nonlensed_amplitude = _waveform_amplitude(nonlensed_waveform)
    lensed_amplitude = _waveform_amplitude(lensed_waveform)
    valid = (
        (frequencies > 0)
        & np.isfinite(nonlensed_amplitude)
        & np.isfinite(lensed_amplitude)
        & (nonlensed_amplitude > 0)
        & (lensed_amplitude > 0)
    )
    if not np.any(valid):
        raise ValueError(
            "Cannot plot waveform overlay: lensed and nonlensed waveforms have no "
            "common finite, positive frequency support."
        )
    frequencies = frequencies[valid]
    nonlensed_amplitude = nonlensed_amplitude[valid]
    lensed_amplitude = lensed_amplitude[valid]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.loglog(
        frequencies,
        nonlensed_amplitude,
        label="Nonlensed",
        linewidth=1.4,
    )
    ax.loglog(
        frequencies,
        lensed_amplitude,
        label="Lensed",
        linewidth=1.4,
    )
    if x_min is not None or x_max is not None:
        left = max(x_min if x_min is not None else frequencies[0], frequencies[0])
        right = min(x_max if x_max is not None else frequencies[-1], frequencies[-1])
        if left < right:
            ax.set_xlim(left=left, right=right)
    ax.set_xlabel(r"Frequency $f$ [Hz]")
    ax.set_ylabel(r"Strain amplitude $|\tilde{h}(f)|$")
    ax.set_title(f"Waveform comparison for sample {sample_index}")
    ax.legend(frameon=False)
    ax.grid(True, which="both", alpha=0.3)
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
            fontsize=10,
            family="monospace",
            bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.9},
        )
        fig.tight_layout(rect=(0.0, 0.0, 0.68, 1.0))
    else:
        fig.tight_layout()
    fig.savefig(output_dir / f"waveform_sample_{sample_index:06d}.png")
    plt.close(fig)


def plot_amplification_factor(
    sample_index,
    frequencies: np.ndarray,
    amplification_factor: np.ndarray,
    output_dir: Path | None = None,
    x_min: float | None = None,
    x_max: float | None = None,
) -> None:
    if plt is None:
        raise ImportError("matplotlib is required when dev_mode is enabled.")
    configure_dev_plot_style()

    if output_dir is None:
        output_dir = Path.cwd() / "dev_plots" / "amplification_factor"
    output_dir.mkdir(parents=True, exist_ok=True)

    frequencies = np.asarray(frequencies)
    amplification_factor = np.asarray(amplification_factor)
    amplification_magnitude = np.abs(amplification_factor)
    amplification_phase = np.angle(amplification_factor)
    valid = (
        (frequencies > 0)
        & np.isfinite(amplification_magnitude)
        & np.isfinite(amplification_phase)
        & (amplification_magnitude > 0)
    )
    if not np.any(valid):
        raise ValueError(
            "Cannot plot amplification factor: no finite, positive frequency "
            "support."
        )
    frequencies = frequencies[valid]
    amplification_magnitude = amplification_magnitude[valid]
    amplification_phase = np.unwrap(amplification_phase[valid])

    fig, axes = plt.subplots(2, 1, figsize=(7, 6), sharex=True)
    axes[0].loglog(frequencies, amplification_magnitude, linewidth=1.4)
    axes[0].set_ylabel(r"$|F(f)|$")
    axes[0].set_title(f"Lensing amplification factor for sample {sample_index}")
    axes[0].grid(True, which="both", alpha=0.3)

    axes[1].semilogx(frequencies, amplification_phase, linewidth=1.4)
    axes[1].set_xlabel(r"Frequency $f$ [Hz]")
    axes[1].set_ylabel(r"$\arg F(f)$ [rad]")
    axes[1].grid(True, which="both", alpha=0.3)

    if x_min is not None or x_max is not None:
        left = max(x_min if x_min is not None else frequencies[0], frequencies[0])
        right = min(x_max if x_max is not None else frequencies[-1], frequencies[-1])
        if left < right:
            axes[1].set_xlim(left=left, right=right)

    fig.tight_layout()
    fig.savefig(output_dir / f"amplification_sample_{sample_index:06d}.png")
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
