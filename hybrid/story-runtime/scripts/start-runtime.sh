#!/usr/bin/env sh
set -eu
RUNTIME_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
: "${STORY_RUNTIME_DB:=$RUNTIME_DIR/data/story.db}"
export STORY_RUNTIME_DB
exec python3 -m story_runtime --db "$STORY_RUNTIME_DB" serve "$@"
