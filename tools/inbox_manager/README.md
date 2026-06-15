# inbox-manager

The credentialed **send + archive** stage of the report-triage pipeline.

`triage-populate-cache` downloads each inbound report from `security@apache.org`
into `report-cache/<date>/<pmc>/<keywords>/` (read-only Gmail API), and
`triage-assess` then assesses it and writes the response drafts
(`draft-forward.md`, `draft-receipt.md`, `draft-reply.md`) plus a disposition in
the bundle's `report.md` front-matter. Neither of those skills holds
write credentials.

This utility presents the live security inbox and, for each message, looks up
its bundle in `report-cache/` by RFC `Message-ID`. When the triage skills have
already dispositioned it, the operator just reviews the ready drafts and the
tool sends them (forward to the PMC + receipt to the reporter, or a push-back
reply) and files the message under the cache's own label. It runs **directly**
(not via an agent): this is the last human review before taking external actions
with credentials that are only exposed to deterministic code, so every send and
every mailbox move is operator-confirmed (`[y]/[n]/[e]dit`).

## What it does with the cache

Per inbox message, it dispatches on the bundle's `status`:

- `drafted-forward` - forward the `draft-forward.md` covering note to the PMC
  (`forwarded_to`) and send the `draft-receipt.md` acknowledgement to the
  reporter, then attach the cache labels and archive.
- `drafted-reply` - send the `draft-reply.md` push-back to the reporter, then
  attach the cache labels and archive.
- `tracked` / open-reports `digest` / known non-issue - nothing to send; attach
  the cache labels and archive.
- `spam` - offer to junk it (move to Spam).
- not in the cache, or filed but not yet assessed - fall back to the original
  fully-interactive triage (guess the PMC, build the forward/receipt/reply from
  the team templates).

A report already in the cache is surfaced even when the header heuristics would
otherwise skip it (e.g. a fresh report Gmail merged into an older thread).

## Attaching the cache labels to Gmail

A Gmail message carries many labels, but only the ones already on it live in
Gmail; the bundle's `tags` is the full set the triage tools recorded. For every
disposition that files/archives (all of the above except `spam`), `inbox_manager`
fetches the message's current Gmail labels, lists the ones in `tags` that are
**missing**, and on confirmation adds them (creating the label if needed) and
archives the message by dropping `\Inbox`. This is what puts every covered
report's label on a **digest** message (its `tags` is that whole set), and what
applies a report's own tag when it is forwarded, replied to, or tracked. The
next `populate-cache` reconcile then sweeps the archived bundle into `handled/`.

## Markdown rendering

The drafts and the team templates are Markdown; outgoing mail is sent as
multipart/alternative. `markdown_render.py` renders one parse two ways: an HTML
part (sanitised through the same nh3 allowlist used for forwarded content) and a
plain-text part wrapped to 78 columns, with `[text](url)` links turned into
numbered `text[n]` references and a `[n] <url>` footnote block at the end.
`[e]dit` edits the Markdown source and re-renders, so both parts stay in sync.

## Configuration

- `TRIAGER_NAME` / `TRIAGER_EMAIL` - operator identity used to sign and address
  forwards (required).
- `APACHE_USER` / `APACHE_PASS` - mail-relay SMTP credentials for sending.
- `GMAIL_READWRITE_OAUTH_*` - OAuth for the read/write IMAP inbox (it moves,
  files and junks messages); see `imap.py`. Distinct from populate_cache's
  read-only Gmail API token (`GMAIL_READONLY_OAUTH_*`).
- `REPORT_CACHE_DIR` - cache root (default: the repo's `report-cache/`). If the
  cache is absent every message falls back to interactive triage.

```bash
uv run --project tools/inbox_manager inbox-manager
```
