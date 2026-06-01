<!-- SPDX-License-Identifier: Apache-2.0
     https://www.apache.org/licenses/LICENSE-2.0 -->

# apache/security

Operational home for the ASF Security team. Holds the reusable
**agent skills** (a.k.a. SKILLs) the team uses to run the
Mythos / Glasswing scan program end-to-end, plus the upstream
[`threat-model-producer`](.github/skills/threat-model-producer/SKILL.md)
recipe used to bootstrap project threat models when a PMC
doesn't have one yet.

If you landed here looking for **how to report a security
vulnerability in an Apache project**, see
<https://www.apache.org/security/> — this repo is the Security
team's tooling, not the public reporting entry point.

## What's in this repository

```
.github/skills/                     — canonical home of all SKILLs
├── README.md                       — per-SKILL index + contribution notes
│   # Glasswing scan-outreach program
├── glasswing-scan-run/             — periodic-sweep umbrella
├── glasswing-scan-response/        — handles inbound [GLASSWING] requests
├── glasswing-model-verify/         — pre-flight model assessment
├── glasswing-scan-update/          — all writes to the Mythos tracker
│                                      (writes go through tools/sheets_writer/)
├── glasswing-scan-status/          — status / rollup view
├── glasswing-scan-submit/          — operator-gated form-then-email submission
│                                      (one vendor form per repo, then PMC email)
├── glasswing-scan-forward/         — sanity-check + forward results to PMC verbatim
│   # Inbound security-report triage (foundation-wide security@apache.org)
├── triage-populate-cache/          — pull new reports into the local report-cache/
├── triage-assess/                  — assess cached reports + draft PMC/reporter replies
│   # Shared
└── threat-model-producer/          — model-authoring rubric, used by both
                                      areas (imported from Scovetta's gist)

tools/                              — small Python projects with pyproject.toml,
                                      tests, and CI; invoked from SKILLs
├── jira_writer/                    — Apache JIRA write helper (PAT-authed);
│                                      see tools/jira_writer/README.md
├── form_submitter/                 — Playwright-driven vendor-form filler;
│                                      see tools/form_submitter/README.md
├── sheets_writer/                  — Google Sheets writer for the tracker;
│                                      see tools/sheets_writer/README.md
├── model_pr/                       — opens AGENTS.md→SECURITY.md→model
│                                      discoverability PRs on PMC repos;
│                                      see tools/model_pr/README.md
└── whimsy_lookup/                  — Deterministic Whimsy/LDAP lookups for
                                      Gate 2 + Gate 3 identity checks;
                                      see tools/whimsy_lookup/README.md

.claude/skills/                     — symlinks so Claude Code finds the SKILLs
```

The SKILLs cover two programs: the **Glasswing scan-outreach** pipeline
(PMC opt-in → pre-flight → vendor submit → forward) and **inbound
security-report triage** (pulling `security@apache.org` reports into a
local cache and drafting responses). `threat-model-producer` is shared.

Adding a new agent-runtime convention later means adding another
symlink under that runtime's expected location — never duplicating
content.

### Two helper tiers — inline scripts vs. `tools/` projects

The repo distinguishes between two scales of Python helper:

- **Inline scripts inside a SKILL directory** — single files using
  PEP 723 inline metadata via `uv run`. No `pyproject.toml`, no test
  suite, no CI. Right for narrow helpers a single SKILL owns
  end-to-end. The repo currently has none of these — every Python
  helper has been promoted to `tools/`.
- **Standalone projects under `tools/`** (`tools/jira_writer/`,
  `tools/whimsy_lookup/`, `tools/form_submitter/`,
  `tools/sheets_writer/`, `tools/model_pr/`) — proper Python projects with `pyproject.toml`,
  unit tests, CI. Right for helpers that **multiple** SKILLs need (or
  expect to soon), have non-trivial logic worth test-covering, or
  interact with a system where regressions are expensive (e.g. JIRA
  writes to apache.org, Whimsy/LDAP lookups that drive PMC-facing
  emails). A SKILL invokes them via
  `uv run --project tools/<name> <cli> ...`.

