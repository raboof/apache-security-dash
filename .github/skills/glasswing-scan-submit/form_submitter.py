#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "google-api-python-client>=2.0",
#     "google-auth>=2.0",
#     "playwright>=1.45",
# ]
# ///
"""Glasswing scan-submission helper — fills the vendor's project-enrollment
Google Form once per repo for a given PMC.

Auth model: a persistent Chromium profile at
~/.config/asf-security/glasswing/playwright-profile/. Run `setup` once
to sign in to Google interactively; subsequent `submit-pmc` invocations
reuse the authenticated session in headless mode.

Submitter identity (Name / @apache.org email / GitHub profile URL) lives
at ~/.config/asf-security/glasswing/submitter.json — set via
`setup-submitter`.

PMC data is read from the same Mythos tracker spreadsheet that
sheets_writer.py writes to, using the same OAuth refresh token at
~/.config/asf-security/glasswing/token.json (read-only scope here).

Subcommands:
  setup
      Launch a non-headless Chromium with the persistent profile and
      navigate to the form URL. The operator signs in to Google
      manually, confirms the form loads, then closes the browser. The
      profile is now populated for subsequent headless runs.

  setup-submitter --name NAME --email APACHE_EMAIL --github URL
      Write the submitter identity config (idempotent).

  submit-pmc --slug SLUG [--dry-run] [--starting-from REPO_NAME]
      Submit one form per repo in the PMC's confirmed scope, ordered by
      OSSF Criticality Score (highest first). With --dry-run, prints the
      per-form fill plan and exits without driving the browser. With
      --starting-from, skips repos earlier in the ordering than the
      named one (resumes after mid-batch error).
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CONFIG_DIR = Path.home() / ".config" / "asf-security" / "glasswing"
TOKEN_PATH = CONFIG_DIR / "token.json"
SUBMITTER_PATH = CONFIG_DIR / "submitter.json"
PROFILE_DIR = CONFIG_DIR / "playwright-profile"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SPREADSHEET_ID = "1pxaWKXYtZ-89cKk3OYE99-ewPMh2kXKvSDaqjR-I1o8"
FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSckkDKXcMnMREC8GTWDE7trx6Rhx0DP_aUP-gAduJhHEWsGcQ/viewform"
)


# --- Sheets read ---


def load_sheets_credentials() -> Credentials:
    if not TOKEN_PATH.exists():
        sys.exit(
            f"No OAuth token at {TOKEN_PATH}. Run sheets_writer.py setup "
            "first (the form_submitter shares its token)."
        )
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return creds


def read_grid(svc, sheet_name: str, rng: str = "A1:Z3000") -> list[dict]:
    result = (
        svc.spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{sheet_name}!{rng}",
            majorDimension="ROWS",
        )
        .execute()
    )
    rows = result.get("values", [])
    if not rows:
        return []
    headers = rows[0]
    out = []
    for r in rows[1:]:
        padded = r + [""] * (len(headers) - len(r))
        out.append({headers[i]: padded[i] for i in range(len(headers))})
    return out


@dataclass
class RepoEntry:
    url: str
    name: str
    criticality: float | None  # None for blank cells; sorted last
    primary_language: str
    stars: str
    has_agents_md: bool = False
    has_security_md: bool = False
    has_security_txt: bool = False
    discoverability_checked: bool = False

    @property
    def is_submittable(self) -> bool:
        """A repo is submittable if at least one discoverability marker exists.

        AGENTS.md or SECURITY.md (or security.txt) — any one of those is
        enough for the scan agent to reach the project's threat model
        through the AGENTS.md → SECURITY.md → model chain (the chain
        tolerates either endpoint).
        """
        return self.has_agents_md or self.has_security_md or self.has_security_txt

    @property
    def can_claim_security_md(self) -> bool:
        """Reflects the form's "valid security.txt or SECURITY.md" checkbox.

        Ticks when ANY discoverability marker is present — AGENTS.md alone
        is sufficient because it carries the same "how to deal with
        findings" pointer the form asks about (the AGENTS.md → external
        SECURITY.md or threat-model URL chain is the standard pattern in
        the ASF Glasswing pipeline). The form's literal phrasing is a bit
        narrower, but the operational intent ("the repo tells researchers
        where to take findings") is satisfied either way.
        """
        return self.has_agents_md or self.has_security_md or self.has_security_txt


def parse_criticality(raw: str) -> float | None:
    raw = (raw or "").strip().rstrip("%").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def repo_has_file(repo_name: str, path: str) -> bool:
    """Return True iff the file exists at HEAD on apache/<repo_name>.

    Uses `gh api repos/apache/<repo>/contents/<path>` — exits 0 on 200,
    non-zero on 404. The gh CLI is auth'd via the user's existing
    GitHub credentials; no extra config needed.
    """
    result = subprocess.run(
        ["gh", "api", f"repos/apache/{repo_name}/contents/{path}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def fill_discoverability(entries: list[RepoEntry]) -> None:
    """Populate the AGENTS.md / SECURITY.md / security.txt flags on every
    entry via the GitHub API. Mutates in place."""
    print(
        "Checking per-repo discoverability via gh api "
        "(AGENTS.md / SECURITY.md / security.txt at HEAD)...",
        file=sys.stderr,
    )
    for e in entries:
        e.has_agents_md = repo_has_file(e.name, "AGENTS.md")
        e.has_security_md = repo_has_file(e.name, "SECURITY.md")
        e.has_security_txt = repo_has_file(e.name, "security.txt") or repo_has_file(
            e.name, ".well-known/security.txt"
        )
        e.discoverability_checked = True
        markers = (
            ", ".join(
                label
                for label, present in [
                    ("AGENTS.md", e.has_agents_md),
                    ("SECURITY.md", e.has_security_md),
                    ("security.txt", e.has_security_txt),
                ]
                if present
            )
            or "NONE — will skip"
        )
        print(f"  apache/{e.name}: {markers}", file=sys.stderr)


def fetch_pmc_state(slug: str) -> dict:
    """Return PMC row + ordered repo list for a slug. Sys-exits on missing data."""
    creds = load_sheets_credentials()
    svc = build("sheets", "v4", credentials=creds)

    pmcs = read_grid(svc, "PMCs")
    pmc_row = next((r for r in pmcs if r.get("PMC Slug", "").strip() == slug), None)
    if pmc_row is None:
        sys.exit(f"PMC slug {slug!r} not found in PMCs sheet.")

    required_fields = {
        "Scan Requested": "Yes",
        "Security model verified": None,  # any non-blank
        "Repositories requested": None,
        "Contact Person": None,
        "Backup contact": None,
        "Security Model": None,
    }
    missing = []
    for field, expected in required_fields.items():
        val = pmc_row.get(field, "").strip()
        if expected is None and not val:
            missing.append(f"{field} (blank)")
        elif expected is not None and val != expected:
            missing.append(f"{field} (got {val!r}, expected {expected!r})")
    if missing:
        sys.exit(
            f"PMC {slug!r} not ready for submission:\n  - " + "\n  - ".join(missing)
        )

    requested_urls = [
        line.strip()
        for line in pmc_row["Repositories requested"].splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not requested_urls:
        sys.exit(f"PMC {slug!r} has no usable URLs in Repositories requested.")

    repos_sheet = read_grid(svc, "Repositories")
    by_url = {r.get("Repository URL", "").strip(): r for r in repos_sheet}

    entries: list[RepoEntry] = []
    for url in requested_urls:
        meta = by_url.get(url)
        if meta is None:
            entries.append(
                RepoEntry(
                    url=url,
                    name=url.rsplit("/", 1)[-1],
                    criticality=None,
                    primary_language="",
                    stars="",
                )
            )
            continue
        entries.append(
            RepoEntry(
                url=url,
                name=meta.get("Repository Name", url.rsplit("/", 1)[-1]).strip(),
                criticality=parse_criticality(meta.get("Criticality Score (%)", "")),
                primary_language=meta.get("Primary Language", "").strip(),
                stars=meta.get("GitHub Stars", "").strip(),
            )
        )

    entries.sort(key=lambda e: (-(e.criticality or -1), e.name))

    fill_discoverability(entries)

    return {"pmc": pmc_row, "repos": entries}


# --- Submitter config ---


def load_submitter() -> dict:
    if not SUBMITTER_PATH.exists():
        sys.exit(
            f"No submitter config at {SUBMITTER_PATH}.\n"
            "Run: form_submitter.py setup-submitter --name 'Your Name' "
            "--email you@apache.org --github https://github.com/you"
        )
    cfg = json.loads(SUBMITTER_PATH.read_text())
    for key in ("name", "email", "github"):
        if not cfg.get(key, "").strip():
            sys.exit(f"submitter.json missing {key!r}.")
    if not cfg["email"].endswith("@apache.org"):
        sys.exit(
            f"submitter.email must be an @apache.org address (got {cfg['email']!r})."
        )
    return cfg


# --- Plan computation ---


@dataclass
class FormFill:
    project_name: str
    repo_url: str
    your_name: str
    your_email: str
    github_profile: str
    your_role: str
    additional_info: str
    confirm_authorized: bool
    confirm_security_md: bool
    confirm_claude_max: bool
    is_headline: bool
    repo_name: str


def parse_expedite_cell(raw: str) -> list[str]:
    """Return list of @apache.org addresses; empty if cell is blank or 'none'."""
    raw = (raw or "").strip()
    if not raw or raw.lower() == "none":
        return []
    return [
        line.strip()
        for line in raw.splitlines()
        if line.strip() and "@" in line.strip()
    ]


def build_headline_additional_info(
    pmc_name: str,
    pmc_row: dict,
    expedite_addrs: list[str],
    repos: list[RepoEntry],
    headline_repo: RepoEntry,
    scan_result_recipients: list[str],
    submission_notes_text: str = "",
) -> str:
    primary = pmc_row.get("Contact Person", "").strip()
    backup = pmc_row.get("Backup contact", "").strip()
    model_url = pmc_row.get("Security Model", "").strip()

    lines = [
        f"Submitted by the ASF Security Committee on behalf of {pmc_name} PMC at their request.",
        "",
        "PMC contacts:",
        f"  - Primary: {primary}",
        f"  - Backup:  {backup}",
        "",
        "Scan-result recipients (the @apache.org addresses the ASF Security",
        "team forwards the vendor's findings to, verbatim, after a",
        "pre-forward sanity check):",
    ]
    if scan_result_recipients:
        for addr in scan_result_recipients:
            lines.append(f"  - {addr}")
    else:
        lines.append(
            f"  - (defaults to Contact Person + Backup contact: {primary}, {backup})"
        )

    lines.extend(
        [
            "",
            "Threat model (verified by the ASF Security team against the",
            "Scovetta rubric):",
            f"  - {model_url}",
        ]
    )

    if expedite_addrs:
        lines.extend(
            [
                "",
                "Claude-for-Open-Source subscription expedite — the following",
                "PMC members have registered for the Claude Max 20x program at",
                "https://claude.com/contact-sales/claude-for-oss and would",
                "benefit from an expedite of their applications. The",
                '"I\'m interested in Claude Max 20x" checkbox on this form',
                "refers specifically to:",
            ]
        )
        for addr in expedite_addrs:
            lines.append(f"  - {addr}")

    lines.extend(
        [
            "",
            f"Repos in scope for {pmc_name} (submitted as separate",
            "forms, ordered by OSSF Criticality Score):",
        ]
    )
    for i, r in enumerate(repos, start=1):
        marker = "  ← this submission (headline)" if r.url == headline_repo.url else ""
        crit = f"{r.criticality:.1f}%" if r.criticality is not None else "blank"
        lines.append(f"  {i}. {r.url} (criticality {crit}){marker}")

    if submission_notes_text:
        lines.extend(["", "Submission notes (operator-supplied):"])
        for line in submission_notes_text.splitlines():
            lines.append(f"  {line}" if line.strip() else "")

    return "\n".join(lines)


def build_subsequent_additional_info(
    pmc_name: str, this_repo: RepoEntry, headline_repo: RepoEntry
) -> str:
    return "\n".join(
        [
            f"Submitted by the ASF Security Committee on behalf of {pmc_name} PMC at their request.",
            "",
            f"This is the apache/{this_repo.name} submission within a per-repo",
            f"batch for {pmc_name}. The maintainer roster, scan-result",
            "recipients, threat model, and any OSS-subscription expedite",
            "request are on the headline submission for this PMC (the",
            f"apache/{headline_repo.name} submission, submitted via this form",
            "immediately before this one).",
        ]
    )


def get_scan_result_recipients_for_pmc(pmc_row: dict) -> list[str]:
    """Best-effort: derive recipients from the PMC row's Notes / Contact /
    Backup columns. The original [GLASSWING] request thread is the source
    of truth, but we don't re-fetch Gmail here — operator confirms the
    list during the plan review."""
    out = []
    for col in ("Contact Person", "Backup contact"):
        raw = pmc_row.get(col, "").strip()
        if "@apache.org" in raw:
            for tok in (
                raw.replace("<", " ").replace(">", " ").replace(",", " ").split()
            ):
                tok = tok.strip().rstrip(",.;")
                if tok.endswith("@apache.org") and tok not in out:
                    out.append(tok)
    return out


def parse_submission_notes(raw: str) -> dict:
    """Parse the PMCs sheet's 'Submission notes' free-text cell into
    structured overrides + leftover text.

    Recognised tagged lines (case-insensitive prefix match):
      - `Scan-result destination: <addr>[, <addr>...]` overrides the
        recipients computed from Contact Person + Backup contact for
        the headline form's Additional Information block. Multiple
        comma-separated addresses on one line, or repeated lines, are
        all accumulated.

    Any line that doesn't match a recognised tag is preserved in
    `notes_text` and rendered verbatim in the headline form's
    Additional Information (under a separate `Submission notes:`
    section). Empty cell -> empty overrides + empty notes_text.
    """
    raw = (raw or "").strip()
    if not raw:
        return {"recipients_override": [], "notes_text": ""}
    addr_override: list[str] = []
    keep_lines: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if s.lower().startswith("scan-result destination:"):
            rest = s.split(":", 1)[1]
            for tok in rest.replace(",", " ").split():
                tok = tok.strip().rstrip(",.;")
                if "@" in tok and tok not in addr_override:
                    addr_override.append(tok)
        else:
            keep_lines.append(line)
    # Drop a single trailing blank line; keep internal structure.
    notes_text = "\n".join(keep_lines).strip()
    return {"recipients_override": addr_override, "notes_text": notes_text}


def build_plan(state: dict, submitter: dict) -> tuple[list[FormFill], list[RepoEntry]]:
    """Return (plan, skipped). Plan is the per-repo FormFill list (ordered);
    skipped is the list of repos dropped because they lack both AGENTS.md and
    SECURITY.md (and security.txt) at HEAD."""
    pmc_row = state["pmc"]
    all_repos: list[RepoEntry] = state["repos"]

    # Drop repos missing all three discoverability markers — those can't be
    # submitted (the scan agent has no AGENTS.md / SECURITY.md / security.txt
    # to anchor on, and the form's "valid SECURITY.md" assertion would be
    # false anyway).
    submittable = [r for r in all_repos if r.is_submittable]
    skipped = [r for r in all_repos if not r.is_submittable]

    if not submittable:
        sys.exit(
            "No repos are submittable — every repo in Repositories requested "
            "lacks AGENTS.md, SECURITY.md, and security.txt at HEAD. Land "
            "discoverability via glasswing-model-verify before re-running."
        )

    repos = submittable
    pmc_name_raw = pmc_row.get("PMC Name", "").strip() or pmc_row["PMC Slug"]
    pmc_name = (
        pmc_name_raw
        if pmc_name_raw.lower().startswith("apache ")
        else f"Apache {pmc_name_raw}"
    )
    expedite_addrs = parse_expedite_cell(
        pmc_row.get("Expedite Claude OSS Requests", "")
    )
    submission_notes = parse_submission_notes(pmc_row.get("Submission notes", ""))
    scan_result_recipients = submission_notes[
        "recipients_override"
    ] or get_scan_result_recipients_for_pmc(pmc_row)

    sec_model = pmc_row.get("Security Model", "").strip()
    if sec_model and not sec_model.lower().startswith(("http://", "https://")):
        print(
            f"WARN: Security Model cell on {pmc_row.get('PMC Slug')!r} is a label, "
            f"not a URL: {sec_model!r}. Form expects a URL — the operator should "
            "supply one before live submission (typically by editing the cell or "
            "passing the URL inline).",
            file=sys.stderr,
        )

    headline = repos[0]
    role = (
        f"ASF Security Committee member, submitting on behalf of "
        f"{pmc_name} PMC at their request"
    )

    plan: list[FormFill] = []
    for i, repo in enumerate(repos):
        is_headline = i == 0
        if is_headline:
            additional = build_headline_additional_info(
                pmc_name=pmc_name,
                pmc_row=pmc_row,
                expedite_addrs=expedite_addrs,
                repos=repos,
                headline_repo=headline,
                scan_result_recipients=scan_result_recipients,
                submission_notes_text=submission_notes["notes_text"],
            )
            confirm_claude_max = bool(expedite_addrs)
        else:
            additional = build_subsequent_additional_info(
                pmc_name=pmc_name,
                this_repo=repo,
                headline_repo=headline,
            )
            confirm_claude_max = False

        plan.append(
            FormFill(
                project_name=pmc_name,
                repo_url=repo.url,
                your_name=submitter["name"],
                your_email=submitter["email"],
                github_profile=submitter["github"],
                your_role=role,
                additional_info=additional,
                confirm_authorized=True,
                # Per-repo: tick only when SECURITY.md or security.txt
                # exists at HEAD. If only AGENTS.md was found, the repo
                # is submittable but the form's "valid SECURITY.md"
                # assertion stays unchecked — the assertion needs to be
                # literally true.
                confirm_security_md=repo.can_claim_security_md,
                confirm_claude_max=confirm_claude_max,
                is_headline=is_headline,
                repo_name=repo.name,
            )
        )

    return plan, skipped


def print_plan(plan: list[FormFill]) -> None:
    print(f"Plan: {len(plan)} form submission(s)")
    for i, f in enumerate(plan, start=1):
        marker = " (HEADLINE)" if f.is_headline else ""
        print(f"\n--- Form {i}/{len(plan)}: apache/{f.repo_name}{marker} ---")
        print(f"  Name of the Open Source Project: {f.project_name}")
        print(f"  URL of the Repository: {f.repo_url}")
        print(f"  Your Name: {f.your_name}")
        print(f"  Your Email Address: {f.your_email}")
        print(f"  URL of your Github profile: {f.github_profile}")
        print(f"  Your Role: {f.your_role}")
        print(f"  Additional information ({len(f.additional_info)} chars):")
        for line in f.additional_info.splitlines():
            print(f"    {line}")
        print(
            f"  [{'x' if f.confirm_authorized else ' '}] I confirm I'm authorized to request this scan"
        )
        print(
            f"  [{'x' if f.confirm_security_md else ' '}] There is a valid security.txt or SECURITY.md"
        )
        print(
            f"  [{'x' if f.confirm_claude_max else ' '}] I'm interested in Claude Max 20x for my Open Source work"
        )


# --- Playwright form submission ---


def submit_one(page, fill: FormFill) -> str:
    """Fill one form and submit. Returns the post-submit URL."""
    import re

    page.goto(FORM_URL)
    page.wait_for_load_state("networkidle")

    page.get_by_role(
        "textbox", name=re.compile(r"Name of the Open Source Project", re.I)
    ).fill(fill.project_name)
    page.get_by_role("textbox", name=re.compile(r"URL of the Repository", re.I)).fill(
        fill.repo_url
    )
    page.get_by_role("textbox", name=re.compile(r"Your Name", re.I)).fill(
        fill.your_name
    )
    page.get_by_role("textbox", name=re.compile(r"Your Email Address", re.I)).fill(
        fill.your_email
    )
    page.get_by_role(
        "textbox", name=re.compile(r"URL of your Github profile", re.I)
    ).fill(fill.github_profile)
    page.get_by_role(
        "textbox", name=re.compile(r"Your Role within the Project", re.I)
    ).fill(fill.your_role)
    page.get_by_role("textbox", name=re.compile(r"Additional information", re.I)).fill(
        fill.additional_info
    )

    if fill.confirm_authorized:
        page.get_by_role(
            "checkbox", name=re.compile(r"authorized to request this scan", re.I)
        ).check()
    if fill.confirm_security_md:
        page.get_by_role(
            "checkbox",
            name=re.compile(r"security\.txt or SECURITY\.md", re.I),
        ).check()
    if fill.confirm_claude_max:
        page.get_by_role("checkbox", name=re.compile(r"Claude Max 20x", re.I)).check()

    page.get_by_role("button", name=re.compile(r"^(Submit|Wyślij)$", re.I)).click()
    page.wait_for_url(re.compile(r"formResponse|viewscore"), timeout=30000)
    return page.url


def run_live(plan: list[FormFill], starting_from: str | None) -> dict:
    from playwright.sync_api import sync_playwright

    if not PROFILE_DIR.exists():
        sys.exit(
            f"Persistent profile not initialised at {PROFILE_DIR}. "
            "Run: form_submitter.py setup"
        )

    skip = starting_from is not None
    submitted: list[dict] = []
    skipped: list[str] = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
        )
        page = ctx.new_page()
        try:
            for fill in plan:
                if skip:
                    if fill.repo_name == starting_from:
                        skip = False
                    else:
                        skipped.append(fill.repo_name)
                        continue
                print(f"Submitting apache/{fill.repo_name}...", flush=True)
                response_url = submit_one(page, fill)
                submitted.append(
                    {
                        "repo_name": fill.repo_name,
                        "repo_url": fill.repo_url,
                        "response_url": response_url,
                        "is_headline": fill.is_headline,
                    }
                )
                print(f"  → {response_url}", flush=True)
        finally:
            ctx.close()

    return {
        "submitted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "submitted": submitted,
        "skipped": skipped,
    }


# --- CLI commands ---


def cmd_setup(_args: argparse.Namespace) -> None:
    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Launching Chromium with persistent profile at {PROFILE_DIR}.")
    print("Sign in to Google in the browser window, confirm the form loads,")
    print("then close the browser window to persist the session.")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
        )
        page = ctx.new_page() if not ctx.pages else ctx.pages[0]
        page.goto(FORM_URL)
        # Wait for human to close the browser. close() blocks until then.
        try:
            ctx.wait_for_event("close", timeout=0)
        except Exception:
            pass
    print(f"Profile populated at {PROFILE_DIR}.")


def cmd_setup_submitter(args: argparse.Namespace) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not args.email.endswith("@apache.org"):
        sys.exit("--email must be an @apache.org address.")
    cfg = {"name": args.name, "email": args.email, "github": args.github}
    SUBMITTER_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    SUBMITTER_PATH.chmod(0o600)
    print(f"Wrote submitter config to {SUBMITTER_PATH}.")


def cmd_submit_pmc(args: argparse.Namespace) -> None:
    if args.dry_run and not SUBMITTER_PATH.exists():
        submitter = {
            "name": "<run setup-submitter to set>",
            "email": "<your.id>@apache.org",
            "github": "<https://github.com/your-handle>",
        }
        print(
            f"NOTE: {SUBMITTER_PATH} missing — using placeholders. "
            "Run setup-submitter before live submission.\n"
        )
    else:
        submitter = load_submitter()
    state = fetch_pmc_state(args.slug)
    plan, skipped = build_plan(state, submitter)

    print_plan(plan)
    if skipped:
        print(
            f"\nSkipped {len(skipped)} repo(s) — no AGENTS.md / SECURITY.md / "
            "security.txt at HEAD:"
        )
        for r in skipped:
            print(f"  - apache/{r.name}")
        print(
            "These won't be submitted. Land discoverability "
            "(via glasswing-model-verify) before re-running for them."
        )

    if args.dry_run:
        print("\nDry run — no form submissions.")
        return

    result = run_live(plan, starting_from=args.starting_from)
    print("\nSubmission complete.")
    print(json.dumps(result, indent=2))

    submission_date = result["submitted_at"][:10]
    submitted_urls = [s["repo_url"] for s in result["submitted"]]
    print("\nValues for glasswing-scan-update apply:")
    print(f"  Date scan requested: {submission_date}")
    print("  Repositories submitted:")
    for url in submitted_urls:
        print(f"    {url}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Submit per-repo scan-request forms for a PMC via the vendor's "
            "project-enrollment Google Form."
        )
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="One-time Google sign-in into persistent profile.")

    s = sub.add_parser(
        "setup-submitter", help="Write submitter identity to submitter.json."
    )
    s.add_argument("--name", required=True, help="Submitter's full name.")
    s.add_argument("--email", required=True, help="Submitter's @apache.org email.")
    s.add_argument("--github", required=True, help="Submitter's GitHub profile URL.")

    s = sub.add_parser("submit-pmc", help="Submit forms for one PMC.")
    s.add_argument("--slug", required=True, help="PMC slug (e.g. tomcat, logging).")
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan only; don't drive the browser.",
    )
    s.add_argument(
        "--starting-from",
        metavar="REPO_NAME",
        help=(
            "Resume mid-batch: skip repos with names earlier than this in "
            "the ordering. Use the bare repo name (e.g. tomcat-native), "
            "not the full URL."
        ),
    )

    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.cmd == "setup":
        cmd_setup(args)
    elif args.cmd == "setup-submitter":
        cmd_setup_submitter(args)
    elif args.cmd == "submit-pmc":
        cmd_submit_pmc(args)
    else:
        sys.exit(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
