#!/usr/bin/env bash
# Step 6.1: The whole end-to-end test of the multi-phase XPHM route, from one command, to leave
# running. It packs the three DINGO commits and the patched LAL, runs a small pre-flight of each
# job here in the image with /home hidden, as on an execute node (about 10 minutes), submits the
# jobs (make_xphm_jobs.py says what they are), waits for them, and collects and judges the results
# (finish_xphm_tests.sh).
#
# Fetch first, since this runs without a terminal:
#     cd ~/dingo-lensing-sync && git pull --rebase && git -C ~/dingo-effeciency fetch origin
#     nohup bash ~/dingo-lensing-sync/dingo_speedups/lal/launch_xphm_tests.sh > ~/dingo-speedups-xphm.log 2>&1 &
#
# The jobs carry on if this script dies, e.g. with a login node restart: Then run
#     bash ~/dingo-lensing-sync/dingo_speedups/lal/finish_xphm_tests.sh RUN_DIR
#
# Every pre-flight runs, and if any fails, the log shows how (show_job.py) and nothing is
# submitted. PREFLIGHT_ONLY=1 stops after the pre-flights in any case.
#
# Settings, from the environment: UPSTREAM, PR454, BRANCH and COMBINED (the DINGO commits), LALBUILD,
# PRIORITY (default 50), RUNS (default ~/dingo-speedups-runs/xphm), WAIT_HOURS (default 48),
# PREFLIGHT_ONLY; PROPOSAL, MODEL and EVENT_DATA as in ../baseline/launch_baseline.sh; the rest
# in ../common.sh.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../common.sh"
HERE="$SPEEDUPS/lal"
LALBUILD="${LALBUILD:-$HOME/dingo-speedups-lal}"
UPSTREAM="${UPSTREAM:-471de26e10cef69bb59a0d2680cc299b4c9c2323}"
PR454="${PR454:-e92d71fbd83fd6e1dd9795655082ed95abdbcda5}"  # its head, as run in 3.5
BRANCH="${BRANCH:-origin/kailib-xphm-multiphase}"
COMBINED="${COMBINED:-origin/kailib-xphm-multiphase-with-pr454}"
EX3="${EX3:-$HOME/dingo_lensing_tutorial/materials/ex3_dingo_lensing_application}"
MODEL="${MODEL:-$EX3/models/model_nonlensed.pt}"
EVENT_DATA="${EVENT_DATA:-$EX3/dingo_EXP2_nonlensed/data/label_data0_1384782888-63_generation_event_data.hdf5}"
PROPOSAL="${PROPOSAL:-$HOME/dingo-speedups-runs/baseline/20261027T070059Z/out/network_samples.hdf5}"
PRIORITY="${PRIORITY:-50}"
RUNS="${RUNS:-$HOME/dingo-speedups-runs/xphm}"

step "Checks"
command -v condor_submit > /dev/null || fail "condor_submit not found: Run this on a CIT access point"
require_current_lal_build "$LALBUILD"
for file in "$MODEL" "$EVENT_DATA" "$PROPOSAL"; do
    [[ -f "$file" ]] || fail "Not found: $file (set MODEL, EVENT_DATA or PROPOSAL)"
