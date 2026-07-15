# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Render the program-totals dashboard as markdown and publish it to a private
gist that ``build-status-tab`` overwrites on every refresh.

The gist id is persisted at ``~/.config/asf-security/glasswing/dashboard_gist.json``
so each run updates the same gist; its URL is printed and kept in that file.
Only aggregate counts go into the dashboard — no PMC names, no program cost mechanics.
"""

from __future__ import annotations

import json
import subprocess

from sheets_writer import CONFIG_DIR

GIST_CONFIG = CONFIG_DIR / "dashboard_gist.json"
GIST_FILENAME = "glasswing-dashboard.md"
GIST_DESCRIPTION = "Glasswing scan pipeline — program-totals dashboard (auto-generated)"


def _load_gist_id() -> str | None:
    try:
        return json.loads(GIST_CONFIG.read_text()).get("gist_id")
    except (OSError, ValueError):
        return None


def _save_gist(gist_id: str, url: str) -> None:
    GIST_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    GIST_CONFIG.write_text(json.dumps({"gist_id": gist_id, "url": url}, indent=2) + "\n")


def update_dashboard_gist(markdown: str) -> str:
    """Create the private dashboard gist (first run) or overwrite it (every run
    after), via ``gh api``. Returns the gist URL. Raises on failure."""
    payload: dict = {
        "description": GIST_DESCRIPTION,
        "files": {GIST_FILENAME: {"content": markdown}},
    }
    gist_id = _load_gist_id()
    if gist_id:
        args = ["gh", "api", f"gists/{gist_id}", "-X", "PATCH", "--input", "-"]
    else:
        payload["public"] = False
        args = ["gh", "api", "gists", "--input", "-"]
    result = subprocess.run(args, input=json.dumps(payload), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh gist update failed: {result.stderr.strip()}")
    resp = json.loads(result.stdout)
    _save_gist(resp["id"], resp["html_url"])
    return resp["html_url"]


def _bar(n: int, total: int, width: int = 22) -> str:
    filled = round(width * n / total) if total else 0
    return "`" + "█" * filled + "·" * (width - filled) + "`"


def _pct(n: int, total: int) -> str:
    return f"{round(100 * n / total)}%" if total else "—"


def render_dashboard(today: str, sheet_url: str, data: dict) -> str:
    """Build the dashboard markdown from a dict of aggregate counts."""
    total = data["total_pmcs"]
    sc = data["state_counts"]
    repos_sub, repos_not, repos_req = data["repos"]
    pr_open, pr_merged, pr_closed, pr_total = data["prs"]
    models = data["models"]
    funnel = data["funnel"]
    has_model = data["has_model"]
    verified = sum(sc[s] for s in ("Ready", "Submitted", "Triaging", "Delivered"))

    out: list[str] = []
    out.append("# Glasswing scan pipeline — dashboard")
    out.append("")
    out.append(f"_As of **{today}** · [open the live tracker]({sheet_url})._")
    out.append("")
    out.append("## At a glance")
    out.append("")
    out.append(
        f"- **{total}** PMCs opted in — **{has_model}** have a model ({_pct(has_model, total)}), "
        f"**{verified}** verified ({_pct(verified, total)})."
    )
    out.append(
        f"- **{repos_sub}/{repos_req}** repos submitted to ASF Tooling "
        f"({_pct(repos_sub, repos_req)})."
    )
    out.append(f"- **{pr_total}** PRs — {pr_open} open, {pr_merged} merged, {pr_closed} closed.")
    out.append("")

    out.append("## PMC funnel")
    out.append("")
    out.append("| Stage | PMCs | % | |")
    out.append("|---|--:|--:|---|")
    for stage, n, _color in funnel:
        out.append(f"| {stage} | {n} | {_pct(n, total)} | {_bar(n, total)} |")
    out.append("")

    out.append("## PMC pipeline")
    out.append("")
    out.append("| Stage | All | % |")
    out.append("|---|--:|--:|")
    pipe = [
        ("Pre-flight (model not yet verified)", sc["Pre-flight"]),
        ("Nominated (model awaiting verification)", data["nominated"]),
        ("Ready (model verified, awaiting submit)", sc["Ready"]),
        ("Submitted (sent to ASF Tooling)", sc["Submitted"]),
        ("Triaging (results back, sanity check)", sc["Triaging"]),
        ("Delivered (forwarded to PMC)", sc["Delivered"]),
        ("Results back (Triaging + Delivered)", data["results_back"]),
    ]
    for label, n in pipe:
        out.append(f"| {label} | {n} | {_pct(n, total)} |")
    out.append(f"| **Total — PMCs opted in** | **{total}** | **100%** |")
    out.append("")

    out.append("## Repositories")
    out.append("")
    out.append("| | Repos | % |")
    out.append("|---|--:|--:|")
    out.append(f"| Submitted to ASF Tooling | {repos_sub} | {_pct(repos_sub, repos_req)} |")
    out.append(f"| Not yet submitted | {repos_not} | {_pct(repos_not, repos_req)} |")
    out.append(f"| **Total — requested** | **{repos_req}** | **100%** |")
    out.append("")

    out.append("## Pull requests")
    out.append("")
    out.append("| | PRs | % |")
    out.append("|---|--:|--:|")
    out.append(f"| Open (not yet merged) | {pr_open} | {_pct(pr_open, pr_total)} |")
    out.append(f"| Merged | {pr_merged} | {_pct(pr_merged, pr_total)} |")
    if pr_closed:
        out.append(f"| Closed without merge | {pr_closed} | {_pct(pr_closed, pr_total)} |")
    out.append(f"| **Total** | **{pr_total}** | **100%** |")
    out.append("")

    out.append("## Threat / security models")
    out.append("")
    out.append("| Origin | All | In progress | Complete | % complete |")
    out.append("|---|--:|--:|--:|--:|")
    cnt, ip_, cp_ = models["counts"], models["in_progress"], models["complete"]
    for key, label in models["origins"]:
        if key == "none":
            out.append(f"| {label} | {cnt[key]} | — | — | — |")
        else:
            out.append(
                f"| {label} | {cnt[key]} | {ip_[key]} | {cp_[key]} | {_pct(cp_[key], cnt[key])} |"
            )
    tot_ip, tot_cp = sum(ip_.values()), sum(cp_.values())
    out.append(
        f"| **Total** | **{total}** | **{tot_ip}** | **{tot_cp}** | **{_pct(tot_cp, total)}** |"
    )
    out.append("")

    out.append(
        f"_Interactive funnel and funnel-over-time charts are on the "
        f"[live spreadsheet]({sheet_url}) (Program totals + Timeline tabs)._"
    )
    out.append("")
    return "\n".join(out)
