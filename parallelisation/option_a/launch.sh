#!/usr/bin/env bash
# Builds and submits the option A tests (T1a, T1b, T2a, T2b); see ../test_log.md.
#
# Run on the cluster, from anywhere:
#     bash ~/dingo-lensing-sync/parallelisation/option_a/launch.sh
#
# Every job runs inside the container image the configs name (../container/).
# Nothing is submitted unless every check passes: The unit tests, the checks on
# environment, code, image and inputs, the data fetch, the frame and model
# checks (both run inside the image), and the checks on all four built
# workflows. Paths can be overridden with the variables below.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# dingo_env builds the workflows on the access point; the jobs run in the image.
ENV_PATH="${ENV_PATH:-$HOME/.conda/envs/dingo_env}"
REPO="${REPO:-$HOME/dingo-lensing}"
BRANCH="kailib-parallelisation"
TUTORIAL_EX3="${TUTORIAL_EX3:-$HOME/dingo_lensing_tutorial/materials/ex3_dingo_lensing_application}"
RUN_ROOT="${RUN_ROOT:-$HOME/dingo-lensing-runs/option_a}"
PYTHON="$ENV_PATH/bin/python"

# Label, run folder, config, number of events.
TESTS=(
    "T1a T1 T1a_single.ini 1"
    "T1b T1 T1b_twice.ini 2"
    "T2a T2 T2a_single.ini 1"
    "T2b T2 T2b_three.ini 3"
)

