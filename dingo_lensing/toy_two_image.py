"""Small conditional two-image GW example using the standard DINGO pipeline.

Only lens magnification and delay are inferred. Source parameters, phase,
sky position and noise spectrum are fixed. This demonstrates execution,
not production-quality inference or posterior calibration.
"""

import argparse
import json
from copy import deepcopy
from pathlib import Path

import bilby
import numpy as np
import torch
import yaml
from bilby.gw.detector import InterferometerList
from dingo.core.posterior_models.build_model import build_model_from_kwargs
from dingo.gw.domains import build_domain
from dingo.gw.inference.sampler import GWComposedSampler
from dingo.gw.noise.asd_dataset import ASDDataset
from dingo.gw.training.train_pipeline import run_training
from scipy.special import logsumexp

from .generate_dataset import generate_dataset
from .injection import LensedInjection
from .result import LensedGWResult

PARAMETERS = ["mu_rel", "lensing_delta_t"]


def seed_everything(seed, threads=4):
    """Seed simulator and network RNGs and bound local CPU thread use."""
    np.random.seed(seed)
    bilby.core.utils.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(threads)


def read_config(path):
    """Read the example settings without evaluating Python expressions."""
    with open(path) as stream:
        return yaml.safe_load(stream)


def write_yaml(path, value):
    """Write human-readable settings using ordinary portable YAML values."""
    Path(path).write_text(yaml.safe_dump(value, sort_keys=False))


def dataset_settings(config):
    """Build the standard DINGO waveform configuration with lens priors."""
    intrinsic = dict(config["source"])
    intrinsic.update(
        luminosity_distance=100.0,
        geocent_time=0.0,
        Delta_phase=float(np.pi / 2),
    )
    for name, bounds in config["prior"].items():
        intrinsic[name] = (
            f"bilby.core.prior.Uniform(minimum={bounds[0]}, "
            f"maximum={bounds[1]}, name='{name}')"
        )
    return {
        "domain": config["domain"],
        "waveform_generator": {
            "approximant": "IMRPhenomD",
            "f_ref": 20.0,
            "lens_model_code": "modwaveforms",
            "amplification_factor_function": "two_images_BBH",
        },
        "intrinsic_prior": intrinsic,
        "num_samples": config["num_samples"],
    }


def make_asds(domain, detectors):
    """Use Bilby's bundled detector design PSDs; no external data download."""
    frequencies = domain.sample_frequencies
    asds = {}
    for ifo in InterferometerList(detectors):
        asd = ifo.power_spectral_density.get_amplitude_spectral_density_array(
            frequencies
        )
        # The likelihood and transforms ignore frequencies below f_min.
        asd = np.where(frequencies < domain.f_min, 1.0, asd)
        if not np.all(np.isfinite(asd)) or np.any(asd <= 0):
            raise ValueError(f"Invalid design ASD for {ifo.name}.")
        asds[ifo.name] = asd
    return asds


def prepare(config, outdir):
    """Generate full-resolution training waveforms and a fixed ASD dataset."""
    outdir = Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    if (outdir / "train_settings.yaml").exists():
        raise FileExistsError("Use a fresh output directory for new data.")
    seed_everything(config["seed"], config["threads"])
    settings = dataset_settings(config)
    domain = build_domain(settings["domain"])
    asds = make_asds(domain, config["detectors"])
    extrinsic = dict(config["extrinsic"])
    extrinsic.update(geocent_time=0.0, luminosity_distance=100.0)
    data = {
        "waveform_dataset_path": str(outdir / "waveforms.hdf5"),
        "train_fraction": 0.9,
        "detectors": config["detectors"],
        "extrinsic_prior": extrinsic,
        "ref_time": config["ref_time"],
        "inference_parameters": PARAMETERS,
    }
    metadata = {"dataset_settings": settings, "train_settings": {"data": data}}
    injection = LensedInjection.from_posterior_model_metadata(metadata)
    injection.asd = asds
    theta = {
        **config["source"],
        **extrinsic,
        "Delta_phase": float(np.pi / 2),
        "mu_rel": 0.0,
        "lensing_delta_t": 0.0,
    }
    signal = injection.signal(theta)["waveform"]
    snr = np.sqrt(
        sum(
            np.sum(np.abs(h / asds[ifo] / domain.noise_std) ** 2)
            for ifo, h in signal.items()
        )
    )
    extrinsic["luminosity_distance"] = float(
        100.0 * snr / config["unlensed_snr"]
    )
    asd_path = outdir / "asds.hdf5"
    ASDDataset(
        dictionary={
            "settings": {"domain_dict": domain.domain_dict},
            "asds": {k: v[None, :] for k, v in asds.items()},
            "gps_times": {k: np.array([config["ref_time"]]) for k in asds},
        }
    ).to_file(asd_path)
    waveforms = generate_dataset(settings)
    for key, value in waveforms.polarizations.items():
        waveforms.polarizations[key] = value.astype(np.complex64)
    waveforms.to_file(outdir / "waveforms.hdf5")
    stage = {
        "epochs": config["epochs"],
        "asd_dataset_path": str(asd_path),
        "freeze_rb_layer": True,
        "optimizer": {"type": "adam", "lr": 0.0005},
        "scheduler": {"type": "cosine", "T_max": config["epochs"]},
        "batch_size": config["batch_size"],
    }
    training = {
        "data": data,
        "model": deepcopy(config["model"]),
        "training": {"stage_0": stage},
        "local": {
            "device": "cpu",
            "num_workers": 0,
            "leave_waveforms_on_disk": False,
            "checkpoint_epochs": config["epochs"],
            "runtime_limits": {
                "max_time_per_run": 86400,
                "max_epochs_per_run": config["epochs"],
            },
        },
    }
    write_yaml(outdir / "config.yaml", config)
    write_yaml(outdir / "waveform_dataset_settings.yaml", settings)
    write_yaml(outdir / "train_settings.yaml", training)
    print(f"Prepared {len(waveforms.parameters)} waveforms in {outdir}.")


