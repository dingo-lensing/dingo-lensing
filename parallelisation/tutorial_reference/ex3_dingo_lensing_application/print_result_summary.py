#!/usr/bin/env python3
"""Print evidence and sampling statistics for Bilby and Dingo results."""

from pathlib import Path

from bilby.core.result import read_in_result
from dingo.gw.result import Result as DingoResult


BILBY_FILE = next(Path("bilby_EXP1_lensed/final_result").glob("*.hdf5"))
DINGO_FILE = next(Path("dingo_EXP1_lensed/result").glob("*importance_sampling.hdf5"))


def main():
    bilby = read_in_result(filename=str(BILBY_FILE))
    dingo = DingoResult(file_name=str(DINGO_FILE))

    stats = bilby.meta_data["run_statistics"]
    bilby_ess = int(stats["neffsamples"])
    bilby_calls = int(stats["nlikelihood"])
    bilby_efficiency = bilby_ess / bilby_calls

    print("Bilby result")
    print(f"  log evidence       : {bilby.log_evidence:.6f} +/- {bilby.log_evidence_err:.6f}")
    print(f"  sample efficiency  : {100 * bilby_efficiency:.6f}%")
    print(f"  effective samples  : {bilby_ess}")
    print(f"  saved samples      : {len(bilby.posterior)}")

    print("\nDingo result")
    print(f"  log evidence       : {dingo.log_evidence:.6f} +/- {dingo.log_evidence_std:.6f}")
    print(f"  sample efficiency  : {100 * dingo.sample_efficiency:.6f}%")
    print(f"  effective samples  : {dingo.n_eff:.1f}")
    print(f"  saved samples      : {len(dingo.samples)}")


if __name__ == "__main__":
    main()
