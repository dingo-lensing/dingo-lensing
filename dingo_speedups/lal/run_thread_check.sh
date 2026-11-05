#!/usr/bin/env bash
# thread_check.py in the image, with the thread settings of an 8-core job (OMP_NUM_THREADS,
# MKL_NUM_THREADS and OPENBLAS_NUM_THREADS at 8), five ways: With the image's LAL; with it and the
# patched LAL's lib/ as LD_LIBRARY_PATH; with the patched LAL as the jobs run it; and that with
# OPENBLAS_NUM_THREADS=1, and with OPENBLAS_MAIN_FREE=1. A minute or two on an access point:
#
#     bash ~/dingo-lensing-sync/dingo_speedups/lal/run_thread_check.sh RUN_DIR
#
# RUN_DIR is a run folder of launch_xphm_tests.sh, for its LAL tarball (lal_pack.json).
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../common.sh"
[[ $# -eq 1 ]] || fail "usage: run_thread_check.sh RUN_DIR"
RUN_DIR="$(realpath "$1")"
[[ -f "$RUN_DIR/lal_pack.json" ]] || fail "$RUN_DIR has no lal_pack.json: Is it a run folder of launch_xphm_tests.sh?"
TARBALL="$("$PYTHON" -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["path"])' "$RUN_DIR/lal_pack.json")"
IMAGE="${IMAGE:-$(newest_image)}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dingo-threads.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
tar -xzf "$TARBALL" -C "$WORK"
LAL="$WORK/$(basename "$TARBALL" .tar.gz)"
[[ -d "$LAL/lib" && -d "$LAL/python" ]] || fail "$TARBALL has no lib/ and python/ under $(basename "$LAL")"
cp "$SPEEDUPS/lal/thread_check.py" "$WORK/"
BINDS=("$WORK")
echo "Image: $IMAGE"
echo "LAL:   $TARBALL"

# check LABEL LAL_SITE [VARIABLE=VALUE ...]: LAL_SITE empty for the image's LAL.
check() {
    local label="$1" site="$2"
    shift 2
    local site_args=()
    [[ -z "$site" ]] || site_args=(--lal-site "$site")
    in_image "$IMAGE" env OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 "$@" \
        /opt/dingo_env/bin/python -I "$WORK/thread_check.py" --label "$label" ${site_args[@]+"${site_args[@]}"} \
        || echo "FAILED: $label (exit $?)"
}

check "image LAL" ""
check "image LAL, the patched LAL's lib/ on LD_LIBRARY_PATH" "" "LD_LIBRARY_PATH=$LAL/lib"
check "patched LAL, as the jobs run it" "$LAL/python" "LD_LIBRARY_PATH=$LAL/lib"
check "patched LAL, OPENBLAS_NUM_THREADS=1" "$LAL/python" "LD_LIBRARY_PATH=$LAL/lib" OPENBLAS_NUM_THREADS=1
check "patched LAL, OPENBLAS_MAIN_FREE=1" "$LAL/python" "LD_LIBRARY_PATH=$LAL/lib" OPENBLAS_MAIN_FREE=1