The promotion path is one-way: if an inline script grows two
callers + non-trivial logic + a "we regret a regression here would
be costly" flavour, it moves to `tools/`. See
[`tools/jira_writer/README.md`](tools/jira_writer/README.md) for the
first project of that tier — added 2026-05-27 after the inline
`jira_writer.py` reached operational use against the HBase PMC.

## The Mythos / Glasswing scan program

Mythos (internal name) / Glasswing (public name) is an
Alpha-Omega / OpenAI partnership that lets Apache PMCs opt in to
**agentic security scans** of their repositories. The compute
cost is on the program; the PMC commits to (a) triaging real
findings and (b) maintaining a threat model the scan can run
against. The Security team coordinates the operational side:
inbound requests, pre-flight checks, vendor handoff, pre-forward
sanity check of returned reports (catching catastrophic
generation errors only — wrong project, wrong/stale model,
truncated output, missing repos), and verbatim delivery of the
vendor's findings to the PMC. Per-finding triage stays with
the PMC against the project's own threat model — the Security
team does not curate, classify, or filter findings on the PMC's
behalf.

### Pipeline

**Scan pipeline** (one path; operator-gated):

```mermaid
flowchart LR
    PMC([PMC sends<br/>GLASSWING request]):::pmc --> R{{scan-response<br/>gates 1-4}}:::skill
    R --> V{{model-verify<br/>per-repo discoverability +<br/>completeness}}:::skill
    V --> P{{scan-response<br/>pre-flight-pass template<br/>pitch + OSS-tooling offer}}:::skill
    P --> PR([PMC reply<br/>expedite list / 'none' /<br/>scoping]):::pmc
    PR --> G{{Operator gate<br/>explicit per-PMC<br/>go-ahead}}:::gate
    G --> S{{scan-submit<br/>vendor enrollment form per repo<br/>+ PMC notification email}}:::skill
    S --> M[(Mirko @<br/>Alpha-Omega<br/>runs the scan)]:::vendor
    M --> F{{scan-forward<br/>sanity check<br/>catastrophic errors only}}:::skill
    F --> A[(Archive to scans/<br/>md + .json + .notes.md<br/>committed to private repo)]:::archive
    A --> RES([Vendor findings forwarded<br/>verbatim to PMC<br/>citing archive filename]):::pmc
    RES --> T([PMC normal triage<br/>CVE / disclosure / release]):::pmc

    classDef pmc fill:#fff3cd,stroke:#9a7d00,color:#553e00
    classDef skill fill:#d4e6f9,stroke:#1f6feb,color:#0a2e5c
    classDef gate fill:#ffcccc,stroke:#cc0000,color:#660000
    classDef vendor fill:#e2d6f9,stroke:#6f42c1,color:#3d2469
    classDef archive fill:#cfe9d7,stroke:#1f7a3a,color:#0a3a1c
```

**OSS-tooling side flow** (parallel, non-blocking on the
scan pipeline). The PMC's reply to the pitch above may
nominate `@apache.org` addresses for an
Anthropic-Claude-for-Open-Source subscription expedite
ask. If it does, the flow is:

```mermaid
flowchart LR
    PR2([PMC reply nominates<br/>expedite addresses]):::pmc --> REG([Step 1: PMC members<br/>register at<br/>claude.com/contact-sales/<br/>claude-for-oss]):::pmc
    REG --> CELL{{Step 2: Expedite list<br/>written to 'Expedite Claude<br/>OSS Requests' cell}}:::skill
    CELL --> RELAY{{We relay expedite<br/>via vendor to Anthropic<br/>best-effort, not a promise}}:::skill
    RELAY --> A2[(Anthropic grants<br/>subscription)]:::vendor
    A2 --> REC{{Recorded in<br/>'Claude OSS Subscriptions<br/>Submitted' cell}}:::skill

    classDef pmc fill:#fff3cd,stroke:#9a7d00,color:#553e00
    classDef skill fill:#d4e6f9,stroke:#1f6feb,color:#0a2e5c
    classDef vendor fill:#e2d6f9,stroke:#6f42c1,color:#3d2469
```

