#!/usr/bin/env bash
# Install the pinned toolchain.
#
# This repo runs on Windows/MSYS as well as Linux, so everything comes from
# `cargo install` with pinned versions rather than prebuilt binaries. Pinned
# versions are a hard requirement: identical tool versions must produce
# identical output (see `make repro-check`).
#
# ASCII only: this machine's MSYS sh mangles non-ASCII shell content.

set -euo pipefail

SVD2RUST_VERSION="${SVD2RUST_VERSION:-0.37.1}"
SVDTOOLS_VERSION="${SVDTOOLS_VERSION:-0.5.0}"
FORM_VERSION="${FORM_VERSION:-0.13.0}"
TARGET="${TARGET:-thumbv7em-none-eabihf}"

cargo install svd2rust --version "$SVD2RUST_VERSION"
cargo install svdtools --version "$SVDTOOLS_VERSION"
cargo install form --version "$FORM_VERSION"
rustup target add "$TARGET"

echo "OK: svd2rust=$SVD2RUST_VERSION svdtools=$SVDTOOLS_VERSION form=$FORM_VERSION target=$TARGET"
