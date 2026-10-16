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

newest_image() {
    local image
    image="$(ls -t "$IMAGE_DIR"/dingo-deps_recipe-*_cpu.sif 2> /dev/null | head -n 1 || true)"
    [[ -n "$image" ]] || fail "No dependencies-only image in $IMAGE_DIR: Run container/build_deps_image.sh first"
    echo "$image"
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
