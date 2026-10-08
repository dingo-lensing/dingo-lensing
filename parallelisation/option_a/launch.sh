#!/usr/bin/env bash
# Builds and submits the option A tests (T1a, T1b, T2a, T2b); see ../test_log.md.
#
# Run on the cluster, from anywhere:
#     bash ~/dingo-lensing-sync/parallelisation/option_a/launch.sh
#
# Nothing is submitted unless every check passes: The unit tests, the checks on
# environment, code and inputs, the data fetch, the model check, and the checks
# on all four built workflows. Paths can be overridden with the variables below.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

check_workflow() {
    local label="$1" dir="$2" events="$3"
    local submit_dir="$dir/$label/submit"
    local dags=("$submit_dir"/dag_*.submit)
    [[ ${#dags[@]} -eq 1 && -f "${dags[0]}" ]] \
        || fail "$label: Expected exactly one DAG file in $submit_dir"
    local dag="${dags[0]}" n_jobs n_generation n_from_env
    n_jobs="$(grep -c '^JOB ' "$dag")"
    n_generation="$(grep -c '^JOB .*_generation_arg_' "$dag" || true)"
    # One data-generation, sampling, importance-sampling and plot job per event.
    [[ "$n_generation" -eq "$events" ]] \
        || fail "$label: $n_generation data-generation jobs, expected $events"
    [[ "$n_jobs" -eq $((4 * events)) ]] \
        || fail "$label: $n_jobs jobs, expected $((4 * events))"
    # Every job must run dingo_env's code, and nothing may merge (n-parallel = 1).
    n_from_env="$(grep -h '^executable' "$submit_dir"/*.submit | grep -c "= $ENV_PATH/bin/" || true)"
    [[ "$n_from_env" -eq "$n_jobs" ]] \
        || fail "$label: Only $n_from_env of $n_jobs jobs run from $ENV_PATH/bin"
    ! grep -q '_merge' "$dag" || fail "$label: Found a merge job"
    echo "$label: $n_jobs jobs for $events event(s), all running from $ENV_PATH/bin"
}

step "Unit tests"
(cd "$HERE/.." && "$PYTHON" -m unittest discover -s tests) || fail "Unit tests failed"

step "Environment and code"
[[ -x "$PYTHON" ]] || fail "No python at $PYTHON (set ENV_PATH)"
command -v condor_submit_dag > /dev/null || fail "condor_submit_dag not found"
for exe in dingo_lensing_pipe dingo_lensing_pipe_generation dingo_lensing_pipe_sampling \
           dingo_lensing_pipe_importance_sampling dingo_pipe_plot; do
    path="$ENV_PATH/bin/$exe"
    [[ -x "$path" ]] || fail "$path is missing"
    # A cloned env can keep scripts whose first line names the original env's python.
    head -n 1 "$path" | grep -q "^#!$ENV_PATH/" \
        || fail "$path starts with '$(head -n 1 "$path")', not $ENV_PATH's python"
done
installed="$(cd / && "$PYTHON" -c 'import dingo_lensing, os; print(os.path.dirname(os.path.dirname(os.path.realpath(dingo_lensing.__file__))))')"
[[ "$installed" == "$(cd "$REPO" && pwd -P)" ]] \
    || fail "dingo_env imports dingo_lensing from $installed, not $REPO"
[[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == "$BRANCH" ]] || fail "$REPO is not on $BRANCH"
git -C "$REPO" diff --quiet HEAD || fail "$REPO has uncommitted changes to tracked files"
git -C "$REPO" fetch -q origin "$BRANCH"
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$(git -C "$REPO" rev-parse "origin/$BRANCH")" ]] \
    || fail "$REPO is not at origin/$BRANCH; run 'git pull' there first"
COMMIT="$(git -C "$REPO" rev-parse HEAD)"
echo "dingo_env runs $REPO, $BRANCH at $COMMIT"

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
cp "$HERE/T1a_single.ini" "$HERE/T1b_twice.ini" "$HERE/T1b_gps.txt" "$RUN_ROOT/T1/"
cp "$HERE/T2a_single.ini" "$HERE/T2b_three.ini" "$HERE/T2b_gps.txt" "$RUN_ROOT/T2/"
cp -r "$TUTORIAL_EX3/gwf_files" "$RUN_ROOT/T2/"
{
    echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "host: $(hostname)"
    echo "code: $BRANCH at $COMMIT"
    echo "tests: $(git -C "$HERE" rev-parse --abbrev-ref HEAD) at $(git -C "$HERE" rev-parse HEAD)"
    echo "env: $ENV_PATH"
    (cd / && "$PYTHON" -c 'import bilby_pipe, dingo, torch; print(f"dingo: {dingo.__version__}\nbilby_pipe: {bilby_pipe.__version__}\ntorch: {torch.__version__}")')
} > "$RUN_ROOT/run_metadata.txt"
cat "$RUN_ROOT/run_metadata.txt"

step "GW150914 data for T1 (GWOSC)"
(cd "$HERE" && "$PYTHON" fetch_gwosc_frames.py "$RUN_ROOT/T1/T1a_single.ini" --run-dir "$RUN_ROOT/T1")

step "Models: Can this branch rebuild their lensed waveform generators?"
(cd "$HERE" && "$PYTHON" check_models.py "$T1_MODEL" "$T2_MODEL")

step "Build and check workflows"
for entry in "${TESTS[@]}"; do
    read -r label folder config events <<< "$entry"
    dir="$RUN_ROOT/$folder"
    (cd "$dir" && "$ENV_PATH/bin/dingo_lensing_pipe" "$config" > "$label.build.log" 2>&1) \
        || fail "Building $label failed; see $dir/$label.build.log"
    check_workflow "$label" "$dir" "$events"
done

step "Submit"
for entry in "${TESTS[@]}"; do
    read -r label folder config events <<< "$entry"
    dir="$RUN_ROOT/$folder"
    dag="$(cd "$dir" && ls "$label"/submit/dag_*.submit)"
    (cd "$dir" && condor_submit_dag "$dag") | tee -a "$RUN_ROOT/submissions.txt"
done

step "Submitted T1a, T1b, T2a and T2b"
echo "Record: $RUN_ROOT/run_metadata.txt and $RUN_ROOT/submissions.txt"
echo "Watch:  condor_q -dag -nobatch"
