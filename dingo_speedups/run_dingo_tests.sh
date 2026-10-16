#!/usr/bin/env bash
# Step 1.4: Runs DINGO's own test suite at one commit (default the baseline) in the
# dependencies-only image, with DINGO shipped and checked as jobs will have it
# (pack_dingo.py, guard.py). Writes the output and a JUnit report to
# results/dingo_tests/.
#
# Run on a CIT access point, from anywhere (a few minutes on a few cores):
#     bash ~/dingo-lensing-sync/dingo_speedups/run_dingo_tests.sh [COMMIT] [-- PYTEST ARGUMENTS]
#
# Give pytest option values as --option=value. Settings: See common.sh.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
COMMIT="${1:-$BASELINE}"
if [[ $# -gt 0 ]]; then shift; fi
if [[ "${1:-}" == "--" ]]; then shift; fi
IMAGE="${IMAGE:-$(newest_image)}"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/dingo-tests.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
pack_and_unpack "$COMMIT" "$WORK"
OUT="$RESULTS/dingo_tests"
mkdir -p "$OUT"
NAME="${COMMIT_FULL:0:10}_$(basename "$IMAGE" .sif)"

step "DINGO ${COMMIT_FULL:0:10}'s tests in $(basename "$IMAGE")"
BINDS=("$WORK" "$SYNC:/srv/sync:ro")
set +e
in_image "$IMAGE" /opt/dingo_env/bin/python -I /srv/sync/dingo_speedups/guard.py pytest \
    --tree "$TREE" --commit "$COMMIT_FULL" -- -p no:cacheprovider -rfEs \
    "--junitxml=$WORK/junit.xml" "$@" 2>&1 | tee "$OUT/$NAME.pytest.txt"
STATUS=${PIPESTATUS[0]}
set -e
cp "$WORK/junit.xml" "$OUT/$NAME.junit.xml" 2> /dev/null || true

step "Done"
echo "pytest exit status $STATUS (0: all passed; 1: some tests failed; 2: the guard refused or pytest was interrupted)"
echo "Output: $OUT/$NAME.pytest.txt"
echo "Push it back:  git -C $SYNC add dingo_speedups/results && git -C $SYNC commit -m 'dingo_speedups: DINGO test results (not for review/merge)' && git -C $SYNC push"
exit "$STATUS"
