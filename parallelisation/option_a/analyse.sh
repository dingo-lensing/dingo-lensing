#!/usr/bin/env bash
# Analyses the finished option A runs inside the image; see analyse_results.py.
#
# Run on the cluster, from anywhere, once all four workflows have finished:
#     bash ~/dingo-lensing-sync/parallelisation/option_a/analyse.sh
#
# Only reads the run folder. Writes ../results/option_a/ in this branch
# (summary.md, summary.json and the corner plots), ready to commit and push.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ROOT="${RUN_ROOT:-$HOME/dingo-lensing-runs/option_a}"
OUTPUT="${OUTPUT:-$(cd "$HERE/.." && pwd)/results/option_a}"
# Kaili's local Exercise 3 run: T2's network samples are compared with its own too.
REFERENCE="${REFERENCE:-$HOME/dingo_lensing_tutorial/materials/ex3_dingo_lensing_application/dingo_EXP1_lensed/result}"

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$RUN_ROOT" ]] || fail "$RUN_ROOT not found"
IMAGE_URL="$(sed -n 's/^container *= *//p' "$HERE/T1a_single.ini")"
IMAGE="/osdf${IMAGE_URL#osdf://}"
[[ -f "$IMAGE" ]] || fail "$IMAGE not found"
REFERENCE_ARGS=()
if [[ -d "$REFERENCE" ]]; then
    REFERENCE_ARGS=(--reference-results "$REFERENCE")
else
    echo "No Exercise 3 results at $REFERENCE, so T2 is compared with its log evidence only."
fi

cd "$HERE"
apptainer exec --cleanenv --bind /home "$IMAGE" /opt/dingo_env/bin/python -s analyse_results.py \
    "$RUN_ROOT" "$OUTPUT" ${REFERENCE_ARGS[@]+"${REFERENCE_ARGS[@]}"}

echo
echo "To send the results back:"
echo "    cd $(dirname "$OUTPUT") && git add $(basename "$OUTPUT") && git commit -m 'Add the option A results (not for review/merge)' && git pull --rebase && git push"
