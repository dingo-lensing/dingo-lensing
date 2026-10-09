#!/usr/bin/env bash
# Analyses the finished option A runs inside the image; see analyse_results.py.
#
# Run on the cluster, from anywhere, once all four workflows have finished:
#     bash ~/dingo-lensing-sync/parallelisation/option_a/analyse.sh        # T1 and T2
#     bash ~/dingo-lensing-sync/parallelisation/option_a/analyse.sh T3     # T3
#
# Only reads the run folders. Writes ../results/option_a/ (or option_a_t3/) in
# this branch (summary.md, summary.json and the corner plots), ready to push.
set -euo pipefail

SUITE="${1:-T1T2}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIRST_RUN_ROOT="$HOME/dingo-lensing-runs/option_a"
case "$SUITE" in
    T1T2) DEFAULT_RUN_ROOT="$FIRST_RUN_ROOT"; RESULTS=option_a; CONFIG=T1a_single.ini ;;
    T3) DEFAULT_RUN_ROOT="$HOME/dingo-lensing-runs/option_a_t3"; RESULTS=option_a_t3; CONFIG=T3a_gw150914.ini ;;
    *) echo "ERROR: Unknown suite '$SUITE': Use T1T2 or T3" >&2; exit 1 ;;
esac
RUN_ROOT="${RUN_ROOT:-$DEFAULT_RUN_ROOT}"
OUTPUT="${OUTPUT:-$(cd "$HERE/.." && pwd)/results/$RESULTS}"
# Kaili's local Exercise 3 run: T2's network samples are compared with its own too.
REFERENCE="${REFERENCE:-$HOME/dingo_lensing_tutorial/materials/ex3_dingo_lensing_application/dingo_EXP1_lensed/result}"

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$RUN_ROOT" ]] || fail "$RUN_ROOT not found"
IMAGE_URL="$(sed -n 's/^container *= *//p' "$HERE/$CONFIG")"
IMAGE="/osdf${IMAGE_URL#osdf://}"
[[ -f "$IMAGE" ]] || fail "$IMAGE not found"
REFERENCE_ARGS=(--suite "$SUITE")
if [[ "$SUITE" == T3 ]]; then
    # GW150914's event data are also compared with T1a's from the first launch.
    REFERENCE_ARGS+=(--earlier-run-root "$FIRST_RUN_ROOT")
elif [[ -d "$REFERENCE" ]]; then
    REFERENCE_ARGS+=(--reference-results "$REFERENCE")
else
    echo "No Exercise 3 results at $REFERENCE, so T2 is compared with its log evidence only."
fi

cd "$HERE"
apptainer exec --cleanenv --bind /home "$IMAGE" /opt/dingo_env/bin/python -s analyse_results.py \
    "$RUN_ROOT" "$OUTPUT" ${REFERENCE_ARGS[@]+"${REFERENCE_ARGS[@]}"}

echo
echo "To send the results back:"
echo "    cd $(dirname "$OUTPUT") && git add $(basename "$OUTPUT") && git commit -m 'Add the option A $SUITE results (not for review/merge)' && git pull --rebase && git push"
