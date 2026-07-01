#!/usr/bin/env bash
# pr-fetch-one.sh URL OUTDIR
#
# Fetch one PR's attention JSON into OUTDIR/parts/<owner_repo_num>.json.
# Split out of pr-attention-sweep.sh on purpose: macOS `xargs` cannot assemble a
# long inline `bash -c` worker ("command line cannot be assembled, too long"),
# so the worker must be a file that xargs invokes with just the URL.
#
# `gh` reads </dev/null so it never swallows a parent `while read` loop's stdin.
set -u
u="$1"; OUT="$2"
[ -z "$u" ] && exit 0
repo=$(printf '%s' "$u" | sed -E 's#https://github.com/([^/]+/[^/]+)/pull/[0-9]+#\1#')
num=$(printf '%s' "$u" | sed -E 's#.*/pull/([0-9]+)#\1#')
safe="${repo//\//_}_${num}"
gh pr view "$u" \
  --json number,state,isDraft,mergeable,reviewDecision,updatedAt,author,comments,reviews,statusCheckRollup \
  </dev/null 2>/dev/null \
  | jq -c --arg repo "$repo" '{_repo:$repo} + .' > "$OUT/parts/$safe.json"
