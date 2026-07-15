---
name: frontier-model-preparation-dashboard
description: >-
  Refresh the Frontier Model Preparation program-totals dashboard.
  Running `sheets-writer build-status-tab` rebuilds the tracker's five tabs (Status in progress, Program totals, Completed, Timeline, README) AND overwrites a single private GitHub gist that mirrors the Program-totals tables + the PMC funnel as a markdown dashboard.
  The gist is created on first run, overwritten on every run after,
  and its URL is kept in the operator's config (`~/.config/asf-security/glasswing/dashboard_gist.json`).
  Invoke when asked to "refresh the dashboard", "update the program totals", or after any change that moves the tracker (a submit, a forward, a model verification).
  Only aggregate counts go to the gist —
  never PMC names, individual data, or the program's cost mechanics.
---

# Frontier Model Preparation dashboard SKILL

Keeps an at-a-glance dashboard of the Frontier Model Preparation program in sync with the tracker.
There are two surfaces and they update together:

1. The **live spreadsheet** (`Program totals` tab) —
   interactive, with the funnel bar chart and the funnel-over-time stacked chart.
2. A **private gist** —
   a markdown rendering of the same Program-totals tables plus a Unicode funnel chart,
   so the numbers can be linked/read without opening Sheets.
   One gist, overwritten in place each run.

Both are produced by a single command:

```bash
uv run --project tools/sheets_writer sheets-writer build-status-tab \
  --spreadsheet-id <MYTHOS_SHEET_ID>
```

That command rebuilds the five tabs and then pushes the dashboard to the gist.
The gist URL is printed and stored in `~/.config/asf-security/glasswing/dashboard_gist.json`.

## When to invoke

- The operator asks to "refresh the dashboard" / "update program totals".
- After any pipeline-moving action (a `frontier-model-preparation-submit`, a `frontier-model-preparation-forward`, a `frontier-model-preparation-model-verify` flip) —
  the dashboard should reflect it.
- As the read-out step of a `frontier-model-preparation-run` sweep.

Skip if the tracker hasn't changed since the last refresh and the operator only wants to *read* the numbers —
point them at the existing gist URL in the config file instead.

## Hard rules

1. **Aggregate-only in the gist.** The dashboard contains counts and percentages (PMCs opted in, repos submitted, PRs, model origins, the funnel).
   It must never contain PMC names, individual contacts, repo lists, email content, or anything identifying a specific project.
   The renderer (`tools/sheets_writer/.../dashboard.py`) is built to emit only aggregates;
   do not extend it to include per-PMC rows.

2. **No program-cost mechanics.** Same program-cost-confidentiality rule as the other Frontier Model Preparation SKILLs —
   the gist must not include the program's cost mechanics (the $1M credit value, per-MTok pricing, or seat/provisioning details).
   The Frontier Model Preparation program name, Mythos / Mythos-5, and ASF Tooling (the runner) are all fine to name; only the cost mechanics stay out.

3. **Private (secret) gist, single instance.** The gist is created with `public: false`.
   There is exactly one dashboard gist;
   every run overwrites it via its stored id rather than creating a new one.
   If the config file is deleted, the next run creates a fresh gist —
   delete the old one on GitHub if so, to avoid a stale orphan.

4. **The gist is a side channel, never the source of truth.** The spreadsheet is authoritative.
   A gist-push failure (e.g. `gh` not authenticated) is a warning, not an error —
   the sheet refresh still succeeds.
   If the warning appears, run `gh auth status` and re-run.

5. **Preview before the first publish.** On the very first run (no gist yet),
   show the operator the rendered markdown (`--dry-run` prints it without pushing) and confirm before creating the public-to-anyone-with-the-link gist.
   Later overwrites don't need re-confirmation —
   the operator opted into "update it every time we update the sheet".

## Mechanics

- **Preview without publishing:** `build-status-tab ... --dry-run` prints the dashboard markdown under a clearly marked banner and pushes nothing.
- **Refresh (sheet + gist):** `build-status-tab ...` (no `--dry-run`).
  Requires the Google OAuth token (`~/.config/asf-security/glasswing/`) for the sheet and an authenticated `gh` for the gist.
- **Config:** `~/.config/asf-security/glasswing/dashboard_gist.json` holds `{"gist_id": "...", "url": "..."}`.
  To re-point at a different gist, edit or delete this file.

The sheet id lives in user-scope memory (`mythos-tracker`), not in this repo.
