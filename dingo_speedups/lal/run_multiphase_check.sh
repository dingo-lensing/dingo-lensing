#!/usr/bin/env bash
# Runs check_multiphase.py in the environment build_lal.sh made, on this access point, on one
# thread: XLALSimIMRPhenomXPHMMultiPhase against single XLALSimIMRPhenomXPHM calls, timings,
# and the angle multibanding check. About two minutes. Writes results/lal_multiphase/.
#
#     bash ~/dingo-lensing-sync/dingo_speedups/lal/run_multiphase_check.sh
#
# Settings, from the environment: LALBUILD (default ~/dingo-speedups-lal); SAMPLES (default
# ~/dingo-speedups-runs/xphm_args/xphm_args.npz, from ../bench/run_xphm_profile.sh; set
# SAMPLES= to skip the DINGO samples); RANDOM_SETS (default 200).
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../common.sh"
LALBUILD="${LALBUILD:-$HOME/dingo-speedups-lal}"
ENV="$LALBUILD/env"
SAMPLES="${SAMPLES-$HOME/dingo-speedups-runs/xphm_args/xphm_args.npz}"
RANDOM_SETS="${RANDOM_SETS:-200}"
[[ -x "$ENV/bin/python" && -f "$LALBUILD/BUILT.txt" ]] || fail "No finished build in $LALBUILD: Run build_lal.sh first"
SAMPLE_ARGS=()
if [[ -n "$SAMPLES" ]]; then
    [[ -f "$SAMPLES" ]] || fail "Not found: $SAMPLES (run ../bench/run_xphm_profile.sh, or set SAMPLES= to skip)"
    SAMPLE_ARGS=(--samples "$SAMPLES")
fi

OUT="$RESULTS/lal_multiphase"
mkdir -p "$OUT"
NAME="$(awk '$1 == "patch_sha256" {print substr($2, 1, 10)}' "$LALBUILD/BUILT.txt")_$(date -u +%Y%m%dT%H%M%SZ)"

step "XLALSimIMRPhenomXPHMMultiPhase against single calls, one thread"
set +e
OMP_NUM_THREADS=1 "$ENV/bin/python" -I "$SPEEDUPS/lal/check_multiphase.py" ${SAMPLE_ARGS[@]+"${SAMPLE_ARGS[@]}"} \
    --random "$RANDOM_SETS" --built "$LALBUILD/BUILT.txt" --output "$OUT/$NAME.json" 2>&1 | tee "$OUT/$NAME.txt"
STATUS=${PIPESTATUS[0]}
set -e

step "Done"
echo "Exit status $STATUS (0: all cases agree as required); report: $OUT/$NAME.json"
echo "Push it back:  git -C $SYNC add dingo_speedups/results && git -C $SYNC commit -m 'dingo_speedups: XPHM multi-phase check (not for review/merge)' && git -C $SYNC pull --rebase && git -C $SYNC push"
exit "$STATUS"
