#!/usr/bin/env bash
# Step 1.5: Checks that the latest DINGO can use our inputs (compat_check.py), in the
# dependencies-only image: Juno's 0.9.7-trained unlensed model loads and samples,
# and the earlier run's network samples load and go through importance sampling.
# The model and data files are mounted read-only. Writes results/compat/.
#
# Run on a CIT access point, from anywhere (a minute or two; loading the model needs
# about 5 GB of memory):
#     bash ~/dingo-lensing-sync/dingo_speedups/run_compat_check.sh [COMMIT]
#
# Defaults are Exercise 3's unlensed model and its pipeline run; override with
# MODEL, EVENT_DATA and PROPOSAL. NUM_SAMPLES (default 200) and NUM_PROCESSES
# (default 4) size the sampling and importance-sampling checks. Other settings:
# See common.sh.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
COMMIT="${1:-$BASELINE}"
EX3="${EX3:-$HOME/dingo_lensing_tutorial/materials/ex3_dingo_lensing_application}"
MODEL="${MODEL:-$EX3/models/model_nonlensed.pt}"
EVENT_DATA="${EVENT_DATA:-$EX3/dingo_EXP2_nonlensed/data/label_data0_1384782888-63_generation_event_data.hdf5}"
PROPOSAL="${PROPOSAL:-$EX3/dingo_EXP2_nonlensed/result/label_data0_1384782888-63_sampling.hdf5}"
NUM_SAMPLES="${NUM_SAMPLES:-200}"
NUM_PROCESSES="${NUM_PROCESSES:-4}"
[[ "$NUM_SAMPLES" =~ ^[1-9][0-9]*$ && "$NUM_PROCESSES" =~ ^[1-9][0-9]*$ ]] \
    || fail "NUM_SAMPLES and NUM_PROCESSES must be positive whole numbers"
for file in "$MODEL" "$EVENT_DATA" "$PROPOSAL"; do
    [[ -f "$file" ]] || fail "Not found: $file (set MODEL, EVENT_DATA or PROPOSAL)"
done
IMAGE="${IMAGE:-$(newest_image)}"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/dingo-compat.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
pack_and_unpack "$COMMIT" "$WORK"
OUT="$RESULTS/compat"
mkdir -p "$OUT"
# The original 200-sample, 4-process check keeps its file names.
NAME="${COMMIT_FULL:0:10}_$(basename "$IMAGE" .sif)"
if [[ "$NUM_SAMPLES" != 200 || "$NUM_PROCESSES" != 4 ]]; then NAME="${NAME}_n${NUM_SAMPLES}_p${NUM_PROCESSES}"; fi

step "Compatibility checks with DINGO ${COMMIT_FULL:0:10} in $(basename "$IMAGE")"
BINDS=("$WORK" "$SYNC:/srv/sync:ro")
for file in "$MODEL" "$EVENT_DATA" "$PROPOSAL"; do
    folder="$(dirname "$(realpath "$file")")"
    BINDS+=("$folder:$folder:ro")
done
set +e
in_image "$IMAGE" /opt/dingo_env/bin/python -I /srv/sync/dingo_speedups/compat_check.py \
    --tree "$TREE" --commit "$COMMIT_FULL" \
    --model "$(realpath "$MODEL")" --event-data "$(realpath "$EVENT_DATA")" --proposal "$(realpath "$PROPOSAL")" \
    --num-samples "$NUM_SAMPLES" --num-processes "$NUM_PROCESSES" \
    --output "$WORK/compat.json" 2>&1 | tee "$OUT/$NAME.compat.txt"
STATUS=${PIPESTATUS[0]}
set -e
cp "$WORK/compat.json" "$OUT/$NAME.compat.json" 2> /dev/null || true

step "Done"
echo "Exit status $STATUS (0: every check passed; 1: some failed, see the report; 2: the guard refused)"
echo "Report: $OUT/$NAME.compat.json"
echo "Push it back:  git -C $SYNC add dingo_speedups/results && git -C $SYNC commit -m 'dingo_speedups: Compatibility check (not for review/merge)' && git -C $SYNC push"
exit "$STATUS"
