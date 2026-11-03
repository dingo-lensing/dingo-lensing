#!/usr/bin/env bash
# Waits for the jobs of launch_xphm_tests.sh, then collects and judges them into
# results/xphm_end_to_end/. launch_xphm_tests.sh ends by running this. Run it by hand if that
# script died, or to look again at a run that had not finished; it can run any number of times:
#
#     bash ~/dingo-lensing-sync/dingo_speedups/lal/finish_xphm_tests.sh RUN_DIR
#
# Settings, from the environment: WAIT_HOURS (default 48); see ../common.sh.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../common.sh"
[[ $# -eq 1 ]] || fail "usage: finish_xphm_tests.sh RUN_DIR"
RUN_DIR="$(realpath "$1")"
[[ -f "$RUN_DIR/jobs.txt" ]] || fail "$RUN_DIR has no jobs.txt: Is it a run folder of launch_xphm_tests.sh?"
WAIT_HOURS="${WAIT_HOURS:-48}"

step "Waiting for the jobs (up to $WAIT_HOURS hours; held jobs show in condor_q -hold)"
DEADLINE=$(($(date +%s) + WAIT_HOURS * 3600))
for job in $(cat "$RUN_DIR/jobs.txt"); do
    LOG="$RUN_DIR/$job/job.log"
    LEFT=$((DEADLINE - $(date +%s)))
    if [[ -f "$LOG" ]] && condor_wait -wait "$((LEFT > 1 ? LEFT : 1))" "$LOG" > /dev/null; then
        echo "$job finished, $(date -u +%H:%M:%SZ)"
    else
        echo "$job has not finished"
    fi
done

step "Collect and judge"
set +e
"$PYTHON" -I "$SPEEDUPS/lal/collect_xphm_tests.py" "$RUN_DIR"
STATUS=$?
set -e

step "Done"
echo "Exit status $STATUS (0: the test passes; 1: see the problems above); run folder $RUN_DIR"
echo "Push it back:  git -C $SYNC add dingo_speedups/results && git -C $SYNC commit -m 'dingo_speedups: End-to-end test of the multi-phase XPHM route (not for review/merge)' && git -C $SYNC pull --rebase && git -C $SYNC push"
exit "$STATUS"
