#!/usr/bin/env bash
# Runs one Condor job inside a staged image, set up exactly as bilby_pipe sets up
# the pipeline's jobs when `container` and `conda-env = /opt/dingo_env` are given:
# The image is fetched from OSDF with the access point's token and named in
# MY.SingularityImage, and the executable lives inside it. This checks the image,
# the OSDF transfer and the token on a real execute node before T1 and T2.
#
# Usage, on a CIT access point:
#     bash smoke_test.sh osdf:///igwn/cit/staging/<user>/containers/<image>.sif
set -euo pipefail

URL="${1:?usage: smoke_test.sh osdf:///igwn/cit/staging/<user>/containers/<image>.sif}"
[[ "$URL" == osdf:///* ]] || { echo "ERROR: Expected an osdf:/// URL, got $URL" >&2; exit 1; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="${RUN_DIR:-$HOME/dingo-lensing-runs/container_smoke_test/$(date -u +%Y%m%dT%H%M%SZ)}"

mkdir -p "$RUN_DIR"
cp "$HERE/smoke_payload.py" "$RUN_DIR/"
cat > "$RUN_DIR/smoke.sub" <<EOF
universe = vanilla
executable = /opt/dingo_env/bin/python
arguments = smoke_payload.py
transfer_executable = False
MY.SingularityImage = "./$(basename "$URL")"
requirements = (HAS_SINGULARITY=?=True)
should_transfer_files = YES
when_to_transfer_output = ON_EXIT
transfer_input_files = $URL,smoke_payload.py
use_oauth_services = scitokens
request_cpus = 1
request_memory = 4GB
request_disk = 10GB
accounting_group = ligo.dev.o4.cbc.explore.test
log = smoke.log
output = smoke.out
error = smoke.err
queue
EOF

(cd "$RUN_DIR" && condor_submit smoke.sub)
echo "Run folder: $RUN_DIR"
echo "Watch:      condor_q"
echo "When done:  cat $RUN_DIR/smoke.out $RUN_DIR/smoke.err"