The two flows are independent: the scan can be submitted
with or without an OSS expedite ask in flight, and an
expedite can be relayed before, during, or after the scan
submission. The pitch step in the scan pipeline raises
the OSS-tooling offer (one outbound email), and the PMC
reply step collects both decisions in one inbound
response.

The **archive step** (`scans/`) is the canonical audit trail —
every scan we forward to a PMC lands there as three files:
`<project>-<repo>-<YYYY-MM-DD>-<short-sha>.md` (the vendor's
findings as forwarded, verbatim), a `.json` sidecar (Mirko's
raw report verbatim, so the archive is auditable), and a
`.notes.md` sidecar (the team's pre-forward sanity-check log
— what we looked for, what we found, whether anything was
returned to the vendor before forwarding). The archive
filename is cited in the PMC-facing email so the PMC has a
stable identifier without needing access to this private repo.
See [`scans/README.md`](scans/README.md) for the layout, the
metadata-header spec, and the confidentiality rules.

Every transition between blocks is a write to the **Mythos
tracker spreadsheet** (the team's shared coordination workbook,
not in this repo); SKILLs read and write specific columns to
keep the per-PMC state visible to the whole team.

### Per-PMC state machine

A scan-requested PMC sits in exactly one pipeline state at any
moment. `glasswing-scan-run`'s classifier (and `build-status-tab`'s
color coding) follow this state machine:

```mermaid
stateDiagram-v2
    [*] --> NewRequest: PMC sends<br/>GLASSWING request
    NewRequest --> PreFlight: gates 1-4 pass
    NewRequest --> BlockedGate2: non-apache.org<br/>sender + no @a.o stated
    BlockedGate2 --> PreFlight: identity anchored
    PreFlight --> ModelVerifyPending: scope confirmed
    ModelVerifyPending --> PreFlightPassedPitchNotSent: model passes rubric<br/>+ every repo discoverable
    ModelVerifyPending --> BlockedDiscoverability: some repos lack AGENTS.md
    BlockedDiscoverability --> ModelVerifyPending: PRs merged<br/>or scope narrowed
    PreFlightPassedPitchNotSent --> PreFlightPassedAwaitingPmcPitchReply: pitch sent<br/>(scan-response pre-flight-pass<br/>template, OSS-tooling offer)
    PreFlightPassedAwaitingPmcPitchReply --> PmcPitchRepliedAwaitingOperatorDecision: PMC replies<br/>(expedite list / 'none' /<br/>scoping clarification)
    PmcPitchRepliedAwaitingOperatorDecision --> Submitted: operator says "submit"<br/>(scan-submit: vendor form per repo<br/>+ PMC notification email)
    Submitted --> Triaging: vendor returns report
    Triaging --> ArchivedForwarded: pre-forward sanity check +<br/>commit to scans/ +<br/>forwarding email sent
    ArchivedForwarded --> [*]: PMC triages normally
```

The colors in the Status-in-progress tab map onto this progression
(light-red Pre-flight → light-red ModelVerifyPending →
yellow PreFlightPassed* (three sub-states) →
light-green Submitted → medium-green Triaging →
dark-green ArchivedForwarded). `ArchivedForwarded` is a
brief, mostly-synchronous step: the archive commit and
the forwarding-email draft are produced together, and the
user's single approval covers both before the email is
sent.

The three `PreFlightPassed*` sub-states reflect the new
operator-gated workflow: pre-flight passing is no longer
an automatic trigger for submission. Instead, the
`scan-response` pre-flight-pass template goes out first
(raising the OSS-tooling offer + asking for scoping
follow-up), the PMC replies, then the Security team
operator decides per-PMC whether to invoke
`scan-submit`'s form-then-email flow. The OSS subscription
expedite ask travels through a parallel side flow (see
the pipeline diagram above) and does not gate the scan
itself.

### Typical interaction

