#!/usr/bin/env python3
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Bot-aware PR-attention classifier for the FMP/Glasswing sweep (Step 3).

Consumes the JSONL that ``pr-attention-sweep.sh`` produces (``prs.jsonl`` — one
``gh pr view --json ...`` object per line, each carrying an added ``_repo`` key)
and prints one attention line per open PR, most-actionable first.

Why this exists alongside the jq classifier in ``pr-attention-sweep.sh``:
the jq path computes ``needs-reply`` as "any non-author comment/review is newer
than ours" — which fires on **CI bots** (copilot-pull-request-reviewer, codecov,
sonarqubecloud, …). Those are not maintainers and owe us nothing, so the jq
version reports false ``needs-reply`` flags every sweep (observed 2026-07-08:
cloudstack#13293/#13554 + hive#6535 all flagged purely on bot comments). This
script drops bot authors before the recency test, so ``needs-reply`` means a
*human* is genuinely waiting on us.

The ``needs-reply`` recency logic otherwise mirrors hard rule 7 for email:
whoever acted last owns the ball. "Our" activity = latest of our last commit,
our comments, our reviews; "their" activity = latest non-bot, non-us comment or
review. Flag when theirs is newer.

Usage:
    # from the sweep's output (default input ./prs.jsonl, or pass a path / '-'):
    pr-attention-analyze.py [PRS_JSONL] --me potiuk
    cat prs.jsonl | pr-attention-analyze.py - --me "$(gh api user --jq .login)"

    # extra project-specific bots, and only show PRs that need us:
    pr-attention-analyze.py prs.jsonl --me potiuk \
        --bot-extra myorg-ci --bot-extra release-drafter --needs-only

Flags emitted (a PR may carry several):
    pr-needs-reply           a human's comment/review is newer than our last activity
    pr-changes-requested     reviewDecision == CHANGES_REQUESTED
    pr-approved              reviewDecision == APPROVED (nudge-to-merge candidate)
    pr-conflict              mergeable == CONFLICTING
    pr-ci-failing            statusCheckRollup has any FAILURE/ERROR/TIMED_OUT/CANCELLED
    pr-draft                 isDraft
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# Substrings / suffixes that mark an author as automation rather than a human.
# GitHub App bots end in "[bot]"; the rest are CI/analysis integrations that
# comment via a user account without the "[bot]" suffix.
DEFAULT_BOT_MARKERS = (
    "[bot]",
    "asfgit",
    "github-actions",
    "codecov",
    "sonarqube",
    "sonarcloud",
    "copilot",
    "coderabbit",
    "dependabot",
    "renovate",
    "netlify",
    "vercel",
    "circleci",
    "travis",
    "gitpod",
)
# Whole-login patterns for CI-ish accounts (apache-*, *-ci, *-bot without [bot]).
DEFAULT_BOT_REGEXES = (r"^apache-", r"-ci$", r"-bot$", r"^ci$")


def make_is_bot(extra_markers, extra_regexes):
    markers = tuple(m.lower() for m in (*DEFAULT_BOT_MARKERS, *extra_markers))
    regexes = tuple(re.compile(r) for r in (*DEFAULT_BOT_REGEXES, *extra_regexes))

    def is_bot(login: str) -> bool:
        if not login:
            return True
        low = login.lower()
        if any(m in low for m in markers):
            return True
        return any(rx.search(low) for rx in regexes)

    return is_bot


def _login(obj) -> str:
    """Pull a login out of either {'author': {'login': x}} or {'login': x}."""
    if not isinstance(obj, dict):
        return ""
    a = obj.get("author")
    if isinstance(a, dict):
        return a.get("login") or ""
    return obj.get("login") or ""


def classify(pr: dict, me: str, is_bot) -> dict:
    """Return {repo, num, flags, their_who, their_when, their_gist, ci} for one PR."""
    repo = pr.get("_repo") or (pr.get("repository") or {}).get("nameWithOwner") or "?"
    num = pr.get("number")

    comments = pr.get("comments") or []
    reviews = pr.get("reviews") or []
    commits = pr.get("commits") or []

    ours, theirs = [], []  # (timestamp, who, body)
    for c in comments:
        who = _login(c)
        ts = c.get("createdAt") or ""
        body = (c.get("body") or "").strip()
        if who == me:
            ours.append((ts, who, body))
        elif not is_bot(who):
            theirs.append((ts, who, body))
    for r in reviews:
        who = _login(r)
        ts = r.get("submittedAt") or ""
        body = (r.get("body") or "").strip() or f"[{r.get('state')} review]"
        if who == me:
            ours.append((ts, who, body))
        elif not is_bot(who):
            theirs.append((ts, who, body))
    # our commits also count as "we acted"
    for cm in commits:
        cd = (
            (cm.get("commit") or {}).get("committedDate")
            or cm.get("committedDate")
            or ""
        )
        if cd:
            ours.append((cd, me, "[commit]"))

    our_last = max((t for t, _, _ in ours if t), default="")
    their = max((x for x in theirs if x[0]), default=None, key=lambda x: x[0])

    flags = []
    their_who = their_when = their_gist = ""
    if their and (not our_last or their[0] > our_last):
        flags.append("pr-needs-reply")
        their_when, their_who, their_gist = their[0], their[1], their[2][:180]

    rd = pr.get("reviewDecision")
    if rd == "CHANGES_REQUESTED":
        flags.append("pr-changes-requested")
    elif rd == "APPROVED":
        flags.append("pr-approved")
    if pr.get("mergeable") == "CONFLICTING":
        flags.append("pr-conflict")

    bad = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED"}
    ci_fail = [
        (ch.get("name") or ch.get("context") or "?")
        for ch in (pr.get("statusCheckRollup") or [])
        if ch.get("conclusion") in bad or ch.get("state") in bad
    ]
    if ci_fail:
        flags.append("pr-ci-failing")
    if pr.get("isDraft"):
        flags.append("pr-draft")

    return {
        "repo": repo,
        "num": num,
        "flags": flags,
        "their_who": their_who,
        "their_when": their_when,
        "their_gist": their_gist,
        "ci": ci_fail,
    }


# Sort key: most human-actionable first.
_PRIORITY = {
    "pr-needs-reply": 0,
    "pr-changes-requested": 1,
    "pr-conflict": 2,
    "pr-ci-failing": 3,
    "pr-approved": 4,
    "pr-draft": 5,
}


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "input",
        nargs="?",
        default="prs.jsonl",
        help="JSONL of gh pr view objects (default: prs.jsonl; '-' = stdin)",
    )
    ap.add_argument(
        "--me", required=True, help="operator's GitHub login (treated as 'us')"
    )
    ap.add_argument(
        "--bot-extra",
        action="append",
        default=[],
        help="extra bot-login substring (repeatable)",
    )
    ap.add_argument(
        "--bot-regex",
        action="append",
        default=[],
        help="extra whole-login bot regex (repeatable)",
    )
    ap.add_argument(
        "--needs-only",
        action="store_true",
        help="only print PRs that carry >=1 attention flag",
    )
    ap.add_argument(
        "--open-only",
        action="store_true",
        default=True,
        help="skip PRs whose state != OPEN (default on)",
    )
    ap.add_argument(
        "--all-states",
        dest="open_only",
        action="store_false",
        help="classify every PR regardless of state",
    )
    args = ap.parse_args()

    is_bot = make_is_bot(args.bot_extra, args.bot_regex)
    fh = sys.stdin if args.input == "-" else open(args.input)
    results = []
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            pr = json.loads(line)
            if args.open_only and pr.get("state") not in (None, "OPEN"):
                continue
            results.append(classify(pr, args.me, is_bot))

    def sortkey(r):
        best = min((_PRIORITY.get(f, 9) for f in r["flags"]), default=9)
        return (best, r["repo"], r["num"] or 0)

    results.sort(key=sortkey)
    needs_reply = []
    for r in results:
        if args.needs_only and not r["flags"]:
            continue
        tag = " ".join(r["flags"]) if r["flags"] else "clean(awaiting-them)"
        print(f"{r['repo']}#{r['num']}\t{tag}")
        if "pr-needs-reply" in r["flags"]:
            print(
                f"     -> {r['their_who']} @ {r['their_when'][:10]}: {r['their_gist']}"
            )
            needs_reply.append(r)
        if r["ci"]:
            print(f"     -> CI FAIL: {r['ci'][:6]}")

    print(
        f"\n=== pr-needs-reply (human waiting on us): {len(needs_reply)} ===",
        file=sys.stderr,
    )
    for r in needs_reply:
        print(
            f"{r['repo']}#{r['num']} — {r['their_who']} @ {r['their_when'][:10]}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
