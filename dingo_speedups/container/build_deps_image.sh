#!/usr/bin/env bash
# Step 1.1: Builds the dependencies-only image from dingo-deps.def, checks it, and
# stages it on OSDF for Condor jobs; see ../test_log.md.
#
# Run on a CIT access point (ldas-grid or citlogin5), from anywhere:
#     bash ~/dingo-lensing-sync/dingo_speedups/container/build_deps_image.sh
#
# Needs a clone of our DINGO fork with upstream's tags (DINGO_REPO, default
# ~/dingo-effeciency); see ../common.sh for the other settings. Nothing is staged
# unless every check passes:
#   - unit tests on the access point, and again inside the image (where the
#     pytest-mode tests can run), plus the guard's mutation check there;
#   - the image's own %test (no DINGO in it, all of DINGO's dependencies);
#   - DINGO at the baseline commit, shipped as jobs ship it, passes guard.py
#     inside the image, and the modules we will change import there.
# A staged file can never be replaced, so the image is named after the last commit
# that changed this folder.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../common.sh"
HERE="$SPEEDUPS/container"
STAGING="${STAGING:-/osdf/igwn/cit/staging/$USER/containers}"

step "Unit tests"
(cd "$SPEEDUPS" && "$PYTHON" -m unittest discover -s tests) || fail "dingo_speedups unit tests failed"
(cd "$SYNC/parallelisation" && "$PYTHON" -m unittest discover -s tests) \
    || fail "parallelisation unit tests failed (its make_requirements.py is reused)"

step "Inputs"
command -v apptainer > /dev/null || fail "apptainer not found"
git -C "$SYNC" diff --quiet HEAD -- dingo_speedups/container \
    || fail "Commit the changes in dingo_speedups/container first: The image name records the recipe's commit"
RECIPE_COMMIT="$(git -C "$SYNC" log -1 --format=%H -- dingo_speedups/container | cut -c1-7)"
[[ "$RECIPE_COMMIT" =~ ^[0-9a-f]{7}$ ]] || fail "Could not find the last commit that changed dingo_speedups/container"
"$PYTHON" -I "$HERE/make_deps_requirements.py" --check "$HERE/requirements-deps-cpu.txt"
git -C "$DINGO_REPO" cat-file -e "${BASELINE}^{commit}" 2> /dev/null \
    || fail "$DINGO_REPO lacks the baseline commit $BASELINE: Clone the fork there, then git fetch upstream --tags"
echo "recipe   $RECIPE_COMMIT"
echo "baseline $BASELINE"

NAME="dingo-deps_recipe-${RECIPE_COMMIT}_cpu.sif"
IMAGE="$IMAGE_DIR/$NAME"
STAGED="$STAGING/$NAME"
[[ ! -e "$IMAGE" ]] || fail "$IMAGE already exists"
[[ ! -e "$STAGED" ]] || fail "$STAGED already exists, and staged files cannot be replaced"

step "Build $NAME (several minutes; full log in $IMAGE.build.log)"
mkdir -p "$IMAGE_DIR"
(cd "$HERE" && apptainer build "$IMAGE" dingo-deps.def) > "$IMAGE.build.log" 2>&1 \
    || { tail -n 30 "$IMAGE.build.log"; fail "Build failed; see $IMAGE.build.log"; }
ls -lh "$IMAGE"

step "Check the image"
(cd / && apptainer test --cleanenv --contain "$IMAGE")
echo "pip check inside the image:"
in_image "$IMAGE" cat /opt/pip-check.txt

step "DINGO ${BASELINE:0:10}, shipped as jobs ship it, passes the guard inside the image"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dingo-deps-check.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
pack_and_unpack "$BASELINE" "$WORK"
BINDS=("$WORK" "$SYNC:/srv/sync:ro")
in_image "$IMAGE" /opt/dingo_env/bin/python -I /srv/sync/dingo_speedups/guard.py check \
    --tree "$TREE" --commit "$COMMIT_FULL" \
    --import dingo.gw.likelihood --import dingo.gw.inference.steps \
    --import dingo.core.density.interpolation --import dingo.gw.waveform_generator \
    > "$IMAGE.guard.json" || fail "The guard refused, or a DINGO module failed to import; see above"
echo "Provenance in $IMAGE.guard.json"

step "Unit tests and the guard's mutation check inside the image"
in_image "$IMAGE" bash -c 'cd /srv/sync/dingo_speedups && /opt/dingo_env/bin/python -m unittest discover -s tests' \
    || fail "Unit tests failed inside the image"
in_image "$IMAGE" bash -c 'cd /srv/sync/dingo_speedups && /opt/dingo_env/bin/python tests/mutation_check.py --module guard.py' \
    || fail "A guard mutation survived inside the image"

step "Stage on OSDF"
mkdir -p "$STAGING"
cp "$IMAGE" "$STAGED"
[[ "$(sha256sum < "$IMAGE")" == "$(sha256sum < "$STAGED")" ]] || fail "The staged copy differs from the build"
URL="osdf://${STAGED#/osdf}"
echo "$URL" > "$IMAGE.url"

step "Done"
echo "Image:  $IMAGE"
echo "OSDF:   $URL"
echo "Next:   bash $SPEEDUPS/run_dingo_tests.sh    (step 1.4)"
