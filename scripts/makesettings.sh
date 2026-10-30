#!/usr/bin/env bash
# Generate settings/<device>.yaml for `svd2rust --settings`.
#
# crate_path is functional: it is the module path of the device inside the
# crate (crate/src/<device>/mod.rs), used by svd2rust when it emits
# cross-module type paths (see svd2rust util.rs block_path_to_ty).
#
# svd2rust settings also accept html_url, a link to published register
# documentation. This project has none, so only crate_path is emitted here
# (html_url only affects doc comments).
#
# ASCII only: this machine's MSYS sh mangles non-ASCII shell content.

set -euo pipefail

printf 'crate_path: crate::%s\n' "$1" > "$2"
