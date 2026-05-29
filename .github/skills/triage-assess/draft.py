#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""Render triage drafts into a filed report bundle, or mark it tracked.

The deterministic half of the triage-assess SKILL. The model assesses a filed
report against the project's threat model + source and decides the outcome;
this helper does the mechanical part: fill the team templates, write the draft
Markdown files into the bundle, and stamp the bundle's report.md front-matter.
It never sends.

Subcommands (all take a bundle <id>: a ponymail id or unique prefix):

  track <id>
      The PMC is a specialized team (own security contact). Record that we
      only track it (status: tracked); write no drafts.

  forward <id> --summary-file F [--triager N] [--model M]
      Plausible report: render templates/forward.md (PMC name + the model's
      summary + AI-model disclaimer + triager) -> draft-forward.md, and
      templates/receipt.md (reporter ack) -> draft-receipt.md.
      status: drafted-forward.

  reply <id> --body-file F [--kind false-positive|hardening] [--triager N]
      High-confidence false-positive / hardening: write the model's
      non-assertive note to the reporter -> draft-reply.md.
      status: drafted-reply.

Drafts carry a leading HTML-comment header (To:/Subject:) for the human who
sends them; the body below is what gets sent. We never use assertive language
to the reporter: the PMC owns the final non-issue / hardening / CVE call.
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKILL_DIR.parents[2]
DEFAULT_CACHE = REPO_ROOT / "report-cache"
TEMPLATES = REPO_ROOT / "templates"
COORDINATES = SKILL_DIR / "coordinates.yaml"
DEFAULT_MODEL = "Claude Opus 4.7"

sys.path.insert(0, str(SKILL_DIR.parent / "triage-populate-cache"))
from report_md import BUNDLE_FILE, read as read_md, write as write_md  # noqa: E402

# A report is the PMC's own (track-only) iff it was addressed To: a per-PMC
# security@<pmc>.apache.org list. Reaching the central security@apache.org list
# means it needs triage, even when the PMC runs its own security team.
_PMC_IN_TO = re.compile(r"\bsecurity@([a-z0-9][a-z0-9-]*)\.apache\.org\b", re.I)


