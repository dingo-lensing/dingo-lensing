#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

mkdir -p data logs .matplotlib_cache
export MPLCONFIGDIR="${MPLCONFIGDIR:-${SCRIPT_DIR}/.matplotlib_cache}"

SETTINGS_FILE="${SETTINGS_FILE:-waveform_dataset_lensed_100000_svd.yaml}"
OUT_FILE="${OUT_FILE:-data/waveform_dataset_lensed_100000_svd.hdf5}"
NUM_PROCESSES="${NUM_PROCESSES:-1}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-dingo_lensing}"

if command -v dingo_lensing_generate_dataset >/dev/null 2>&1; then
  DINGO_LENSING_CMD=(dingo_lensing_generate_dataset)
else
  DINGO_LENSING_CMD=(conda run -n "${CONDA_ENV_NAME}" dingo_lensing_generate_dataset)
fi

"${DINGO_LENSING_CMD[@]}" \
  --settings_file "${SETTINGS_FILE}" \
  --num_processes "${NUM_PROCESSES}" \
  --out_file "${OUT_FILE}"
