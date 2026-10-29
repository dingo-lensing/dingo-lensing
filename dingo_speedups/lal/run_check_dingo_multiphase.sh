#!/usr/bin/env bash
# Step 5.6: Runs check_dingo_multiphase.py in the dependencies-only image on this access point,
# with build_lal.sh's LAL and LALSimulation bound in at their own path and put first: DINGO's
# one-call route against its nine-call route on the 2.1 run's network samples, and the tree's
# XPHM DFT tests. One process, OMP_NUM_THREADS=1. Writes results/lal_multiphase/.
#
#     bash ~/dingo-lensing-sync/dingo_speedups/lal/run_check_dingo_multiphase.sh [DINGO_COMMIT]
#
# DINGO_COMMIT defaults to the fork's kailib-xphm-multiphase branch (fetch it first). Settings,
# from the environment: LALBUILD (default ~/dingo-speedups-lal); NUM_SAMPLES (default 50);
# PROPOSAL and EVENT_DATA as in ../bench/run_xphm_profile.sh; the rest in ../common.sh.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../common.sh"
LALBUILD="${LALBUILD:-$HOME/dingo-speedups-lal}"
ENV="$LALBUILD/env"
LAL_SITE="$ENV/lib/python3.13/site-packages"
COMMIT="${1:-$(git -C "$DINGO_REPO" rev-parse origin/kailib-xphm-multiphase)}"
EX3="${EX3:-$HOME/dingo_lensing_tutorial/materials/ex3_dingo_lensing_application}"
PROPOSAL="${PROPOSAL:-$HOME/dingo-speedups-runs/baseline/20261027T070059Z/out/network_samples.hdf5}"
EVENT_DATA="${EVENT_DATA:-$EX3/dingo_EXP2_nonlensed/data/label_data0_1384782888-63_generation_event_data.hdf5}"
NUM_SAMPLES="${NUM_SAMPLES:-50}"
[[ -f "$LALBUILD/BUILT.txt" && -d "$LAL_SITE/lalsimulation" ]] || fail "No finished build in $LALBUILD: Run build_lal.sh first"
for file in "$PROPOSAL" "$EVENT_DATA"; do
    [[ -f "$file" ]] || fail "Not found: $file (set PROPOSAL or EVENT_DATA)"
done
PROPOSAL="$(realpath "$PROPOSAL")"
EVENT_DATA="$(realpath "$EVENT_DATA")"
IMAGE="${IMAGE:-$(newest_image)}"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/dingo-multiphase.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
pack_and_unpack "$COMMIT" "$WORK"
OUT="$RESULTS/lal_multiphase"
mkdir -p "$OUT"
NAME="dingo_${COMMIT_FULL:0:10}_$(date -u +%Y%m%dT%H%M%SZ)"

step "DINGO ${COMMIT_FULL:0:10}: one LS.SimInspiralFDMultiPhase call against nine LS.SimInspiralFD calls"
BINDS=(
    "$WORK"
    "$SYNC:/srv/sync:ro"
    "$ENV:$ENV:ro"
    "$(dirname "$PROPOSAL"):$(dirname "$PROPOSAL"):ro"
    "$(dirname "$EVENT_DATA"):$(dirname "$EVENT_DATA"):ro"
)
set +e
in_image "$IMAGE" bash -c "OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MPLBACKEND=Agg \
    /opt/dingo_env/bin/python -I /srv/sync/dingo_speedups/lal/check_dingo_multiphase.py \
    --lal-site '$LAL_SITE' --tree '$TREE' --commit '$COMMIT_FULL' --proposal '$PROPOSAL' \
    --event-data '$EVENT_DATA' --num-samples $NUM_SAMPLES --output '$WORK/report.json'" \
    2>&1 | tee "$OUT/$NAME.txt"
STATUS=${PIPESTATUS[0]}
set -e
cp "$WORK/report.json" "$OUT/$NAME.json" 2> /dev/null || true

step "Done"
echo "Exit status $STATUS (0: the routes agree and the tests pass); report: $OUT/$NAME.json"
exit "$STATUS"
