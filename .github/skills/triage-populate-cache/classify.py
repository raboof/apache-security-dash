"""Deterministic noise classifier for the triage-populate-cache sweep.

`security@apache.org` is a firehose: per a 2-day sample it carries spam,
CVE-workflow automation ("CVE-X is now READY"), SVN commit mails, GitHub
notifications, and outbound CVE announcements alongside the genuine
inbound vulnerability reports the Security team needs to triage.

The sweep keeps only **thread heads** (no In-Reply-To) from **external**
senders that don't match the noise denylists below. The rules are data,
not code: pass a YAML override via --filter-config to tune them per
operator without editing this file. Spam from novel external addresses
will still slip through (no deterministic rule catches it); that residue
is what the human/model triages and marks non-issue, and recurring
spammers can be added to deny_sender_substrings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Senders that are pure automation / never an inbound report. Matched as
# case-insensitive substrings of the From address.
DEFAULT_DENY_SENDERS: tuple[str, ...] = (
    "notifications@github.com",
    "noreply@github.com",
    "@svn.apache.org",
    "jira@apache.org",
    "gitbox@apache.org",
)

# Domains treated as internal (outbound announcements, CVE workflow, commits).
# Dropped unless --include-internal is passed to the sweep.
DEFAULT_INTERNAL_DOMAINS: tuple[str, ...] = ("apache.org",)

# Subject patterns (case-insensitive) that mark automation / not-a-report.
DEFAULT_DENY_SUBJECTS: tuple[str, ...] = (
    r"^re:\s",
    r"^svn commit\b",
    r"\bis now ready\b",
    r"^\[github\]",
    r"^\[jira\]",
)

# Positive signal: subjects that look like a security report. Without this
# second stage the denylist still leaves a wall of retail/points spam
# (MyLowe's, Harbor Freight, FedEx, "(광고)" ads ...) that never mentions
# Apache or a vuln class. Attachment presence is NOT a usable signal here:
# spammers attach files too (verified against live data), so a candidate is
# kept only when its subject matches one of these. Override with
# report_subject_regexes; disable entirely with --no-keyword-filter.
DEFAULT_REPORT_SUBJECTS: tuple[str, ...] = (
    r"\bapache\b",
    r"\[security",
    r"\bvulnerab",
    r"\bcve[- ]?\d",
    r"\b(rce|xss|ssrf|idor|csrf|xxe)\b",
    r"\binjection\b",
    r"\bdeseriali",
    r"\b(disclosure|exploit|bypass|exposure|traversal|overflow)\b",
    r"\b(credential|password|secret|token)\b",
    r"\bsecurity (report|issue|finding|vulnerab)",
    r"\bproof[- ]of[- ]concept\b|\bpoc\b",
)


@dataclass
class Rules:
    deny_senders: tuple[str, ...] = DEFAULT_DENY_SENDERS
    internal_domains: tuple[str, ...] = DEFAULT_INTERNAL_DOMAINS
    deny_subjects: tuple[str, ...] = DEFAULT_DENY_SUBJECTS
    report_subjects: tuple[str, ...] = DEFAULT_REPORT_SUBJECTS
    include_internal: bool = False
    require_signal: bool = True
    _deny_res: list[re.Pattern] = field(default=None, repr=False)
    _report_res: list[re.Pattern] = field(default=None, repr=False)

    def __post_init__(self):
        self._deny_res = [re.compile(p, re.IGNORECASE) for p in self.deny_subjects]
        self._report_res = [re.compile(p, re.IGNORECASE) for p in self.report_subjects]

    @classmethod
    def from_config(
        cls,
        data: dict | None,
        *,
        include_internal: bool = False,
        require_signal: bool = True,
    ) -> Rules:
        data = data or {}
        return cls(
            deny_senders=tuple(
                data.get("deny_sender_substrings", DEFAULT_DENY_SENDERS)
            ),
            internal_domains=tuple(
                data.get("internal_domains", DEFAULT_INTERNAL_DOMAINS)
            ),
            deny_subjects=tuple(
                data.get("deny_subject_regexes", DEFAULT_DENY_SUBJECTS)
            ),
            report_subjects=tuple(
                data.get("report_subject_regexes", DEFAULT_REPORT_SUBJECTS)
            ),
            include_internal=include_internal,
            require_signal=require_signal,
        )

    def classify(
        self, from_email: str, subject: str, in_reply_to: str
    ) -> tuple[bool, str]:
        """Return (keep, reason). `reason` labels why, for run stats."""
        if (in_reply_to or "").strip():
            return False, "reply"
        addr = (from_email or "").strip().lower()
        if not addr:
            return False, "no-sender"
        if any(sub in addr for sub in self.deny_senders):
            return False, "automation-sender"
        domain = addr.rsplit("@", 1)[-1]
        if not self.include_internal and any(
            domain == d or domain.endswith("." + d) for d in self.internal_domains
        ):
            return False, "internal"
        subject = subject or ""
        if any(r.search(subject) for r in self._deny_res):
            return False, "noise-subject"
        if self.require_signal and not any(r.search(subject) for r in self._report_res):
            return False, "no-report-signal"
        return True, "candidate"