fail() { echo "ERROR: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

# On failure, say whether anything reached Condor and what to clean up.
CREATED_RUN_ROOT=0
SUBMITTED=0
on_exit() {
    local status=$?
    [[ $status -eq 0 || $CREATED_RUN_ROOT -eq 0 ]] && return
    if [[ $SUBMITTED -eq 0 ]]; then
        echo "Nothing was submitted. Remove $RUN_ROOT before running again." >&2
    else
        echo "$SUBMITTED workflow(s) were submitted before the failure; check condor_q before removing $RUN_ROOT." >&2
    fi
}
trap on_exit EXIT

step "Unit tests"
(cd "$HERE/.." && "$PYTHON" -m unittest discover -s tests) || fail "Unit tests failed"

step "Environment and code"
[[ -x "$PYTHON" ]] || fail "No python at $PYTHON (set ENV_PATH)"
command -v condor_submit_dag > /dev/null || fail "condor_submit_dag not found"
command -v apptainer > /dev/null || fail "apptainer not found"
# conda-env (/opt/dingo_env) is not a folder here, so bilby_pipe runs
# 'conda env list' before accepting it as the container's environment.
command -v conda > /dev/null || fail "conda not found, and bilby_pipe needs it to accept conda-env"
path="$ENV_PATH/bin/dingo_lensing_pipe"
[[ -x "$path" ]] || fail "$path is missing"
# A cloned env can keep scripts whose first line names the original env's python.
head -n 1 "$path" | grep -q "^#!$ENV_PATH/" \
    || fail "$path starts with '$(head -n 1 "$path")', not $ENV_PATH's python"
installed="$(cd / && "$PYTHON" -c 'import dingo_lensing, os; print(os.path.dirname(os.path.dirname(os.path.realpath(dingo_lensing.__file__))))')"
[[ "$installed" == "$(cd "$REPO" && pwd -P)" ]] \
    || fail "dingo_env imports dingo_lensing from $installed, not $REPO"
[[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == "$BRANCH" ]] || fail "$REPO is not on $BRANCH"
git -C "$REPO" diff --quiet HEAD || fail "$REPO has uncommitted changes to tracked files"
git -C "$REPO" fetch -q origin "$BRANCH"
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$(git -C "$REPO" rev-parse "origin/$BRANCH")" ]] \
    || fail "$REPO is not at origin/$BRANCH; run 'git pull' there first"
COMMIT="$(git -C "$REPO" rev-parse HEAD)"
echo "dingo_env builds the workflows with $REPO, $BRANCH at $COMMIT"

step "Image"
IMAGE_URL="$(sed -n 's/^container *= *//p' "$HERE/T1a_single.ini")"
for entry in "${TESTS[@]}"; do
    read -r label folder config events <<< "$entry"
    [[ "$(sed -n 's/^container *= *//p' "$HERE/$config")" == "$IMAGE_URL" ]] \
        || fail "$config names a different image from T1a_single.ini"
done
[[ "$IMAGE_URL" == osdf:///* ]] || fail "Expected the configs' container to be an osdf:/// URL, got '$IMAGE_URL'"
# bilby_pipe sends the image with each job only if it finds it here, under /osdf.
IMAGE="/osdf${IMAGE_URL#osdf://}"
[[ -f "$IMAGE" ]] || fail "$IMAGE not found; build and stage it with ../container/build_image.sh"
IMAGE_COMMIT="$(cd / && apptainer exec --cleanenv --contain "$IMAGE" cat /opt/dingo-lensing.commit)"
[[ "$IMAGE_COMMIT" == "$COMMIT" ]] \
    || fail "The image has DINGO-Lensing $IMAGE_COMMIT, but the workflows would be built with $COMMIT"
echo "$IMAGE_URL"
echo "has DINGO-Lensing $IMAGE_COMMIT, the commit that builds the workflows"
# Python inside the image, seeing /home like the access point. Run scripts by
# path: Python then adds only the script's folder to its path, and -s keeps out
# any user site-packages folder in the bound home.
IN_IMAGE=(apptainer exec --cleanenv --bind /home "$IMAGE" /opt/dingo_env/bin/python -s)

step "Inputs"
T1_MODEL="$(sed -n 's/^model *= *//p' "$HERE/T1a_single.ini")"
T2_MODEL="$(sed -n 's/^model *= *//p' "$HERE/T2a_single.ini")"
mapfile -t T2_PSDS < <(cd "$HERE" && "$PYTHON" -c \
    'from pipe_config import parse_dict, read_pipe_ini; print("\n".join(parse_dict(read_pipe_ini("T2a_single.ini")["psd-dict"]).values()))')
INPUTS=("$T1_MODEL" "$T2_MODEL" "${T2_PSDS[@]}" "$TUTORIAL_EX3/gwf_files/H1.gwf" "$TUTORIAL_EX3/gwf_files/L1.gwf")
[[ ${#INPUTS[@]} -eq 6 ]] || fail "Expected 6 input files, found ${#INPUTS[@]}: ${INPUTS[*]}"
for input in "${INPUTS[@]}"; do
    [[ -r "$input" ]] || fail "Cannot read $input"
    echo "ok  $input"
done
[[ ! -e "$RUN_ROOT" ]] || fail "$RUN_ROOT already exists; move it away or set RUN_ROOT"

step "Run folder $RUN_ROOT"
mkdir -p "$RUN_ROOT/T1" "$RUN_ROOT/T2"
CREATED_RUN_ROOT=1
cp "$HERE/T1a_single.ini" "$HERE/T1b_twice.ini" "$HERE/T1b_gps.txt" "$RUN_ROOT/T1/"
cp "$HERE/T2a_single.ini" "$HERE/T2b_three.ini" "$HERE/T2b_gps.txt" "$RUN_ROOT/T2/"
cp -r "$TUTORIAL_EX3/gwf_files" "$RUN_ROOT/T2/"
{
    echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "host: $(hostname)"
    echo "code: $BRANCH at $COMMIT"
    echo "tests: $(git -C "$HERE" rev-parse --abbrev-ref HEAD) at $(git -C "$HERE" rev-parse HEAD)"
    echo "image: $IMAGE_URL"
    echo "workflows built with: $ENV_PATH"
    (cd / && apptainer exec --cleanenv --contain "$IMAGE" /opt/dingo_env/bin/python -I -c \
        'import bilby_pipe, dingo, torch; print(f"in the image: dingo {dingo.__version__}, bilby_pipe {bilby_pipe.__version__}, torch {torch.__version__}")')
} > "$RUN_ROOT/run_metadata.txt"
cat "$RUN_ROOT/run_metadata.txt"

step "GW150914 data for T1 (GWOSC)"
(cd "$HERE" && "$PYTHON" fetch_gwosc_frames.py "$RUN_ROOT/T1/T1a_single.ini" --run-dir "$RUN_ROOT/T1")

step "Frames, read inside the image as the data-generation jobs will"
# T1b and T2b list the same events as T1a and T2a (unit-tested), so this covers all four.
(cd "$HERE" && "${IN_IMAGE[@]}" check_frames.py "$RUN_ROOT/T1/T1a_single.ini" --run-dir "$RUN_ROOT/T1")
(cd "$HERE" && "${IN_IMAGE[@]}" check_frames.py "$RUN_ROOT/T2/T2a_single.ini" --run-dir "$RUN_ROOT/T2")

step "Models: Can the image rebuild their lensed waveform generators?"
(cd "$HERE" && "${IN_IMAGE[@]}" check_models.py "$T1_MODEL" "$T2_MODEL")

step "Build and check workflows"
for entry in "${TESTS[@]}"; do
    read -r label folder config events <<< "$entry"
    dir="$RUN_ROOT/$folder"
    (cd "$dir" && "$ENV_PATH/bin/dingo_lensing_pipe" "$config" > "$label.build.log" 2>&1) \
        || fail "Building $label failed; see $dir/$label.build.log"
    (cd "$HERE" && "$PYTHON" check_workflow.py "$dir" "$config" "$events") \
        || fail "$label's workflow failed the checks above"
done

step "Submit"
for entry in "${TESTS[@]}"; do
    read -r label folder config events <<< "$entry"
    dir="$RUN_ROOT/$folder"
    dag="$(cd "$dir" && ls "$label"/submit/dag_*.submit)"
    (cd "$dir" && condor_submit_dag "$dag") | tee -a "$RUN_ROOT/submissions.txt"
    SUBMITTED=$((SUBMITTED + 1))
done

step "Submitted T1a, T1b, T2a and T2b"
echo "Record: $RUN_ROOT/run_metadata.txt and $RUN_ROOT/submissions.txt"
echo "Watch:  condor_q -dag -nobatch"
