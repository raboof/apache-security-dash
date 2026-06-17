#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""Stamp a filed report bundle with the model's disposition, or mark it tracked.

The deterministic half of the triage-assess SKILL. The model assesses a filed
report and decides the outcome; this helper does the mechanical part: write the
model's free-text fragments (summary / reason / note) into the bundle as their
own Markdown files and stamp the bundle's report.md front-matter. It renders no
templates and never sends.

Template rendering is owned entirely by inbox_manager, which applies the
templates at send time (when the live message, the operator identity, and the
PMC coordinates are all known). draft.py only supplies the *values*: the
free-text fragments as sibling files and the scalar decision data in the
front-matter. See templates/README.md for the marker contract.

Subcommands (all take a bundle <id>: a ponymail id or unique prefix):

  track <id>
      The report reached the PMC's own list (its security_contact or
      private@<pmc> is in To/Cc), so the Security team only tracks it. Writes
      no fragments. status: tracked.

  forward <id> --summary-file F --model M [--duplicate-of URL]
               [--reporter-note F] [--wf W]
      Plausible report. Writes summary.md (and note.md when --reporter-note is
      given), records model / duplicate_of in the front-matter. inbox_manager
      renders templates/forward.md (or forward-duplicate.md when duplicate_of
      is set) plus the reporter receipt at send time. status: drafted-forward.

  reply <id> (--reason TEXT | --body-file F) [--kind false-positive|hardening]
      High-confidence false-positive / hardening (or a known non-issue): writes
      reason.md, which inbox_manager renders through templates/reject.md at send
      time. status: drafted-reply.

We never use assertive language to the reporter: the PMC owns the final
non-issue / hardening / CVE call.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKILL_DIR.parents[2]
DEFAULT_CACHE = REPO_ROOT / "report-cache"
FALLBACK_CONTACT = "security@apache.org"

sys.path.insert(0, str(SKILL_DIR.parent / "triage-populate-cache"))
from report_md import BUNDLE_FILE, read as read_md, write as write_md  # noqa: E402

# Per-PMC security coordinates (security_contact) come from the whimsy-lookup
# tool, which reads apache/security-site's project-coordinates.json. draft.py
# needs them only for the `track` guard - to confirm the report really reached
# the PMC's own security contact. The forward path no longer needs them:
# inbox_manager derives the forward address from the PMC coordinates at send
# time, so draft.py records no recipient.
sys.path.insert(0, str(REPO_ROOT / "tools" / "whimsy_lookup" / "src"))
from whimsy_lookup.fetch import FetchError, fetch_security_coordinates  # noqa: E402
from whimsy_lookup.security_info import pmc_security_info  # noqa: E402


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def pmc_coords(pmc: str) -> dict:
    """The pmc_security_info record for a PMC, or {} on fetch failure / unknown."""
    if not pmc:
        return {}
    try:
        coordinates = fetch_security_coordinates()
    except FetchError as e:
        print(
            f"warning: could not fetch security coordinates ({e}); "
            "assuming central triage.",
            file=sys.stderr,
        )
        return {}
    return pmc_security_info(coordinates, pmc)


def find_bundle(cache: Path, ident: str) -> Path:
    """Locate a filed bundle (outside _inbox) by ponymail id or prefix."""
    ident = ident.strip()
    matches = []
    for bundle_file in cache.rglob(BUNDLE_FILE):
        if "_inbox" in bundle_file.parts:
            continue
        d = bundle_file.parent
        try:
            meta, _ = read_md(bundle_file)
        except (OSError, ValueError):
            continue
        pid = str(meta.get("ponymail_id") or "")
        if (
            d.name == ident
            or pid == ident
            or d.name.startswith(ident)
            or pid.startswith(ident)
        ):
            matches.append(d)
    if not matches:
        raise SystemExit(f"No filed bundle matching {ident!r}.")
    if len(matches) > 1:
        raise SystemExit(
            f"{ident!r} is ambiguous: {', '.join(d.name for d in matches)}"
        )
    return matches[0]


WF_MARKERS = ("reporter", "cve-allocation", "non-issue-feedback", "non-issue-docs")


def apply_wf(meta: dict, marker: str | None) -> None:
    """Set the workflow marker and append `wf <marker>` to the tag."""
    if not marker:
        return
    meta["wf"] = marker
    tag = meta.get("tag") or ""
    suffix = f"wf {marker}"
    if tag and suffix not in tag:
        meta["tag"] = f"{tag} {suffix}"


def save_meta(bundle: Path, meta: dict, body: str) -> None:
    write_md(bundle / BUNDLE_FILE, meta, body)


