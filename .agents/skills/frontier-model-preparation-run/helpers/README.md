<!-- SPDX-License-Identifier: Apache-2.0 -->

# frontier-model-preparation-run helpers

Deterministic shell helpers for the periodic FMP/Glasswing sweep, extracted from
repeated real-run friction so the next sweep doesn't re-hit it. All of them must
run **outside the sandbox** (`dangerouslyDisableSandbox`) because they need host
credentials the sandbox hides (the `gh` keyring, the sheets OAuth token).

| Script | Does | Sweep step |
|---|---|---|
| [`pr-attention-sweep.sh`](pr-attention-sweep.sh) | Every open operator PR → attention flags (changes-requested / approved-awaiting-merge / conflict / ci-failing / needs-reply / draft). | Step 3 |
| [`pr-fetch-one.sh`](pr-fetch-one.sh) | Worker: one PR → one JSON file. Invoked by the sweep via `xargs`. | Step 3 |
| [`sheet-dump.sh`](sheet-dump.sh) | Untruncated PMCs-sheet dump as JSON objects (via Sheets API, not the Drive MCP). | Step 2 |

```bash
# Step 3 — PRs waiting on us:
.agents/skills/frontier-model-preparation-run/helpers/pr-attention-sweep.sh

# Step 2 — every Scan-Requested=Yes row, key columns:
.agents/skills/frontier-model-preparation-run/helpers/sheet-dump.sh PMCs \
  | jq -r 'select((."Scan Requested"|ascii_downcase)=="yes")
           | [.PMC, ."Security model verified", ."Date scan requested", ."Date scan received"] | @tsv'
```

## Gotchas these scripts encode (read before writing your own sweep glue)

1. **zsh mangles `!` — even inside a single-quoted heredoc.** `awk`/`python`
   programs containing `!=` arrive as `\!=` and die with a syntax error. The
   `<<'EOF'` trick does **not** save you here (the mangle happens before the
   heredoc is parsed). Do analysis in **jq**, or write the program to a file with
   the editor and run it with `-f` / as a module — never inline a `!` program.

2. **`gh` inside `while read … done < file` swallows the loop's stdin.** `gh`
   reads stdin, consuming the remaining URLs, so the loop "runs once then hangs."
   Always feed it `gh … </dev/null`.

3. **`gh pr view` latency is wildly variable (0.8s … >30s).** A serial loop over
   ~40 PRs blows any tool timeout. Fan out with `xargs -P 8`, one output file per
   PR (concurrent appends to one file interleave). `statusCheckRollup` is the
   slow field — worst on the big-CI repos.

4. **macOS `xargs` cannot assemble a long inline `bash -c`** ("command line
   cannot be assembled, too long"). The per-item worker must be a **file**
   (`pr-fetch-one.sh`), invoked as `xargs -I{} worker.sh {} …`.

5. **The sheets OAuth refresh writes a sandbox-denied path.** `sheets-writer`
   rewrites `~/.config/asf-security/glasswing/token.json` on every run;
   sandboxed, that is `Operation not permitted`. Run `sheet-dump.sh` unsandboxed.

6. **`/tmp/claude` is not reliably persistent between tool calls.** Use
   `$TMPDIR` (the session scratchpad) or an explicit OUTDIR you control.

7. **Gmail `search_threads` snippets are stale for long threads.** It returns the
   *first* ~5 messages, not the newest, so `messages[-1]` lies for any thread at
   the cap. Resolve the true latest message per changed thread with `get_thread`
   (MINIMAL). `is:unread` is not a safe "awaiting us" proxy either — the operator
   reads mail in the UI without actioning it. (MCP-side; no shell helper.)
