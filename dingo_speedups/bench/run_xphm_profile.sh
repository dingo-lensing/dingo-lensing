#!/usr/bin/env bash
# Step 2.2: Runs xphm_profile.py, the per-sample split of the synthetic phase, in the
# dependencies-only image on this access point, in one process with
# OMP_NUM_THREADS=1. Writes results/xphm_profile/. About two minutes.
#
#     bash ~/dingo-lensing-sync/dingo_speedups/bench/run_xphm_profile.sh [COMMIT]
#
# Settings, from the environment: NUM_SAMPLES (default 100); PROPOSAL (default the
# 2.1 run's network samples); EVENT_DATA (default Exercise 3's unlensed run); the
# rest in ../common.sh.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../common.sh"
COMMIT="${1:-$BASELINE}"
EX3="${EX3:-$HOME/dingo_lensing_tutorial/materials/ex3_dingo_lensing_application}"
PROPOSAL="${PROPOSAL:-$HOME/dingo-speedups-runs/baseline/20261027T070059Z/out/network_samples.hdf5}"
EVENT_DATA="${EVENT_DATA:-$EX3/dingo_EXP2_nonlensed/data/label_data0_1384782888-63_generation_event_data.hdf5}"
NUM_SAMPLES="${NUM_SAMPLES:-100}"
for file in "$PROPOSAL" "$EVENT_DATA"; do
    [[ -f "$file" ]] || fail "Not found: $file (set PROPOSAL or EVENT_DATA)"
done
PROPOSAL="$(realpath "$PROPOSAL")"
EVENT_DATA="$(realpath "$EVENT_DATA")"
IMAGE="${IMAGE:-$(newest_image)}"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/dingo-xphm.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
pack_and_unpack "$COMMIT" "$WORK"
OUT="$RESULTS/xphm_profile"
mkdir -p "$OUT"
NAME="${COMMIT_FULL:0:10}_$(basename "$IMAGE" .sif)_n${NUM_SAMPLES}"

step "Per-sample split of the synthetic phase, DINGO ${COMMIT_FULL:0:10}, one process, OMP_NUM_THREADS=1"
BINDS=("$WORK" "$SYNC:/srv/sync:ro" "$(dirname "$PROPOSAL"):$(dirname "$PROPOSAL"):ro" "$(dirname "$EVENT_DATA"):$(dirname "$EVENT_DATA"):ro")
set +e
in_image "$IMAGE" bash -c "OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /opt/dingo_env/bin/python -I \
    /srv/sync/dingo_speedups/bench/xphm_profile.py --tree '$TREE' --commit '$COMMIT_FULL' \
    --proposal '$PROPOSAL' --event-data '$EVENT_DATA' --num-samples $NUM_SAMPLES --output '$WORK/profile.json'" \
    2>&1 | tee "$OUT/$NAME.txt"
STATUS=${PIPESTATUS[0]}
set -e
cp "$WORK/profile.json" "$OUT/$NAME.json" 2> /dev/null || true

step "Done"
echo "Exit status $STATUS; report: $OUT/$NAME.json"
echo "Push it back:  git -C $SYNC add dingo_speedups/results && git -C $SYNC commit -m 'dingo_speedups: 2.2 XPHM profile (not for review/merge)' && git -C $SYNC push"
exit "$STATUS"
