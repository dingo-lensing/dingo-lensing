#!/usr/bin/env bash
# Submits one job of a launch_xphm_tests.sh run again, as this checkout now writes it (the scripts,
# the job's manifest and its submit file), e.g. after Condor held it; then waits for the run and
# collects and judges it all again (finish_xphm_tests.sh). The old job's log and output are kept
# beside the new, with the time of the resubmission in their names.
#
#     nohup bash ~/dingo-lensing-sync/dingo_speedups/lal/resubmit_xphm_job.sh RUN_DIR JOB > ~/dingo-speedups-xphm-JOB.log 2>&1 &
#
# Remove the old job from the queue first (condor_rm CLUSTER). Settings: See ../common.sh.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../common.sh"
HERE="$SPEEDUPS/lal"
[[ $# -eq 2 ]] || fail "usage: resubmit_xphm_job.sh RUN_DIR JOB"
RUN_DIR="$(realpath "$1")"
JOB="$2"
[[ -f "$RUN_DIR/$JOB/job.sub" && -f "$RUN_DIR/launch.json" ]] || fail "$RUN_DIR has no job $JOB from launch_xphm_tests.sh"
command -v condor_submit > /dev/null || fail "condor_submit not found: Run this on a CIT access point"

step "Checks"
if [[ -f "$RUN_DIR/$JOB/submit.txt" ]]; then
    CLUSTER="$(sed -n 's/.*submitted to cluster \([0-9]*\)\..*/\1/p' "$RUN_DIR/$JOB/submit.txt" | tail -n 1)"
    if [[ -n "$CLUSTER" && -n "$(condor_q "$CLUSTER" -af ClusterId 2> /dev/null)" ]]; then
        fail "Cluster $CLUSTER ($JOB) is still in the queue: Run condor_rm $CLUSTER first"
    fi
fi
echo "Run folder: $RUN_DIR"

step "The old $JOB aside, the scripts as they are now, the job written again"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
for name in out job.log job.out job.err submit.txt; do
    if [[ -e "$RUN_DIR/$JOB/$name" ]]; then
        mv "$RUN_DIR/$JOB/$name" "$RUN_DIR/$JOB/$name.before_$STAMP"
    fi
done
cp "$HERE/xphm_job.py" "$HERE/stress_multiphase.py" "$HERE/check_multiphase.py" "$HERE/check_dingo_multiphase.py" \
    "$HERE/run_suite.py" "$SPEEDUPS/baseline/baseline_run.py" "$SPEEDUPS/baseline/compare_results.py" \
    "$SPEEDUPS/guard.py" "$RUN_DIR/scripts/"
"$PYTHON" -I "$HERE/make_xphm_jobs.py" --rewrite "$RUN_DIR" "$JOB"
grep -E "^request_(cpus|memory|disk)" "$RUN_DIR/$JOB/job.sub"

step "Submit $JOB"
(cd "$RUN_DIR/$JOB" && condor_submit job.sub) | tee "$RUN_DIR/$JOB/submit.txt"

bash "$HERE/finish_xphm_tests.sh" "$RUN_DIR"
