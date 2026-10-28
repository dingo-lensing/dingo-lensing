#!/usr/bin/env bash
# Compares the importance-sampling results of two baseline runs (compare_results.py),
# inside the dependencies-only image, and writes the report to
# results/baseline/compare_<first>_vs_<second>.json.
#
# Run on a CIT access point, from anywhere:
#     bash ~/dingo-lensing-sync/dingo_speedups/baseline/compare_runs.sh RUN_DIR_A RUN_DIR_B
#
# Settings: See ../common.sh. Reads the results with DINGO at the baseline commit.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../common.sh"
[[ $# -eq 2 ]] || fail "usage: compare_runs.sh RUN_DIR_A RUN_DIR_B"
FIRST="$(realpath "$1")"
SECOND="$(realpath "$2")"
for run in "$FIRST" "$SECOND"; do
    [[ -f "$run/out/importance_sampling.hdf5" ]] || fail "No out/importance_sampling.hdf5 in $run"
done
IMAGE="${IMAGE:-$(newest_image)}"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/dingo-compare.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
pack_and_unpack "$BASELINE" "$WORK"
OUT="$RESULTS/baseline"
mkdir -p "$OUT"
NAME="compare_$(basename "$FIRST")_vs_$(basename "$SECOND")"

BINDS=("$WORK" "$SYNC:/srv/sync:ro" "$FIRST:$FIRST:ro" "$SECOND:$SECOND:ro")
set +e
in_image "$IMAGE" /opt/dingo_env/bin/python -I /srv/sync/dingo_speedups/baseline/compare_results.py \
    --tree "$TREE" --commit "$COMMIT_FULL" \
    "$FIRST/out/importance_sampling.hdf5" "$SECOND/out/importance_sampling.hdf5" \
    --output "$WORK/compare.json"
STATUS=$?
set -e
cp "$WORK/compare.json" "$OUT/$NAME.json" 2> /dev/null || true
echo "Report: $OUT/$NAME.json (exit $STATUS: 0 identical to round-off, 1 not, 2 the guard refused)"
exit "$STATUS"
