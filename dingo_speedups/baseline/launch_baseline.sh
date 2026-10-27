#!/usr/bin/env bash
# Step 2.1: Launches one full unlensed run on the latest DINGO as a Condor job
# (baseline_run.py), after a pre-flight of the same script with 500 samples inside
# the image on this access point (2 to 3 minutes). See ../test_log.md.
#
# Run on a CIT access point, from anywhere:
#     bash ~/dingo-lensing-sync/dingo_speedups/baseline/launch_baseline.sh [COMMIT]
#
# Settings, from the environment: PRIORITY (default 50), NUM_SAMPLES (50000),
# CPUS (32), MEMORY_GB (48), SKIP_PREFLIGHT=1 to skip the pre-flight, RUNS (default
# ~/dingo-speedups-runs/baseline); MODEL and EVENT_DATA as in ../run_compat_check.sh;
# the rest in ../common.sh. Each launch gets its own run folder, named by time.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../common.sh"
HERE="$SPEEDUPS/baseline"
COMMIT="${1:-$BASELINE}"
EX3="${EX3:-$HOME/dingo_lensing_tutorial/materials/ex3_dingo_lensing_application}"
MODEL="${MODEL:-$EX3/models/model_nonlensed.pt}"
EVENT_DATA="${EVENT_DATA:-$EX3/dingo_EXP2_nonlensed/data/label_data0_1384782888-63_generation_event_data.hdf5}"
PRIORITY="${PRIORITY:-50}"
NUM_SAMPLES="${NUM_SAMPLES:-50000}"
CPUS="${CPUS:-32}"
MEMORY_GB="${MEMORY_GB:-48}"
RUNS="${RUNS:-$HOME/dingo-speedups-runs/baseline}"

step "Checks"
command -v condor_submit > /dev/null || fail "condor_submit not found: Run this on a CIT access point"
for file in "$MODEL" "$EVENT_DATA"; do
    [[ -f "$file" ]] || fail "Not found: $file (set MODEL or EVENT_DATA)"
done
MODEL="$(realpath "$MODEL")"
EVENT_DATA="$(realpath "$EVENT_DATA")"
IMAGE="${IMAGE:-$(newest_image)}"
[[ -f "$IMAGE.url" ]] || fail "$IMAGE has no .url file, so it did not pass every build check"
URL="$(cat "$IMAGE.url")"
[[ "$URL" == osdf:///* ]] || fail "Expected an osdf:/// URL in $IMAGE.url, got $URL"
echo "Image:  $IMAGE"
echo "OSDF:   $URL"

RUN_DIR="$RUNS/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN_DIR"
pack_and_unpack "$COMMIT" "$RUN_DIR"
TARBALL="$TREE.tar.gz"
rm -rf "$TREE"  # the job unpacks its own copy; only the tarball is sent
cp "$HERE/baseline_run.py" "$SPEEDUPS/guard.py" "$RUN_DIR/"
echo "Run folder: $RUN_DIR"

if [[ "${SKIP_PREFLIGHT:-0}" != 1 ]]; then
    step "Pre-flight: The same script with 500 samples on 4 processes, inside the image, here"
    PRE="$(mktemp -d "${TMPDIR:-/tmp}/dingo-preflight.XXXXXX")"
    trap 'rm -rf "$PRE"' EXIT
    cp "$RUN_DIR/baseline_run.py" "$RUN_DIR/guard.py" "$TARBALL" "$PRE/"
    BINDS=("$PRE" "$(dirname "$MODEL"):$(dirname "$MODEL"):ro" "$(dirname "$EVENT_DATA"):$(dirname "$EVENT_DATA"):ro")
    set +e
    in_image "$IMAGE" bash -c "cd '$PRE' && OMP_NUM_THREADS=1 /opt/dingo_env/bin/python -I baseline_run.py \
        --tarball '$(basename "$TARBALL")' --commit '$COMMIT_FULL' --model '$MODEL' --event-data '$EVENT_DATA' \
        --num-samples 500 --batch-size 500 --num-processes 4"
    STATUS=$?
    set -e
    cp "$PRE/out/baseline.json" "$RUN_DIR/preflight.json" 2> /dev/null || true
    [[ $STATUS -eq 0 ]] || fail "Pre-flight failed (exit $STATUS); its report is in $RUN_DIR/preflight.json. Nothing was submitted."
fi

step "Submit (priority $PRIORITY, $CPUS cores, $MEMORY_GB GB, $NUM_SAMPLES samples)"
"$PYTHON" -I "$HERE/make_submit.py" --image-url "$URL" \
    --run-script "$RUN_DIR/baseline_run.py" --guard "$RUN_DIR/guard.py" --tarball "$TARBALL" \
    --model "$MODEL" --event-data "$EVENT_DATA" --commit "$COMMIT_FULL" \
    --num-samples "$NUM_SAMPLES" --cpus "$CPUS" --memory-gb "$MEMORY_GB" --priority "$PRIORITY" \
    --output "$RUN_DIR/baseline.sub"
cat > "$RUN_DIR/launch.json" <<EOF
{
  "dingo_commit": "$COMMIT_FULL",
  "image": "$IMAGE",
  "image_url": "$URL",
  "sync_commit": "$(git -C "$SYNC" rev-parse HEAD)",
  "model": "$MODEL",
  "event_data": "$EVENT_DATA",
  "num_samples": $NUM_SAMPLES,
  "cpus": $CPUS,
  "memory_gb": $MEMORY_GB,
  "priority": $PRIORITY,
  "launched_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
(cd "$RUN_DIR" && condor_submit baseline.sub) | tee "$RUN_DIR/submit.txt"

step "Submitted"
echo "Watch:     condor_q -nobatch"
echo "Log:       tail -f $RUN_DIR/baseline.log"
echo "When done: $PYTHON -I $HERE/collect_baseline.py $RUN_DIR"
echo "Then push: git -C $SYNC add dingo_speedups/results && git -C $SYNC commit -m 'dingo_speedups: 2.1 baseline (not for review/merge)' && git -C $SYNC push"