def do_track(bundle: Path, meta: dict, body: str, pmc: str, sc: str | None) -> int:
    """Mark a report the PMC already has (addressed to its own list)."""
    recipients = ((meta.get("to") or "") + " " + (meta.get("cc") or "")).lower()
    own = {f"private@{pmc}.apache.org"}
    if sc and sc != FALLBACK_CONTACT:
        own.add(sc.lower())
    hit = next((addr for addr in own if addr in recipients), None)
    if not hit:
        raise SystemExit(
            f"Refusing to track {bundle.name}: neither the PMC's security_contact "
            f"nor private@{pmc}.apache.org is in To/Cc "
            f"(to={meta.get('to')!r} cc={meta.get('cc')!r}). A report that reached "
            "only the central list needs triage even if the PMC runs its own team."
        )
    meta.update({"status": "tracked", "tracked_via": hit, "tracked_at": now()})
    save_meta(bundle, meta, body)
    print(f"{bundle.name}: tracked (addressed to {hit}); no fragments written.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("action", choices=["track", "forward", "reply"])
    ap.add_argument("id", help="Ponymail id or unique prefix of the filed bundle")
    ap.add_argument(
        "--summary-file", type=Path, help="forward: the model's PMC summary"
    )
    ap.add_argument(
        "--model", help="forward: the AI model that wrote the summary (disclaimer)"
    )
    ap.add_argument(
        "--duplicate-of",
        help="forward: link to the still-open report this duplicates "
        "(inbox_manager renders forward-duplicate.md)",
    )
    ap.add_argument(
        "--reporter-note",
        type=Path,
        help="forward: optional extra paragraph for the receipt",
    )
    ap.add_argument("--body-file", type=Path, help="reply: file with the reject reason")
    ap.add_argument(
        "--reason", help="reply: the reject reason inline (alternative to --body-file)"
    )
    ap.add_argument(
        "--wf",
        choices=WF_MARKERS,
        help="forward: workflow marker appended to the tag (e.g. cve-allocation)",
    )
    ap.add_argument(
        "--kind",
        choices=["false-positive", "hardening"],
        default="false-positive",
        help="reply: disposition recorded in meta",
    )
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    args = ap.parse_args()

    bundle = find_bundle(args.cache_dir, args.id)
    meta, body = read_md(bundle / BUNDLE_FILE)
    pmc = meta.get("pmc") or ""

    if args.action == "track":
        sc = pmc_coords(pmc).get("security_contact")
        return do_track(bundle, meta, body, pmc, sc)

    if args.action == "forward":
        if not args.summary_file:
            raise SystemExit("forward needs --summary-file")
        if not args.model:
            raise SystemExit(
                "forward needs --model (the AI model that wrote the summary)"
            )
        summary = args.summary_file.read_text(encoding="utf-8").strip()
        (bundle / "summary.md").write_text(summary + "\n", encoding="utf-8")
        if args.reporter_note:
            note = args.reporter_note.read_text(encoding="utf-8").strip()
            (bundle / "note.md").write_text(note + "\n", encoding="utf-8")

        meta.update(
            {
                "status": "drafted-forward",
                "decision": "forward",
                "model": args.model,
                "drafted_at": now(),
            }
        )
        if args.duplicate_of:
            meta["duplicate_of"] = args.duplicate_of
        apply_wf(meta, args.wf)
        save_meta(bundle, meta, body)
        kind = "forward-duplicate" if args.duplicate_of else "forward"
        wrote = "summary.md + note.md" if args.reporter_note else "summary.md"
        print(f"{bundle.name}: wrote {wrote} ({kind}); status drafted-forward.")
        return 0

    # reply
    reason = args.reason
    if not reason and args.body_file:
        reason = args.body_file.read_text(encoding="utf-8").strip()
    if not reason:
        raise SystemExit("reply needs --reason or --body-file")
    (bundle / "reason.md").write_text(reason + "\n", encoding="utf-8")
    meta.update({"status": "drafted-reply", "decision": args.kind, "drafted_at": now()})
    # A decline closes the report as a non-issue without forwarding to the PMC.
    # The zzz-non-issue/ tag prefix IS that classification (it sorts the report
    # out of the active queue), so it carries no wf marker.
    meta["wf"] = None
    tag = meta.get("tag") or ""
    if tag and not tag.startswith("zzz-non-issue/"):
        meta["tag"] = f"zzz-non-issue/{tag}"
    save_meta(bundle, meta, body)
    print(f"{bundle.name}: wrote reason.md ({args.kind}); status drafted-reply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
