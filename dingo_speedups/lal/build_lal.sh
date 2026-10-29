#!/usr/bin/env bash
# Builds LAL and LALSimulation at the release the image uses (lalsuite-v7.26.15) with
# xphm_multiphase.patch applied, with Python bindings, into a conda environment of its own on
# this access point: ~/dingo-speedups-lal/{env,lalsuite}. About 30 to 45 minutes the first
# time (environment, shallow clone, configure, build); a rerun reapplies the patch and rebuilds
# only what changed. Nothing else is touched.
#
#     nohup bash ~/dingo-lensing-sync/dingo_speedups/lal/build_lal.sh > ~/dingo-speedups-lal.log 2>&1 &
#     tail -f ~/dingo-speedups-lal.log
#
# Settings, from the environment: LALBUILD (default ~/dingo-speedups-lal), LAL_TAG
# (lalsuite-v7.26.15), JOBS (parallel make jobs, default 8).
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../common.sh"
LALBUILD="${LALBUILD:-$HOME/dingo-speedups-lal}"
LAL_TAG="${LAL_TAG:-lalsuite-v7.26.15}"
JOBS="${JOBS:-8}"
ENV="$LALBUILD/env"
SRC="$LALBUILD/lalsuite"
PATCH="$SPEEDUPS/lal/xphm_multiphase.patch"
PATCHED_FILES=(lalsimulation/lib/LALSimIMRPhenomXPHM.c lalsimulation/lib/LALSimIMR.h)
mkdir -p "$LALBUILD"

step "Conda environment: $ENV"
CONDA="${CONDA_EXE:-$(command -v conda || true)}"
[[ -n "$CONDA" ]] || fail "conda not found: Run this from a shell with conda (e.g. the igwn environment)"
if [[ ! -x "$ENV/bin/python" ]]; then
    "$CONDA" create -y -p "$ENV" -c conda-forge --override-channels \
        python=3.13 numpy swig gsl fftw zlib hdf5 \
        autoconf automake libtool pkg-config make c-compiler help2man
fi
set +u  # conda's activation scripts read unset variables
source "$("$CONDA" info --base)/etc/profile.d/conda.sh"
conda activate "$ENV"
set -u
echo "Python: $(command -v python), compiler: ${CC:-cc}"

step "LALSuite $LAL_TAG with the patch: $SRC"
if [[ ! -d "$SRC/.git" ]]; then
    git clone --depth 1 --branch "$LAL_TAG" https://git.ligo.org/lscsoft/lalsuite.git "$SRC"
fi
[[ "$(git -C "$SRC" describe --tags --exact-match HEAD)" == "$LAL_TAG" ]] || fail "$SRC is not at $LAL_TAG"
git -C "$SRC" checkout -q -- "${PATCHED_FILES[@]}"  # undo an earlier application of the patch
git -C "$SRC" apply --check "$PATCH" || fail "The patch does not apply to $LAL_TAG"
git -C "$SRC" apply "$PATCH"
git -C "$SRC" diff --stat

step "Configure (LAL and LALSimulation only, Python bindings)"
cd "$SRC"
[[ -x configure ]] || ./00boot
if [[ ! -f Makefile ]]; then
    ./configure --prefix="$ENV" --disable-all-lal --enable-lalsimulation --enable-swig-python \
        --disable-doxygen --disable-gcc-flags PYTHON="$ENV/bin/python"
fi

step "Build and install into the environment ($JOBS jobs)"
make -j"$JOBS"
make install

step "Check"
python -I - <<'EOF'
import lal
import lalsimulation as ls

print("lal", lal.__version__, lal.__file__)
print("lalsimulation", ls.__version__, ls.__file__)
assert hasattr(ls, "SimIMRPhenomXPHMMultiPhase"), "the patched function is missing"
print("SimIMRPhenomXPHMMultiPhase: present")
EOF
{
    echo "tag $LAL_TAG"
    echo "commit $(git -C "$SRC" rev-parse HEAD)"
    echo "patch_sha256 $(sha256sum "$PATCH" | cut -d' ' -f1)"
    echo "sync_commit $(git -C "$SYNC" rev-parse HEAD)"
    echo "built_utc $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$LALBUILD/BUILT.txt"
cat "$LALBUILD/BUILT.txt"

step "Done"
echo "Next: bash $SPEEDUPS/lal/run_multiphase_check.sh"