def per_pmc_addressee(meta: dict) -> str | None:
    """Return the per-PMC slug if the To header names a security@<pmc> list."""
    for m in _PMC_IN_TO.findall(meta.get("to") or ""):
        if m.lower() != "apache":
            return m.lower()
    return None


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def git_user_name() -> str:
    try:
        return subprocess.check_output(
            ["git", "config", "user.name"], text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def load_coordinates() -> dict:
    if COORDINATES.exists():
        return yaml.safe_load(COORDINATES.read_text()) or {}
    return {}


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
    text = (TEMPLATES / template_name).read_text(encoding="utf-8")
    for key, val in mapping.items():
        # Templates write placeholders as escaped markdown, e.g. `\<summary>`.
        text = text.replace(f"\\<{key}>", val).replace(f"<{key}>", val)
    return text


def header(to: str, subject: str) -> str:
    return (
        "<!-- DRAFT for human review — not sent automatically.\n"
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


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("action", choices=["track", "forward", "reply"])
    ap.add_argument("id", help="Ponymail id or unique prefix of the filed bundle")
    ap.add_argument(
        "--summary-file", type=Path, help="forward: the model's PMC summary"
    )
    ap.add_argument("--body-file", type=Path, help="reply: the model's reporter note")
    ap.add_argument(
        "--reporter-note",
        type=Path,
        help="forward: extra paragraph for the receipt (e.g. a likely-non-issue hint)",
    )
    ap.add_argument(
        "--wf",
        choices=WF_MARKERS,
        help="workflow marker appended to the tag (e.g. non-issue-feedback)",
    )
    ap.add_argument(
        "--kind",
        choices=["false-positive", "hardening"],
        default="false-positive",
        help="reply: disposition recorded in meta",
    )
    ap.add_argument(
        "--triager", default=None, help="Triager full name (default: git user.name)"
    )
    ap.add_argument(
        "--model", default=DEFAULT_MODEL, help="AI model for the forward disclaimer"
    )
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    args = ap.parse_args()

    bundle = find_bundle(args.cache_dir, args.id)
    meta, body = read_md(bundle / BUNDLE_FILE)
    pmc = meta.get("pmc") or ""
    coords = load_coordinates().get(pmc, {})
    pmc_name = coords.get("name") or (f"Apache {pmc.title()}" if pmc else "the project")
    subject = meta.get("subject") or "(no subject)"
    triager = args.triager or git_user_name() or "the Apache Security Team"

    if args.action == "track":
        addressee = per_pmc_addressee(meta)
        if not addressee:
            raise SystemExit(
                f"Refusing to track {bundle.name}: To is {meta.get('to')!r}, not a "
                "per-PMC security@<pmc> list. A report on the central list needs "
                "triage even if the PMC runs its own team — assess and draft instead."
            )
        meta["status"] = "tracked"
        meta["tracked_via"] = f"security@{addressee}.apache.org"
        meta["tracked_at"] = now()
        save_meta(bundle, meta, body)
        print(
            f"{bundle.name}: tracked (sent to security@{addressee}.apache.org); "
            "no drafts written."
        )
        return 0

    if args.action == "forward":
        if not args.summary_file:
            raise SystemExit("forward needs --summary-file")
        summary = args.summary_file.read_text(encoding="utf-8").strip()
        # A PMC that runs its own security team (specialized) gets the report at
        # its own address, and the reporter is pointed there for follow-up; a
        # centrally-handled PMC gets it on its private@ list.
        specialized = bool(coords.get("specialized"))
        pmc_address = coords.get("contact") or f"security@{pmc}.apache.org"
        fwd_to = pmc_address if specialized else f"private@{pmc}.apache.org"
        fwd = header(f"{fwd_to}  (verify the PMC list)", f"Fwd: {subject}")
        fwd += render(
            "forward.md",
            {
                "PMC name": pmc_name,
                "summary": summary,
                "model": args.model,
                "Triager full name": triager,
            },
        )
        (bundle / "draft-forward.md").write_text(fwd, encoding="utf-8")
        note = (
            args.reporter_note.read_text(encoding="utf-8").strip()
            if args.reporter_note
            else ""
        )
        rcpt = header(meta.get("reporter") or "(reporter)", f"Re: {subject}")
        rcpt += render(
            "receipt-specialized.md" if specialized else "receipt.md",
            {
                "Reporter name": meta.get("reporter_name") or "there",
                "PMC name": pmc_name,
                "PMC security address": pmc_address,
                "note": note,
                "Triager full name": triager,
            },
        )
        rcpt = re.sub(r"\n{3,}", "\n\n", rcpt)  # collapse the gap if note is empty
        (bundle / "draft-receipt.md").write_text(rcpt, encoding="utf-8")
        meta.update(
            {
                "status": "drafted-forward",
                "decision": "forward",
                "forwarded_to": fwd_to,
                "triager": triager,
                "model": args.model,
                "drafted_at": now(),
            }
        )
        apply_wf(meta, args.wf)
        save_meta(bundle, meta, body)
        print(
            f"{bundle.name}: wrote draft-forward.md + draft-receipt.md "
            f"(to {pmc_name}); status drafted-forward."
        )
        return 0

    # reply
    if not args.body_file:
        raise SystemExit("reply needs --body-file")
    reply_body = args.body_file.read_text(encoding="utf-8").strip()
    name = meta.get("reporter_name") or "there"
    out = header(meta.get("reporter") or "(reporter)", f"Re: {subject}")
    out += f"Hi {name},\n\n{reply_body}\n\nBest regards,\n\n{triager}\n"
    (bundle / "draft-reply.md").write_text(out, encoding="utf-8")
    meta.update(
        {
            "status": "drafted-reply",
            "decision": args.kind,
            "triager": triager,
            "drafted_at": now(),
        }
    )
    # A push-back closes the report as a non-issue without forwarding to the
    # PMC. The zzz-non-issue/ tag prefix IS that classification (it sorts the
    # report out of the active queue, zzz- sorts last), so it carries no wf
    # marker. If we ever both reply and forward, the prefix would not apply.
    meta["wf"] = None
    tag = meta.get("tag") or ""
    if tag and not tag.startswith("zzz-non-issue/"):
        meta["tag"] = f"zzz-non-issue/{tag}"
    save_meta(bundle, meta, body)
    print(f"{bundle.name}: wrote draft-reply.md ({args.kind}); status drafted-reply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
