#!/usr/bin/env bash
# Builds the CPU-only DINGO-Lensing image from dingo-lensing.def, checks it, and
# stages it on OSDF for Condor jobs; see ../test_log.md.
#
# Run on a CIT access point (ldas-grid or citlogin5), from anywhere:
#     bash ~/dingo-lensing-sync/parallelisation/container/build_image.sh
#
# Nothing is staged unless every check passes. A staged file can never be
# replaced, so each image is named after the two commits it is built from: Our
# DINGO-Lensing branch and this recipe.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="$(git -C "$HERE" rev-parse --show-toplevel)"
ENV_PATH="${ENV_PATH:-$HOME/.conda/envs/dingo_env}"
REPO="${REPO:-$HOME/dingo-lensing}"
BRANCH="kailib-parallelisation"
IMAGE_DIR="${IMAGE_DIR:-$HOME/dingo-lensing-images}"
STAGING="${STAGING:-/osdf/igwn/cit/staging/$USER/containers}"
PYTHON="$ENV_PATH/bin/python"

fail() { echo "ERROR: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

step "Unit tests"
(cd "$SYNC/parallelisation" && "$PYTHON" -m unittest discover -s tests) || fail "Unit tests failed"

step "Inputs"
command -v apptainer > /dev/null || fail "apptainer not found"
git -C "$SYNC" diff --quiet HEAD -- parallelisation/container \
    || fail "Commit the changes in parallelisation/container first: The image name records the recipe's commit"
RECIPE_COMMIT="$(git -C "$SYNC" rev-parse --short=7 HEAD)"
[[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == "$BRANCH" ]] || fail "$REPO is not on $BRANCH"
git -C "$REPO" diff --quiet HEAD || fail "$REPO has uncommitted changes to tracked files"
git -C "$REPO" fetch -q origin "$BRANCH"
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$(git -C "$REPO" rev-parse "origin/$BRANCH")" ]] \
    || fail "$REPO is not at origin/$BRANCH, and the image downloads that commit from GitHub"
DINGO_LENSING_COMMIT="$(git -C "$REPO" rev-parse HEAD)"
# dingo_env installed modwaveforms from git; pip records the exact commit.
MODWAVEFORMS_COMMIT="$(cd / && "$PYTHON" -c 'import json, importlib.metadata as m; print(json.loads(m.distribution("modwaveforms").read_text("direct_url.json") or "{}").get("vcs_info", {}).get("commit_id", ""))')"
[[ "$MODWAVEFORMS_COMMIT" =~ ^[0-9a-f]{40}$ ]] \
    || fail "Could not read modwaveforms' git commit from dingo_env (got '$MODWAVEFORMS_COMMIT')"
"$PYTHON" "$HERE/make_requirements.py" "$HERE/dingo_env_pip_list.txt" --check "$HERE/requirements-cpu.txt"
diff <(cd / && "$PYTHON" -m pip list --format=freeze 2> /dev/null) "$HERE/dingo_env_pip_list.txt" > /dev/null \
    || fail "dingo_env has changed since dingo_env_pip_list.txt was recorded; record it again and rerun make_requirements.py"
echo "DINGO-Lensing $DINGO_LENSING_COMMIT"
echo "modwaveforms  $MODWAVEFORMS_COMMIT"
echo "recipe        $RECIPE_COMMIT"

NAME="dingo-lensing_${DINGO_LENSING_COMMIT:0:10}_recipe-${RECIPE_COMMIT}_cpu.sif"
IMAGE="$IMAGE_DIR/$NAME"
STAGED="$STAGING/$NAME"
[[ ! -e "$IMAGE" ]] || fail "$IMAGE already exists"
[[ ! -e "$STAGED" ]] || fail "$STAGED already exists, and staged files cannot be replaced"

step "Build $NAME (several minutes; full log in $IMAGE.build.log)"
mkdir -p "$IMAGE_DIR"
(cd "$HERE" && apptainer build \
    --build-arg "DINGO_LENSING_COMMIT=$DINGO_LENSING_COMMIT" \
    --build-arg "MODWAVEFORMS_COMMIT=$MODWAVEFORMS_COMMIT" \
    "$IMAGE" dingo-lensing.def) > "$IMAGE.build.log" 2>&1 \
    || { tail -n 30 "$IMAGE.build.log"; fail "Build failed; see $IMAGE.build.log"; }
ls -lh "$IMAGE"

step "Check the image"
# Run from /, so the old package copy at the sync branch's root (or any other
# folder) can't shadow the image's. --cleanenv keeps the access point's
# environment out; --contain also hides /home, as on CIT's execute nodes.
cd /
apptainer test --cleanenv --contain "$IMAGE"
echo "pip check inside the image:"
apptainer exec --cleanenv --contain "$IMAGE" cat /opt/pip-check.txt
T1_MODEL="$(sed -n 's/^model *= *//p' "$SYNC/parallelisation/option_a/T1a_single.ini")"
T2_MODEL="$(sed -n 's/^model *= *//p' "$SYNC/parallelisation/option_a/T2a_single.ini")"
# The model check needs /home for the model files and the script. Python adds
# only the script's own folder to its path, and -s keeps out any user
# site-packages folder in the bound home.
apptainer exec --cleanenv --bind /home "$IMAGE" /opt/dingo_env/bin/python -s \
    "$SYNC/parallelisation/option_a/check_models.py" "$T1_MODEL" "$T2_MODEL"

step "Stage on OSDF"
mkdir -p "$STAGING"
cp "$IMAGE" "$STAGED"
[[ "$(sha256sum < "$IMAGE")" == "$(sha256sum < "$STAGED")" ]] || fail "The staged copy differs from the build"
URL="osdf://${STAGED#/osdf}"
echo "$URL" > "$IMAGE.url"

step "Done"
echo "Image:  $IMAGE"
echo "OSDF:   $URL"
echo "Next:   bash $HERE/smoke_test.sh $URL"