done
MODEL="$(realpath "$MODEL")"
EVENT_DATA="$(realpath "$EVENT_DATA")"
PROPOSAL="$(realpath "$PROPOSAL")"
UPSTREAM="$(git -C "$DINGO_REPO" rev-parse "$UPSTREAM^{commit}")" || fail "$DINGO_REPO has no $UPSTREAM"
PR454="$(git -C "$DINGO_REPO" rev-parse "$PR454^{commit}")" || fail "$DINGO_REPO has no $PR454"
BRANCH="$(git -C "$DINGO_REPO" rev-parse "$BRANCH^{commit}")" || fail "$DINGO_REPO has no $BRANCH: Run git -C $DINGO_REPO fetch origin"
COMBINED="$(git -C "$DINGO_REPO" rev-parse "$COMBINED^{commit}")" || fail "$DINGO_REPO has no $COMBINED: Run git -C $DINGO_REPO fetch origin"
IMAGE="${IMAGE:-$(newest_image)}"
[[ -f "$IMAGE.url" ]] || fail "$IMAGE has no .url file, so it did not pass every build check"
URL="$(cat "$IMAGE.url")"
[[ "$URL" == osdf:///* ]] || fail "Expected an osdf:/// URL in $IMAGE.url, got $URL"
echo "Upstream: $UPSTREAM"
echo "PR #454:  $PR454"
echo "Branch:   $BRANCH"
echo "Combined: $COMBINED"
echo "Image:    $IMAGE"

RUN_DIR="$RUNS/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN_DIR/scripts"
echo "Run folder: $RUN_DIR"

step "Pack DINGO and LAL"
pack_commit() {
    pack_and_unpack "$1" "$RUN_DIR"
    rm -rf "$TREE"  # the job unpacks its own copy; only the tarball is sent
    rm -f "$RUN_DIR/pack.json"
    PACKED="$TREE.tar.gz"
}
pack_commit "$UPSTREAM"
UPSTREAM_TARBALL="$PACKED"
pack_commit "$PR454"
PR454_TARBALL="$PACKED"
pack_commit "$BRANCH"
BRANCH_TARBALL="$PACKED"
pack_commit "$COMBINED"
COMBINED_TARBALL="$PACKED"
"$PYTHON" -I "$HERE/pack_lal.py" --env "$LALBUILD/env" --built "$LALBUILD/BUILT.txt" --output-dir "$RUN_DIR" | tee "$RUN_DIR/lal_pack.json"
LAL_TARBALL="$("$PYTHON" -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["path"])' "$RUN_DIR/lal_pack.json")"
cp "$HERE/xphm_job.py" "$HERE/stress_multiphase.py" "$HERE/check_multiphase.py" "$HERE/check_dingo_multiphase.py" \
    "$HERE/run_suite.py" "$SPEEDUPS/baseline/baseline_run.py" "$SPEEDUPS/baseline/compare_results.py" \
    "$SPEEDUPS/guard.py" "$RUN_DIR/scripts/"

step "Manifests and submit files"
"$PYTHON" -I "$HERE/make_xphm_jobs.py" --run-dir "$RUN_DIR" --image-url "$URL" \
    --upstream-tarball "$UPSTREAM_TARBALL" --upstream-commit "$UPSTREAM" \
    --pr454-tarball "$PR454_TARBALL" --pr454-commit "$PR454" \
    --branch-tarball "$BRANCH_TARBALL" --branch-commit "$BRANCH" \
    --combined-tarball "$COMBINED_TARBALL" --combined-commit "$COMBINED" \
    --lal-tarball "$LAL_TARBALL" --proposal "$PROPOSAL" --model "$MODEL" --event-data "$EVENT_DATA" \
    --priority "$PRIORITY"
cat > "$RUN_DIR/launch.json" <<EOF
{
  "upstream": "$UPSTREAM",
  "pr454": "$PR454",
  "branch": "$BRANCH",
  "combined": "$COMBINED",
  "lal_tarball": "$LAL_TARBALL",
  "image": "$IMAGE",
  "image_url": "$URL",
  "sync_commit": "$(git -C "$SYNC" rev-parse HEAD)",
  "proposal": "$PROPOSAL",
  "model": "$MODEL",
  "event_data": "$EVENT_DATA",
  "priority": $PRIORITY,
  "launched_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

step "Pre-flight: Each job, small, in the image, with /home hidden as on an execute node"
PRE="$(mktemp -d "${TMPDIR:-/tmp}/dingo-xphm.XXXXXX")"
trap 'rm -rf "$PRE"' EXIT
cp "$RUN_DIR"/scripts/* "$RUN_DIR"/*.tar.gz "$RUN_DIR"/preflight/*.json "$PRE/"
BINDS=(
    "$PRE"
    "$(dirname "$MODEL"):$(dirname "$MODEL"):ro"
    "$(dirname "$EVENT_DATA"):$(dirname "$EVENT_DATA"):ro"
    "$(dirname "$PROPOSAL"):$(dirname "$PROPOSAL"):ro"
)
FAILED=()
for job in $(cat "$RUN_DIR/preflight_jobs.txt"); do
    echo "--- $job"
    set +e
    in_image "$IMAGE" bash -c "cd '$PRE' && rm -rf out work && OMP_NUM_THREADS=1 /opt/dingo_env/bin/python -I xphm_job.py $job.json"
    STATUS=$?
    set -e
    mkdir -p "$RUN_DIR/preflight/$job"
    cp -r "$PRE/out/." "$RUN_DIR/preflight/$job/" 2> /dev/null || true
    if [[ $STATUS -eq 3 ]]; then
        echo "WARNING: The $job pre-flight ran but disagrees; submitting anyway, for the full numbers: See $RUN_DIR/preflight/$job"
    elif [[ $STATUS -ne 0 ]]; then
        echo "FAILED: The $job pre-flight (exit $STATUS); its reports are in $RUN_DIR/preflight/$job"
        "$PYTHON" -I "$HERE/show_job.py" "$RUN_DIR/preflight/$job" || true
        FAILED+=("$job")
    fi
done
rm -rf "$PRE"
trap - EXIT
[[ ${#FAILED[@]} -eq 0 ]] || fail "Pre-flights failed: ${FAILED[*]}. Nothing was submitted."
if [[ "${PREFLIGHT_ONLY:-0}" == 1 ]]; then
    step "Every pre-flight passed; nothing submitted (PREFLIGHT_ONLY=1). Run folder: $RUN_DIR"
    exit 0
fi

step "Submit (priority $PRIORITY)"
for job in $(cat "$RUN_DIR/jobs.txt"); do
    (cd "$RUN_DIR/$job" && condor_submit job.sub) | tee "$RUN_DIR/$job/submit.txt"
done

bash "$HERE/finish_xphm_tests.sh" "$RUN_DIR"