```mermaid
sequenceDiagram
    autonumber
    participant PMC
    participant Sec as Security Team
    participant V as Vendor (Alpha-Omega)
    participant A as Anthropic
    PMC->>Sec: GLASSWING request<br/>(repos, contacts, model URL)
    Sec->>Sec: scan-response: gates 1-4
    Sec-->>PMC: Scope confirmation reply<br/>(if PMC has more active repos)
    PMC-->>Sec: Confirms scope
    Sec->>Sec: model-verify: per-repo<br/>discoverability + completeness
    alt Discoverability gaps
        Sec-->>PMC: PR adding AGENTS.md /<br/>SECURITY.md
        PMC-->>Sec: Merges PR
        Sec->>Sec: model-verify re-runs
    end
    Sec-->>PMC: Pre-flight-pass template<br/>(scan ready when you say go,<br/>OSS-tooling offer for triagers)
    PMC-->>Sec: Reply (expedite list / 'none' /<br/>scoping clarification)
    opt PMC nominated expedite addresses
        Note over PMC,A: PMC members first register at<br/>https://claude.com/contact-sales/claude-for-oss
        Sec->>Sec: Write addresses to<br/>'Expedite Claude OSS Requests' cell
    end
    Note over Sec: Wait for operator gate<br/>(explicit per-PMC go-ahead)
    Sec->>V: scan-submit — one vendor enrollment<br/>form per repo, in OSSF-criticality order.<br/>Headline form carries the maintainer roster<br/>and expedite addresses if the PMC nominated any
    Sec-->>PMC: PMC notification email<br/>(scan request submitted,<br/>results forthcoming,<br/>NO vendor identity in body)
    par OSS side flow (only if expedite asked)
        V->>A: Vendor relays expedite ask
        A-->>Sec: Subscription grant confirmation
        Sec->>Sec: Append to<br/>'Claude OSS Subscriptions<br/>Submitted' cell
    and Scan path
        V-->>Sec: Scan report
        Sec->>Sec: scan-forward: sanity-check<br/>(catastrophic generation<br/>errors only — wrong project,<br/>truncation, missing repos)
        Sec->>Sec: Archive to scans/<br/>(md + .json + .notes.md commit)
        Sec-->>PMC: Vendor findings forwarded<br/>verbatim (cites archive filename,<br/>NO vendor identity in body)
    end
    PMC->>PMC: Triage / CVE /<br/>coordinated disclosure
```

## The inbound security-report triage process

A second, separate workflow — operated by **Piotr Karwasz** — handles the
inbound security reports that land on the foundation-wide
`security@apache.org` alias. Where the Glasswing program is *outbound* (the
team offers scans to PMCs), this one is *inbound*: reports arrive and have to
be routed to the right PMC. Two SKILLs cover it —
[`triage-populate-cache`](.github/skills/triage-populate-cache/SKILL.md) pulls
and files reports, and
[`triage-assess`](.github/skills/triage-assess/SKILL.md) assesses each report
and drafts the response. Nothing is ever sent automatically, and the Security
team does not make the call — the PMC owns the final disposition (real issue /
non-issue / hardening / CVE).

```mermaid
flowchart TD
    IN([Inbound report<br/>security@apache.org]):::ext --> SW{{triage-populate-cache<br/>sweep.py — deterministic<br/>Ponymail sweep}}:::skill
    SW --> INBOX[(report-cache/_inbox/<br/>one report.md per bundle)]:::cache
    INBOX --> CL{{agent reads + classifies<br/>each bundle}}:::skill
    CL -->|spam / bounce / marketing| DIS([dismiss<br/>file.py --remove<br/>operator confirms]):::drop
    CL -->|genuine report| FILE[(filed under<br/>date / pmc / keywords)]:::cache
    FILE --> REC{Addressed to?}:::gate
    REC -->|PMC's own<br/>security list| TRK([track only<br/>PMC already has it]):::done
    REC -->|central<br/>security list| AS{{triage-assess<br/>read threat model + code,<br/>check archive for duplicates}}:::skill
    AS --> J{In scope and<br/>plausible?}:::gate
    J -->|false positive<br/>or hardening| RP([non-assertive reply<br/>to reporter<br/>draft.py reply]):::draft
    J -->|plausible| FW([forward to PMC<br/>plus reporter receipt<br/>draft.py forward]):::draft
    TRK --> H([human reviews + sends.<br/>PMC owns the final call]):::pmc
    RP --> H
    FW --> H

    classDef ext fill:#fff3cd,stroke:#9a7d00,color:#553e00
    classDef skill fill:#d4e6f9,stroke:#1f6feb,color:#0a2e5c
    classDef gate fill:#ffcccc,stroke:#cc0000,color:#660000
    classDef cache fill:#cfe9d7,stroke:#1f7a3a,color:#0a3a1c
    classDef draft fill:#e2d6f9,stroke:#6f42c1,color:#3d2469
    classDef done fill:#cfe9d7,stroke:#1f7a3a,color:#0a3a1c
    classDef drop fill:#eeeeee,stroke:#888888,color:#333333
    classDef pmc fill:#fff3cd,stroke:#9a7d00,color:#553e00
```