def train(outdir):
    """Train on local CPU using upstream DINGO's unmodified training runner."""
    outdir = Path(outdir).resolve()
    config = read_config(outdir / "config.yaml")
    seed_everything(config["seed"], config["threads"])
    settings = read_config(outdir / "train_settings.yaml")
    local = settings.pop("local")
    train_dir = outdir / "training"
    if (train_dir / "model_latest.pt").exists():
        raise FileExistsError("Training checkpoint already exists.")
    train_dir.mkdir(exist_ok=True)
    write_yaml(train_dir / "local_settings.yaml", local)
    complete, _, epoch = run_training(
        settings, local, str(train_dir), ckpt_file=None, resume=False
    )
    if not complete or epoch != config["epochs"]:
        raise RuntimeError(f"Training incomplete at epoch {epoch}.")


def inference(outdir):
    """Generate one held-out noisy injection and save NPE proposal samples."""
    outdir = Path(outdir).resolve()
    config = read_config(outdir / "config.yaml")
    seed_everything(config["seed"] + 1, config["threads"])
    model = build_model_from_kwargs(
        filename=str(outdir / "training/model_latest.pt"), device="cpu"
    )
    injection = LensedInjection.from_posterior_model_metadata(model.metadata)
    injection.asd = ASDDataset(file_name=outdir / "asds.hdf5")
    theta = injection.prior.sample()
    theta = {k: float(v) for k, v in theta.items()}
    theta.update(config["injection"])
    observation = injection.injection(theta)
    sampler = GWComposedSampler.from_model(model, observation)
    sampler.run_sampler(
        config["posterior_samples"], batch_size=config["batch_size"]
    )
    result = LensedGWResult(dictionary=sampler.to_result().to_dictionary())
    if not np.isfinite(result.samples["log_prob"]).all():
        raise ValueError("Nonfinite proposal log density.")
    result.to_file(outdir / "proposal.hdf5")
    write_yaml(outdir / "injection.yaml", theta)
    print(f"Saved {result.num_samples} posterior proposal samples.")


def check_weights(result):
    """Check mean-one weights and evidence against the density ratio."""
    samples = result.samples
    valid = np.isfinite(samples["log_prior"].to_numpy())
    log_weights = np.full(result.num_samples, -np.inf)
    log_weights[valid] = (
        samples.loc[valid, "log_likelihood"]
        + samples.loc[valid, "log_prior"]
        - samples.loc[valid, "log_prob"]
    )
    if not np.isfinite(log_weights[valid]).all() or not valid.any():
        raise ValueError("No valid finite importance weights.")
    expected = np.exp(log_weights - logsumexp(log_weights))
    weights = samples["weights"].to_numpy()
    if not np.isfinite(weights).all() or np.any(weights < 0):
        raise ValueError("Invalid importance weights.")
    np.testing.assert_allclose(weights, expected * len(weights), rtol=1e-10)
    np.testing.assert_allclose(
        result.log_evidence,
        logsumexp(log_weights) - np.log(len(weights)),
        atol=1e-8,
    )
    return {
        "num_samples": int(result.num_samples),
        "valid_prior_samples": int(valid.sum()),
        "effective_sample_size": float(result.effective_sample_size),
        "sample_efficiency": float(result.sample_efficiency),
        "maximum_normalized_weight": float(expected.max()),
        "log_evidence": float(result.log_evidence),
        "weight_formula_verified": True,
        "calibration_assessed": False,
    }


def importance_sampling(outdir):
    """Importance sample the saved proposal, resample, and plot diagnostics."""
    outdir = Path(outdir).resolve()
    config = read_config(outdir / "config.yaml")
    seed_everything(config["seed"] + 2, config["threads"])
    result = LensedGWResult(file_name=outdir / "proposal.hdf5")
    result.importance_sample(num_processes=1)
    report = check_weights(result)
    result.to_file(outdir / "importance.hdf5")
    result.sampling_importance_resampling(random_state=config["seed"] + 2)[
        PARAMETERS
    ].to_csv(outdir / "posterior.csv", index=False)
    # Fixed source parameters have zero width; plot inferred dimensions.
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(9, 3.5))
    for axis, name in zip(axes, PARAMETERS):
        axis.hist(
            result.samples[name],
            bins=40,
            density=True,
            histtype="step",
            label="NPE",
        )
        axis.hist(
            result.samples[name],
            bins=40,
            density=True,
            weights=result.samples["weights"],
            histtype="step",
            label="Importance weighted",
        )
        axis.axvline(
            config["injection"][name],
            color="black",
            linestyle="--",
            label="Injection",
        )
        axis.set_xlabel(
            "Delay [s]"
            if name == "lensing_delta_t"
            else "Relative magnification"
        )
        axis.set_ylabel("Posterior density")
    axes[0].legend()
    figure.tight_layout()
    figure.savefig(outdir / "posterior.png", dpi=160)
    plt.close(figure)
    (outdir / "diagnostics.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


def main():
    """Run individual stages or the complete local CPU example."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage", choices=["prepare", "train", "inference", "importance", "all"]
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    if args.stage in ("prepare", "all"):
        if args.config is None:
            parser.error("--config is required for preparation")
        prepare(read_config(args.config), args.outdir)
    for stage, function in [
        ("train", train),
        ("inference", inference),
        ("importance", importance_sampling),
    ]:
        if args.stage in (stage, "all"):
            function(args.outdir)


if __name__ == "__main__":
    main()
