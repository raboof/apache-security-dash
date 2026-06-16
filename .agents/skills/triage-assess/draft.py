#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""Render triage drafts into a filed report bundle, or mark it tracked.

The deterministic half of the triage-assess SKILL. The model assesses a filed
report and decides the outcome; this helper does the mechanical part: pick the
right template, fill the *content* markers the model authored, write the draft
Markdown into the bundle, and stamp the bundle's report.md front-matter. It
never sends.

draft.py fills ONLY the content markers (<summary>, <reason>, <note>, <model>,
<duplicate>). Every identity / PMC / infra marker (<PMC name>, <Reporter name>,
<Triager full name>, <link>, <model link>, <contributing link>,
<dashboard link>, <PMC security address>) is left in place for inbox_manager to
fill at send time; inbox_manager drops any line whose marker stays empty. See
templates/README.md for the full marker contract.

Subcommands (all take a bundle <id>: a ponymail id or unique prefix):

  track <id>
      The report reached the PMC's own list (its security_contact or
      private@<pmc> is in To/Cc), so the Security team only tracks it. Writes
      no drafts. status: tracked.

  forward <id> --summary-file F --model M [--duplicate-of URL]
               [--reporter-note F] [--wf W]
      Plausible report. Renders templates/forward.md (or forward-duplicate.md
      when --duplicate-of is given) -> draft-forward.md, plus a reporter
      receipt (receipt-specialized.md for a specialized PMC, else receipt.md)
      -> draft-receipt.md. status: drafted-forward.

  reply <id> (--reason TEXT | --body-file F) [--kind false-positive|hardening]
      High-confidence false-positive / hardening (or a known non-issue):
      renders templates/reject.md -> draft-reply.md. status: drafted-reply.

Drafts carry a leading HTML-comment header (To:/Subject:) as a hint for the
sender; the body below is what gets sent. We never use assertive language to
the reporter: the PMC owns the final non-issue / hardening / CVE call.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKILL_DIR.parents[2]
DEFAULT_CACHE = REPO_ROOT / "report-cache"
TEMPLATES = REPO_ROOT / "templates"
FALLBACK_CONTACT = "security@apache.org"

sys.path.insert(0, str(SKILL_DIR.parent / "triage-populate-cache"))
from report_md import BUNDLE_FILE, read as read_md, write as write_md  # noqa: E402

# Per-PMC security coordinates (security_contact, threat-model link) come from
# the whimsy-lookup tool, which reads apache/security-site's
# project-coordinates.json. draft.py needs them only to tell a specialized PMC
# from a centrally-handled one (which receipt template + where the forward
# routes); inbox_manager fills the PMC markers in the drafts at send time.
sys.path.insert(0, str(REPO_ROOT / "tools" / "whimsy_lookup" / "src"))
from whimsy_lookup.fetch import FetchError, fetch_security_coordinates  # noqa: E402
from whimsy_lookup.security_info import pmc_security_info  # noqa: E402


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def pmc_coords(pmc: str) -> dict:
    """The pmc_security_info record for a PMC, or {} on fetch failure / unknown.

    {} (or a foundation-wide fallback contact) means the PMC is treated as
    centrally handled: the forward goes to private@<pmc> and the plain receipt
    is used.
    """
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


def render(template_name: str, mapping: dict[str, str]) -> str:
    """Fill the given markers in a template, leaving the rest for inbox_manager.

    Markers are written escaped (``\\<key>``) in the templates; we replace both
    the escaped and bare forms for the keys we own, and leave every other
    marker untouched so inbox_manager fills (or line-drops) it at send time.
    """
    text = (TEMPLATES / template_name).read_text(encoding="utf-8")
    for key, val in mapping.items():
        text = text.replace(f"\\<{key}>", val).replace(f"<{key}>", val)
    return text


def header(to: str, subject: str) -> str:
    return (
        "<!-- DRAFT for human review (not sent automatically).\n"
        f"To: {to}\n"
        f"Subject: {subject}\n"
        "-->\n\n"
    )


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
    print(f"{bundle.name}: tracked (addressed to {hit}); no drafts written.")
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
        "(renders forward-duplicate.md)",
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
    coords = pmc_coords(pmc)
    sc = coords.get("security_contact")
    specialized = bool(sc and sc != FALLBACK_CONTACT)
    subject = meta.get("subject") or "(no subject)"
    reporter = meta.get("reporter") or "(reporter)"

    if args.action == "track":
        return do_track(bundle, meta, body, pmc, sc)

    if args.action == "forward":
        if not args.summary_file:
            raise SystemExit("forward needs --summary-file")
        if not args.model:
            raise SystemExit(
                "forward needs --model (the AI model that wrote the summary)"
            )
        summary = args.summary_file.read_text(encoding="utf-8").strip()
        fwd_to = sc if specialized else f"private@{pmc}.apache.org"

        if args.duplicate_of:
            fwd_body = render(
                "forward-duplicate.md",
                {
                    "summary": summary,
                    "model": args.model,
                    "duplicate": args.duplicate_of,
                },
            )
        else:
            fwd_body = render("forward.md", {"summary": summary, "model": args.model})
        fwd = header(f"{fwd_to}  (verify the PMC list)", f"Fwd: {subject}") + fwd_body
        (bundle / "draft-forward.md").write_text(fwd, encoding="utf-8")

        receipt_map: dict[str, str] = {}
        if args.reporter_note:
            receipt_map["note"] = args.reporter_note.read_text(encoding="utf-8").strip()
        receipt_tmpl = "receipt-specialized.md" if specialized else "receipt.md"
        rcpt = header(reporter, f"Re: {subject}") + render(receipt_tmpl, receipt_map)
        (bundle / "draft-receipt.md").write_text(rcpt, encoding="utf-8")

        meta.update(
            {
                "status": "drafted-forward",
                "decision": "forward",
                "forwarded_to": fwd_to,
                "model": args.model,
                "drafted_at": now(),
            }
        )
        apply_wf(meta, args.wf)
        save_meta(bundle, meta, body)
        kind = "forward-duplicate" if args.duplicate_of else "forward"
        print(
            f"{bundle.name}: wrote draft-forward.md ({kind}) + draft-receipt.md; "
            "status drafted-forward."
        )
        return 0

    # reply
    reason = args.reason
    if not reason and args.body_file:
        reason = args.body_file.read_text(encoding="utf-8").strip()
    if not reason:
        raise SystemExit("reply needs --reason or --body-file")
    out = header(reporter, f"Re: {subject}") + render("reject.md", {"reason": reason})
    (bundle / "draft-reply.md").write_text(out, encoding="utf-8")
    meta.update({"status": "drafted-reply", "decision": args.kind, "drafted_at": now()})
    # A decline closes the report as a non-issue without forwarding to the PMC.
    # The zzz-non-issue/ tag prefix IS that classification (it sorts the report
    # out of the active queue), so it carries no wf marker.
    meta["wf"] = None
    tag = meta.get("tag") or ""
    if tag and not tag.startswith("zzz-non-issue/"):
        meta["tag"] = f"zzz-non-issue/{tag}"
    save_meta(bundle, meta, body)
    print(f"{bundle.name}: wrote draft-reply.md ({args.kind}); status drafted-reply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
