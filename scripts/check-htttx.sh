#!/usr/bin/env bash
# Verify the vendored htttx block in openapi.yaml against upstream.
#
# The block is a verbatim copy, so this is a plain diff. It needs the network
# and is deliberately not part of `make lint`, which stays offline.

set -euo pipefail

COMMIT=37d2385
SOURCE=definitions/stateless/stateless-v1-alpha.yaml
URL="https://raw.githubusercontent.com/hex-tic-tac-toe/htttx-bot-api/${COMMIT}/${SOURCE}"

root=$(cd "$(dirname "$0")/.." && pwd)
vendored=$(mktemp)
upstream=$(mktemp)
trap 'rm -f "$vendored" "$upstream"' EXIT

# Everything between the markers, minus the BEGIN marker plus its three header
# comment lines and the END marker. The four header lines are dropped by
# position, not by pattern, so a line inserted anywhere in the block shifts the
# content and shows up in the diff.
sed -n '/# --- BEGIN vendored htttx ---/,/# --- END vendored htttx ---/p' \
    "$root/openapi.yaml" | sed '1,4d;$d' > "$vendored"

# Upstream ships the same schemas under `components: schemas:`, so the block
# starts at `Coord` and runs to the end of the file at the same indentation.
curl -fsSL "$URL" | sed -n '/^    Coord:/,$p' > "$upstream"

if diff -u --label "htttx-bot-api@${COMMIT} ${SOURCE}" --label openapi.yaml \
    "$upstream" "$vendored"; then
    echo "ok: vendored block matches htttx-bot-api@${COMMIT}"
else
    echo "drift: vendored block differs from htttx-bot-api@${COMMIT}" >&2
    exit 1
fi
