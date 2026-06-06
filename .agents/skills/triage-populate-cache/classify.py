"""Deterministic selection criteria for the triage-populate-cache sweep.

No heuristics. A message is downloaded for triage iff, by objective facts about
its headers:

  1. it is a thread head (no In-Reply-To), and
  2. it is addressed (To) to an ASF security@ alias (security@apache.org or
     security@<project>.apache.org), and
  3. it is NOT addressed (To) to one of the specialized per-PMC security lists
     below -- those projects run their own security team, so reports sent there
     are theirs to handle, not ours; but security@apache.org and any project
     without a dedicated list still need central triage, and
  4. it is NOT addressed (To or Cc) to a project private@ list.

That is the whole filter. Spam, duplicates, and non-issues that satisfy these
criteria are downloaded and judged by the triager / downstream skills, never
guessed at here. The set of specialized lists is hardcoded on purpose (only
addresses that actually exist count); refresh it from apache/security-site's
project-coordinates.json when projects gain or lose a dedicated team.
"""

from __future__ import annotations

import re

# Specialized per-PMC security lists: a report addressed To one of these is
# handled by that project's own security team, so the Security team does NOT
# triage it (do not even download it). Note: security@apache.org is NOT here --
# the central list is exactly what we triage.
SPECIALIZED_LISTS = frozenset(
    {
        "security@airflow.apache.org",
        "security@ambari.apache.org",
        "security@commons.apache.org",
        "security@couchdb.apache.org",
        "security@dolphinscheduler.apache.org",
        "security@dubbo.apache.org",
        "security@fineract.apache.org",
        "security@geronimo.apache.org",
        "security@guacamole.apache.org",
        "security@hadoop.apache.org",
        "security@hive.apache.org",
        "security@httpd.apache.org",
        "security@hugegraph.apache.org",
        "security@ignite.apache.org",
        "security@jackrabbit.apache.org",
        "security@kafka.apache.org",
        "security@libcloud.apache.org",
        "security@logging.apache.org",
        "security@lucene.apache.org",
        "security@metron.apache.org",
        "security@nifi.apache.org",
        "security@nuttx.apache.org",
        "security@ofbiz.apache.org",
        "security@openmeetings.apache.org",
        "security@openoffice.apache.org",
        "security@sentry.apache.org",
        "security@shiro.apache.org",
        "security@singa.apache.org",
        "security@sling.apache.org",
        "security@solr.apache.org",
        "security@spamassassin.apache.org",
        "security@spark.apache.org",
        "security@struts.apache.org",
        "security@subversion.apache.org",
        "security@tomcat.apache.org",
        "security@trafficcontrol.apache.org",
        "security@trafficserver.apache.org",
        "security@trafodion.apache.org",
        "security@zeppelin.apache.org",
        "security@zookeeper.apache.org",
    }
)

# A deliberately tiny denylist of pure-automation senders that never carry a
# security report. Kept minimal on purpose ("don't miss anything else"):
# deciding whether real mail is a report is the agent's job, not this list.
AUTOMATION_SENDERS = frozenset(
    {
        "notifications@github.com",
        "noreply@github.com",
    }
)

# Any ASF security alias: security@apache.org or security@<project>.apache.org.
_SECURITY = re.compile(r"\bsecurity@(?:[a-z0-9][a-z0-9-]*\.)?apache\.org\b", re.I)
_PRIVATE = re.compile(r"\bprivate@[a-z0-9][a-z0-9-]*\.apache\.org\b", re.I)
_SECURITY_PMC = re.compile(r"\bsecurity@([a-z0-9][a-z0-9-]*)\.apache\.org\b", re.I)


def select(from_addr: str, to: str, cc: str, in_reply_to: str) -> tuple[bool, str]:
    """Return (keep, reason) for a message, by objective header facts only.

    Keep iff it is a thread head, addressed To an ASF security@ alias that is
    NOT a project's specialized list, and not addressed (To/Cc) to a private@
    list. A few pure-automation senders are dropped too. Whether kept mail is
    actually a *new security report* is decided later by the agent, not here.
    """
    if (in_reply_to or "").strip():
        return False, "reply"
    if (from_addr or "").strip().lower() in AUTOMATION_SENDERS:
        return False, "automation-sender"
    to_l = (to or "").lower()
    if not _SECURITY.search(to_l):
        return False, "not-security-addressed"
    if any(alias in to_l for alias in SPECIALIZED_LISTS):
        return False, "specialized-pmc"
    if _PRIVATE.search(f"{to or ''} {cc or ''}"):
        return False, "pmc-private"
    return True, "candidate"


def pmc_from_to(to: str) -> str | None:
    """The PMC slug from a security@<pmc> address in To (not the central list).

    Returns the single per-PMC slug when exactly one is present, else None
    (e.g. addressed only to security@apache.org)."""
    pmcs = {m.lower() for m in _SECURITY_PMC.findall(to or "")}
    pmcs.discard("apache")
    return next(iter(pmcs)) if len(pmcs) == 1 else None
