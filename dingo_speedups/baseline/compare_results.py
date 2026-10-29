"""Compare two importance-sampling results on the same network samples, e.g. from two DINGO commits.

Runs inside the dependencies-only image from a shipped DINGO tree (checked by guard.py):

    python -I compare_results.py --tree DIR --commit SHA A.hdf5 B.hdf5 --output OUT.json

For every numeric sample column the two share it reports the largest absolute and
relative difference over finite entries and any mismatch in the non-finite ones (which
must be identical, e.g. -inf log priors), and the differences in the log evidence,
its error and the effective samples. Exit code 0 if both have the same samples and
every shared column agrees to --rtol (default 1e-9), 1 otherwise, 2 if the guard refused.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
for folder in (HERE, HERE.parent):
    if (folder / "guard.py").is_file():
        sys.path.insert(0, str(folder))
        break

import guard  # noqa: E402


def column_differences(a: np.ndarray, b: np.ndarray) -> dict:
    """Largest absolute and relative difference of two equally long columns where both are finite.
    Entries not finite in either must be identical (the same infinity, or both NaN), e.g. the log
    prior of samples outside the prior."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.shape != b.shape:
        raise ValueError(f"Columns differ in shape: {a.shape} and {b.shape}")
    finite = np.isfinite(a) & np.isfinite(b)
    same = (a == b) | (np.isnan(a) & np.isnan(b))
    difference = np.abs(a[finite] - b[finite])
    scale = np.maximum(np.maximum(np.abs(a[finite]), np.abs(b[finite])), np.finfo(float).tiny)
    return {
        "max_abs": float(difference.max()) if difference.size else 0.0,
        "max_rel": float((difference / scale).max()) if difference.size else 0.0,
        "nonfinite": int(np.sum(~finite)),
        "nonfinite_mismatch": int(np.sum(~finite & ~same))
    }


def agrees(differences: dict, rtol: float) -> bool:
    return differences["nonfinite_mismatch"] == 0 and differences["max_rel"] <= rtol


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tree", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("--rtol", type=float, default=1e-9)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        provenance = guard.use_dingo(args.tree, args.commit)
    except guard.GuardError as error:
        print(f"GUARD FAILED: {error}", file=sys.stderr)
        return 2
    from dingo.gw.result import Result

    first, second = Result(file_name=args.first), Result(file_name=args.second)
    report = {"provenance": provenance, "first": args.first, "second": args.second, "rtol": args.rtol}
    same_length = len(first.samples) == len(second.samples)
    report["num_samples"] = [len(first.samples), len(second.samples)]
    columns = {}
    if same_length:
        for name in sorted(set(first.samples.columns) & set(second.samples.columns)):
            if np.issubdtype(first.samples[name].dtype, np.number):
                columns[name] = column_differences(
                    first.samples[name].to_numpy(),
                    second.samples[name].to_numpy()
                )
    report["columns"] = columns
    report["only_in_first"] = sorted(set(first.samples.columns) - set(second.samples.columns))
    report["only_in_second"] = sorted(set(second.samples.columns) - set(first.samples.columns))
    report["summary"] = {
        key: [float(getattr(first, key)), float(getattr(second, key))]
        for key in ("log_evidence", "log_evidence_std", "n_eff", "sample_efficiency")
    }
    report["identical_to_rtol"] = same_length and all(agrees(c, args.rtol) for c in columns.values())
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for name, c in columns.items():
        differences = f"max abs {c['max_abs']:10.3e}   max rel {c['max_rel']:10.3e}"
        print(f"{name:28s} {differences}   non-finite {c['nonfinite']}, mismatched {c['nonfinite_mismatch']}")
    for key, (x, y) in report["summary"].items():
        print(f"{key:28s} {x:.6f} vs {y:.6f}")
    print(f"Identical to rtol {args.rtol:g}: {report['identical_to_rtol']}")
    return 0 if report["identical_to_rtol"] else 1


if __name__ == "__main__":
    sys.exit(main())