**Phase 1 — populate the cache**
([`triage-populate-cache`](.github/skills/triage-populate-cache/SKILL.md)). A
deterministic `sweep.py` queries the `security@apache.org` Ponymail archive
incrementally (off a watermark), keeps only thread-head messages addressed to a
triageable `security@` alias (not a project's own specialized security list, not
Cc'd to a `private@` list), downloads each survivor's body + attachments
straight off the Ponymail HTTP API, and writes one `report.md` (YAML
front-matter + body) per bundle into a local `report-cache/_inbox/`. The agent
then reads each bundle and either **files** a genuine report under
`<date>/<pmc>/<keywords>/` or **dismisses** spam / marketing / bounces —
dismissals are confirmed with the operator first, since they delete files. The
`report-cache/` tree is local-only (not committed).

**Phase 2 — assess and draft**
([`triage-assess`](.github/skills/triage-assess/SKILL.md)). For each filed
report: one addressed to a PMC's **own** `security@<pmc>` list is only
**tracked** (the PMC already has it); one on the **central**
`security@apache.org` is assessed — the agent pulls the project's threat model
(or `SECURITY.md`), reads the relevant code, and checks the archive for
duplicates and repeat reporters before judging whether the behaviour is an
in-scope, plausible vulnerability. A high-confidence false positive or hardening
item gets a **non-assertive reply to the reporter**; anything plausible gets a
**forward to the PMC** (`private@<pmc>` or the project's specialized security
list) plus a **receipt to the reporter**. Which PMCs are "specialized" (route to
their own security list) comes from a committed `coordinates.yaml`, regenerated
from the security-site project coordinates by `build_coordinates.py`. Every
output is a draft for a human to review and send.

## How to use the SKILLs

### One-time setup per Security-team member

1. **Clone this repo**, locally or wherever your agent runtime
   reads SKILLs from (Claude Code's `.claude/skills/` symlinks
   point at `.github/skills/`).

2. **Add a memory entry** that points at the Mythos tracker
   spreadsheet (the coordination URL stays out of the repo —
   it lives in user-scope memory). The
   [`glasswing-scan-status`](.github/skills/glasswing-scan-status/SKILL.md)
   SKILL describes the entry shape; the file ID + view URL
   come from the team.

3. **Authorize OAuth for the Sheets helper.** The
   [`glasswing-scan-update`](.github/skills/glasswing-scan-update/SKILL.md)
   SKILL walks through it:
   - Create a Google Cloud OAuth client (Desktop app type),
     enable the Sheets API.
   - Drop `oauth_client_secret.json` in
     `~/.config/asf-security/glasswing/` — **outside the repo**
     by deliberate choice; per-user, no shared service account.
   - Run `uv run --project tools/sheets_writer sheets-writer setup` once to mint a refresh token.
   - Make sure you have Editor access to the workbook.

4. **Authenticate to ponymail** the first time you do a sweep
   that needs direct thread permalinks: run
   `mcp__ponymail__login` (opens a browser for ASF LDAP). The
   session cookie caches; you'll rarely re-run.

### Periodic work loop

Whenever you sit down to do Glasswing work, start with the
umbrella sweep:

```
glasswing-scan-run
```

It does a read-only sweep across Gmail, the tracker
spreadsheet, the GitHub PRs the team has opened on PMC repos,
and Mirko correspondence. It emits a single action list,
classified by pipeline stage, with the per-task SKILL named
for each next action. Pick an item and invoke that SKILL.

The sweep also refreshes the `Status` tab in the workbook, so
anyone reading the spreadsheet sees the same picture you do —
including counts of open / merged PRs per PMC (parsed out of
the `PR/Issues` cell via `gh pr view`).

### When a GLASSWING request arrives

→ Use [`glasswing-scan-response`](.github/skills/glasswing-scan-response/SKILL.md).
It runs gates 1–4 on the request (required fields, sender
identity rooted in `@apache.org`, PMC roster, scope confirmation
against the PMC's active repos), pulls embedded questions out
of the request body, and drafts a reply that addresses each.
Output is a Gmail draft — review and click Send yourself.

### When a PMC confirms scope or replies on a thread

→ Same SKILL. The procedure also writes the confirmed
repo list to the tracker's `Repositories requested` cell via
[`glasswing-scan-update`](.github/skills/glasswing-scan-update/SKILL.md).

### When a model needs pre-flight verification

→ Use [`glasswing-model-verify`](.github/skills/glasswing-model-verify/SKILL.md).
Reads the PMC's confirmed repo list, walks each repo's
discoverability chain (`AGENTS.md` → `SECURITY.md` → model
URL), assesses the model itself against the
[`threat-model-producer`](.github/skills/threat-model-producer/SKILL.md)
minimum-bar rubric. Produces either a PR (for mechanical
fixes — typically adding two pointer files at the repo root)
or an email-reply with the gaps framed as proposals. When a
PMC needs PRs across multiple repos, each PR URL is appended
on a new line in the `PR/Issues` cell — never overwriting.

### When pre-flight passes for a PMC

→ Use [`glasswing-scan-response`](.github/skills/glasswing-scan-response/SKILL.md)'s
**pre-flight-pass template**. Sends one email back to the
PMC thread: confirms pre-flight is complete, raises the
Anthropic-Claude-for-OSS subscription offer for PMC
triagers (with register-first sequencing + the
best-effort-via-vendor framing), and asks the PMC for any
`@apache.org` addresses to nominate for the expedite ask.
The PMC's reply lands as either an expedite list or
"none" in the `Expedite Claude OSS Requests` cell. After
that, the PMC sits in
`pmc-pitch-replied-awaiting-operator-decision` until the
operator says "submit".

This SKILL does **not** auto-trigger `scan-submit`.
Pre-flight passing means we're ready to submit; the
operator decides per-PMC whether to actually queue.

### When the operator says "submit X for scan"

→ Use [`glasswing-scan-submit`](.github/skills/glasswing-scan-submit/SKILL.md).
Drafts the **form-then-email submission flow** for a PMC the
operator has explicitly green-lit:

  - **One vendor enrollment-form submission per repo** in
    scope, ordered by OSSF Criticality Score (highest
    first). The headline (top-criticality) form carries the
    maintainer roster + threat-model URL + the OSS-expedite
    addresses + the "I'm interested in Claude Max 20x"
    checkbox; later forms are slimmer and point back to it.
    Repos with no discoverability anchor (`AGENTS.md` /
    `SECURITY.md` / `security.txt`) are auto-skipped and
    surfaced for a later batch. Form filling runs through
    [`tools/form_submitter/`](tools/form_submitter/) (a
    Playwright persistent profile; one-time Google sign-in
    via `form-submitter setup`). The operator approves a
    `--dry-run` plan before anything is submitted live.
  - **A PMC notification email** to the PMC primary, CC
    backup + named contacts + `private@<pmc>` +
    `security@<pmc>` alias (if exists) + `security@apache.org`
    + the `@apache.org` scan-result recipients. Notifies the
    PMC the scan has been queued. **Body redacts vendor
    identity** — "the scan pipeline" / "our vendor partner"
    generic phrasing.

Output is the live form submissions (after dry-run approval)
plus a Gmail draft for the PMC email; you click Send. After
send, hand off to `glasswing-scan-update` to set
`Date scan requested` + `Repositories submitted`.

### When a scan report comes back from the vendor

→ Use [`glasswing-scan-forward`](.github/skills/glasswing-scan-forward/SKILL.md).
Runs a **pre-forward sanity check** on the vendor's report —
catching catastrophic generation errors only (wrong project,
wrong/stale model, truncated output, missing repos,
cross-PMC leakage, mangled formatting). If the check passes,
forwards the vendor's findings **verbatim** to the PMC's listed
scan-result recipients; if it fails, surfaces to the operator
to escalate back to the vendor before the PMC ever sees the
broken report. The team explicitly does **not** do per-finding
triage — no classification against the threat model, no
filtering, no annotation. The PMC owns the read against their
own model.

### When the spreadsheet needs an update

→ Use [`glasswing-scan-update`](.github/skills/glasswing-scan-update/SKILL.md)
directly (the other SKILLs hand off to it). The bundled
helper ([`tools/sheets_writer/`](tools/sheets_writer/)) has subcommands for every write
shape: `apply` for row updates, `init-canned-tab` /
`append-canned` for the canned-responses tab,
`insert-column` / `add-columns` / `rename-column` for schema
changes, `build-status-tab` to rebuild the auto-generated
`Status in progress` / `Completed` / `Timeline` tabs, and
`dump` for a read-only grid export.

## Operational rules encoded in the SKILLs

- **CC discipline.** `security@apache.org` on every
  Glasswing reply. PMC-facing replies (from
  `scan-response`, `scan-forward`, and `scan-submit`'s
  PMC notification email) also CC the PMC's
  `private@<pmc>.apache.org` and `security@<pmc>.apache.org`
  alias (when one exists, looked up via
  <https://security.apache.org/projects/>). The
  vendor-facing scan request is no longer an email at all —
  it's a per-repo submission to the vendor's enrollment form
  — so it carries no CC list and keeps the vendor and PMC
  threads separate by construction.
- **PMC-facing vendor opacity.** Emails that go to PMC
  audiences (any of the four PMC-facing SKILLs above)
  never name the scan vendor. Canonical wordings: "our
  scan vendor partner" / "our vendor relationship" /
  "the scan pipeline". The Glasswing **program name** is
  fine (it's already in the `[GLASSWING]` subject line).
  Anthropic + Apache Magpie + Claude OSS are fine to
  name; vendor identity (Mirko / Alpha-Omega /
  `mirko@alpha-omega.dev` / "the Glasswing pipeline"
  used as vendor synonym) is what's redacted in
  PMC-facing email bodies. Internal SKILL docs and this
  README name the vendor freely; the redaction is
  PMC-facing-content-only.
- **Identity anchoring.** General discussion can come from
  any email; the formal `[GLASSWING]` request needs at least
  one `@apache.org` address attached, because scan results
  are delivered only to `@apache.org` personal addresses.
- **Scope confirmation.** Always cross-check the PMC's
  requested repos against their active set (non-blank OSSF
  criticality score on the Repositories sheet of the tracker)
  and ask before silently accepting a narrower scope than
  what the PMC actively maintains.
- **Glasswing-name discipline in public artefacts.** PR
  titles, PR bodies, and commit messages on PMC repos use
  neutral phrasing ("an automated agentic security scan we're
  piloting"). The program name stays inside private channels
  (email to `private@<pmc>`, `security@apache.org`, and this
  repo itself).
- **PRs not issues for PMC-side communication.** Many Apache
  projects have GitHub issues disabled, and issues are public
  in any case. PMC-facing follow-ups go on the existing
  `[GLASSWING]` email thread instead.
- **Pre-forward sanity check, not per-finding triage.** The
  Security team's role on returned scan reports is a narrow
  gatekeeping pass — catch catastrophic generation errors
  (wrong project, wrong/stale model, truncated output,
  missing repos, cross-PMC leakage, mangled formatting) so
  the PMC isn't asked to read a clearly broken report. The
  vendor's findings are then forwarded **verbatim**. The team
  does not classify findings against the threat model, drop
  findings as out-of-scope, suppress findings as known
  non-findings, or annotate findings with model citations —
  per-finding triage stays with the PMC, against their own
  model, through the project's normal `private@<pmc>` flow.
- **`PR/Issues` is a running list, not a single-slot field.**
  Each PR URL is on its own line; new ones append.
  `build-status-tab` parses every URL out of the cell to
  compute per-PMC `PRs opened (not yet merged)` / `PRs merged` /
  `PRs total` counts, plus a program-wide rollup at the top of
  the Status sheet.

## Memory and secrets boundary

| Where | What lives there | Why |
|---|---|---|
| `apache/security` (this repo, **private**) | SKILL definitions, helper code, seed canned-responses, threat-model-producer rubric, internal README. | Read access limited to Security team members. Anything that needs to be linked externally (currently: the `threat-model-producer` rubric, since PMC-facing emails cite it) is mirrored to a public gist — see the table below. |
| Public mirror of `threat-model-producer` | <https://gist.github.com/potiuk/da14a826283038ddfe38cc9fe6310573> | The rubric is referenced by every outbound PMC-facing email. Maintained by Jarek; sync procedure documented in `§10` of [`threat-model-producer/SKILL.md`](.github/skills/threat-model-producer/SKILL.md). |
| User-scope Claude memory (`~/.claude/.../memory/`) | The Mythos spreadsheet's file ID + view URL (entry name `mythos-tracker`). | The coordination URL is internal to the program; not for the public repo. |
| `~/.config/asf-security/glasswing/` (outside any repo) | OAuth `client_secret.json`, refresh `token.json`. | Per-Security-team-member; no shared service account; every write attributable to a named human. |
| The Mythos spreadsheet | Per-PMC state — opt-in flag, contacts, repos, dates, ponymail thread URLs, model assessment, PR/Issues. | The shared coordination view; SKILLs read and write it via the OAuth helper. |

## Contributing

Improvements to the SKILLs land via PRs to this repo. New SKILLs
go under `.github/skills/<short-name>/SKILL.md` with the YAML
frontmatter (`name`, `description`) the SKILL loaders expect.
See [`.github/skills/README.md`](.github/skills/README.md) for
the per-SKILL conventions and the PR description shape.

The `tools/` projects target **Python 3.13** and run a `prek`
pre-commit/pre-push hook plus a CI matrix; `main` requires the
`prek`, `tests-ok`, and `allowlist` status checks to pass before
merge. The toolchain conventions (prek setup, commit-message
trailer, sandbox-bypass etiquette) live in
[`AGENTS.md`](AGENTS.md).

## Agent-assisted contribution (apache-steward)

This repo adopts the
[`apache/airflow-steward`](https://github.com/apache/airflow-steward)
framework via a snapshot mechanism. The framework is **not**
vendored — it lives as a gitignored snapshot under
`.apache-steward/`, fetched on demand from the version pinned in
the committed [`.apache-steward.lock`](.apache-steward.lock)
(currently tracking the framework's `main` branch).

The only framework artefact committed to this repo is the
`setup-steward` skill at
[`.github/skills/setup-steward/`](.github/skills/setup-steward/);
every other framework skill is a gitignored symlink the setup
skill wires up. This adopter currently wires only the framework's
**always-on maintenance skills** (`setup-isolated-setup-*`,
`setup-override-upstream`, `setup-shared-config-sync`,
`list-steward-skills`) — none of the opt-in `security-*`,
`pr-management-*`, or `issue-*` families are installed. (The
repo's own Glasswing / triage SKILLs are unaffected.)

A fresh clone needs the snapshot populated before any framework
skill is invocable. In your agent harness, run:

    /setup-steward

(or follow [`.claude/skills/setup-steward/`](.claude/skills/setup-steward/))
to fetch the snapshot per the committed lock, scaffold the
gitignored symlinks, and install the post-checkout hook.

Adopter-specific modifications to framework workflows live in
[`.apache-steward-overrides/`](.apache-steward-overrides/)
(committed) — never edit the snapshot directly. Framework changes
go via PR to
[`apache/airflow-steward`](https://github.com/apache/airflow-steward).

## License

Apache License, Version 2.0 —
<https://www.apache.org/licenses/LICENSE-2.0>.
