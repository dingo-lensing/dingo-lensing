#!/usr/bin/env bash
# Build the existing Gravelamps native requirement into an explicit prefix.
# Prerequisites: CMake >=3.27, C++20 compiler, Boost math_c99, FLINT >=3.
set -euo pipefail
PREFIX="${1:?Usage: install_gravelamps_native.sh PREFIX BUILD_ROOT}"
BUILD_ROOT="${2:?Supply a workspace-local build directory}"
REVISION=5545fa16561db99d02aff404b3282fc85be6ff7b
mkdir -p "$BUILD_ROOT"
BUILD_ROOT="$(cd "$BUILD_ROOT" && pwd)"
ARCHIVE="${BUILD_ROOT}/gravelamps-${REVISION}.tar.gz"
if [[ ! -f "$ARCHIVE" ]]; then
    curl --fail --location --retry 2 \
        "https://git.ligo.org/link/pre-merger-software/gravelamps/-/archive/${REVISION}/gravelamps-${REVISION}.tar.gz" \
        --output "$ARCHIVE"
fi
if [[ ! -d "${BUILD_ROOT}/gravelamps-${REVISION}" ]]; then
    tar -xzf "$ARCHIVE" -C "$BUILD_ROOT"
fi
BOOST_ARGS=()
if [[ -n "${BOOST_CMAKE_DIR:-}" ]]; then
    BOOST_ARGS+=("-DBoost_DIR=${BOOST_CMAKE_DIR}")
fi
cmake -S "${BUILD_ROOT}/gravelamps-${REVISION}/src" \
    -B "${BUILD_ROOT}/build" \
    -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_PREFIX_PATH="$PREFIX" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DCMAKE_CXX_FLAGS="-I${PREFIX}/include" \
    -DCMAKE_SHARED_LINKER_FLAGS="-L${PREFIX}/lib -Wl,-rpath,${PREFIX}/lib" \
    "${BOOST_ARGS[@]}"
cmake --build "${BUILD_ROOT}/build" -j 2
cmake --install "${BUILD_ROOT}/build"
