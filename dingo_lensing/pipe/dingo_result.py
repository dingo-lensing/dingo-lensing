"""Merge lensed result parts without executing upstream source text."""

import argparse
from pathlib import Path

from dingo_lensing.result import LensedGWResult


def main():
    """Merge results with the existing upstream-compatible CLI arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=str)
    parser.add_argument("--label", type=str)
    parser.add_argument("--extension", type=str)
    parser.add_argument("--result", type=str, nargs="+")
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()
    if args.merge:
        parts = [LensedGWResult(file_name=p) for p in args.result]
        result = LensedGWResult.merge(parts)
        result.print_summary()
        output = Path(args.outdir) / (
            args.label.replace("_merge", "") + ".hdf5"
        )
        result.to_file(output)


if __name__ == "__main__":
    main()
