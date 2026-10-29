# Shared by the dingo_speedups scripts: Source it, don't run it.
#
# Settings, all overridable from the environment:
#   PYTHON      Python on the access point for packing (standard library only);
#               default dingo_env's. Its own DINGO is never used.
#   DINGO_REPO  Clone of our DINGO fork, with upstream's tags; default ~/dingo-effeciency
#   IMAGE_DIR   Where the dependencies-only images are built; default ~/dingo-speedups-images
#   IMAGE       The image to use; default the newest in IMAGE_DIR

SPEEDUPS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="$(git -C "$SPEEDUPS" rev-parse --show-toplevel)"
PYTHON="${PYTHON:-$HOME/.conda/envs/dingo_env/bin/python}"
DINGO_REPO="${DINGO_REPO:-$HOME/dingo-effeciency}"
IMAGE_DIR="${IMAGE_DIR:-$HOME/dingo-speedups-images}"
BASELINE="$(tr -d '[:space:]' < "$SPEEDUPS/BASELINE_COMMIT")"
RESULTS="$SPEEDUPS/results"
BINDS=()

fail() { echo "ERROR: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

# newest_image: The newest image that passed every check of build_deps_image.sh. Only
# those get a .url file, written once the image is staged; an image whose checks
# failed, or one still being built, has none.
newest_image() {
    local url
    url="$(ls -t "$IMAGE_DIR"/dingo-deps_recipe-*_cpu.sif.url 2> /dev/null | head -n 1 || true)"
    [[ -n "$url" ]] \
        || fail "No checked dependencies-only image in $IMAGE_DIR: Run container/build_deps_image.sh and let it finish"
    [[ -f "${url%.url}" ]] || fail "${url%.url} is missing, although its .url file exists"
    echo "${url%.url}"
}

# pack_and_unpack COMMIT WORK: Packs DINGO at COMMIT from DINGO_REPO into WORK and
# unpacks it there. Sets TREE (the unpacked folder) and COMMIT_FULL.
pack_and_unpack() {
    local commit="$1" work="$2" tarball
    git -C "$DINGO_REPO" cat-file -e "${commit}^{commit}" 2> /dev/null \
        || fail "$DINGO_REPO has no commit $commit: Clone the fork there, then run git -C $DINGO_REPO fetch upstream --tags"
    "$PYTHON" -I "$SPEEDUPS/pack_dingo.py" --repo "$DINGO_REPO" --commit "$commit" --output-dir "$work" \
        > "$work/pack.json" || fail "Packing $commit failed"
    tarball="$("$PYTHON" -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["path"])' "$work/pack.json")"
    COMMIT_FULL="$("$PYTHON" -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["commit"])' "$work/pack.json")"
    tar -xzf "$tarball" -C "$work"
    TREE="${tarball%.tar.gz}"
    [[ -f "$TREE/COMMIT.json" ]] || fail "Unpacking $tarball did not give $TREE"
    echo "Packed DINGO $COMMIT_FULL into $tarball"
}

# in_image IMAGE COMMAND...: Runs COMMAND in IMAGE as a job would see it: From /,
# with the access point's environment kept out and /home hidden. Mounts BINDS.
in_image() {
    local image="$1"
    shift
    local binds=()
    local bind
    for bind in "${BINDS[@]}"; do
        binds+=(--bind "$bind")
    done
    (cd / && apptainer exec --cleanenv --contain "${binds[@]}" "$image" "$@")
}

# require_current_lal_build LALBUILD: Fails unless LALBUILD holds a finished build_lal.sh build of
# the current lal/xphm_multiphase.patch. While a rebuild runs, BUILT.txt still describes the
# earlier build, whose installed files the rebuild is about to replace.
require_current_lal_build() {
    local lalbuild="$1" have want
    if command -v pgrep > /dev/null && pgrep -u "$(id -u)" -f build_lal.sh > /dev/null; then
        fail "build_lal.sh is running: Let it finish, then run this again"
    fi
    [[ -f "$lalbuild/BUILT.txt" ]] || fail "No finished build in $lalbuild: Run lal/build_lal.sh first"
    have="$(awk '$1 == "patch_sha256" {print $2}' "$lalbuild/BUILT.txt")"
    want="$(sha256sum "$SPEEDUPS/lal/xphm_multiphase.patch" | cut -d' ' -f1)"
    [[ "$have" == "$want" ]] \
        || fail "$lalbuild holds a build of an earlier xphm_multiphase.patch (${have:0:10}, now ${want:0:10}): Run lal/build_lal.sh"
}
