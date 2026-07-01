#!/usr/bin/env bash
# pr-attention-sweep.sh [OUTDIR]
#
# Pull attention state for every OPEN PR authored by the operator and print the
# ones that need us. Feeds Step 3 (prs-needing-attention) of the
# frontier-model-preparation-run sweep.
#
# Run OUTSIDE the sandbox (dangerouslyDisableSandbox): gh needs the host keyring,
# which is unreadable in-sandbox.
#
# Why it is shaped this way (all learned the hard way — see README.md):
#   * `gh pr view` latency here is wildly variable (0.8s .. >30s per call). A
#     serial loop over ~40 PRs blows any Bash-tool timeout, so we fan out with
#     `xargs -P 8` and one output file per PR (concurrent appends to one file
#     interleave).
#   * the per-PR worker is a FILE (pr-fetch-one.sh), not an inline `bash -c`,
#     because macOS xargs cannot assemble a long inline command.
#   * `gh` inside a loop reads stdin; the worker feeds it `</dev/null`.
#   * all analysis is jq — zsh mangles `!` even inside single-quoted heredocs,
#     so inline awk/python `!=` is off-limits.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-${TMPDIR:-/tmp}/pr-sweep}"
ME="$(gh api user --jq .login 2>/dev/null)"
mkdir -p "$OUT/parts"
rm -f "$OUT/parts/"*.json 2>/dev/null

gh search prs --author=@me --state=open --limit 100 --json url --jq '.[].url' > "$OUT/urls.txt"
echo "open PRs: $(wc -l < "$OUT/urls.txt" | tr -d ' ')  (me=$ME)"

< "$OUT/urls.txt" xargs -P 8 -I{} "$HERE/pr-fetch-one.sh" {} "$OUT"
cat "$OUT/parts/"*.json > "$OUT/prs.jsonl" 2>/dev/null
echo "pulled: $(ls "$OUT/parts/"*.json 2>/dev/null | wc -l | tr -d ' ')"
echo ""
echo "=== PRs with attention flags (sorted) ==="

# needs-reply = a non-author comment/review is newer than our latest one.
jq -r --arg me "$ME" '
  select(.state=="OPEN")
  | ((.comments//[]) + (.reviews//[])) as $all
  | ([ $all[] | select((.author.login//"")!=$me) | (.submittedAt//.createdAt//"") ] | max // "") as $theirs
  | ([ $all[] | select((.author.login//"")==$me)  | (.submittedAt//.createdAt//"") ] | max // "") as $ours
  | ( (if .reviewDecision=="CHANGES_REQUESTED" then " changes-requested" else "" end)
    + (if .reviewDecision=="APPROVED" then " approved-awaiting-merge" else "" end)
    + (if .mergeable=="CONFLICTING" then " conflict" else "" end)
    + (if ([ (.statusCheckRollup//[])[] | select(.conclusion=="FAILURE" or .conclusion=="TIMED_OUT" or .conclusion=="CANCELLED" or .state=="FAILURE") ] | length) > 0 then " ci-failing" else "" end)
    + (if ($theirs!="" and $theirs>$ours) then " needs-reply" else "" end)
    + (if .isDraft then " draft" else "" end) ) as $f
  | select($f|length>0)
  | (._repo + "#" + (.number|tostring)) + " —" + $f
    + (if ($theirs!="" and $theirs>$ours) then "  (their last: " + ($theirs[0:10]) + ")" else "" end)
' "$OUT/prs.jsonl" | sort
