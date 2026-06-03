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
"""``model-pr open`` — open a threat-model / discoverability PR on a PMC repo.

Collapses the repeated fork -> clone -> write SECURITY.md/AGENTS.md (create or
append) [-> land THREAT_MODEL.md] -> commit -> push -> ``gh pr create`` dance
into one invocation. Two modes:

  in-repo model:   --model PATH         lands PATH as THREAT_MODEL.md and wires
                                        AGENTS.md -> SECURITY.md -> THREAT_MODEL.md
  pointer:         --pointer URL        wires AGENTS.md -> SECURITY.md -> URL
                                        (for satellite repos that defer to an
                                        umbrella model in another repo)

The branch is pushed to a fork (``--fork-owner``, default: the gh-authenticated
user). The PR is opened with ``gh pr create --web`` by default (you submit in
the browser); pass ``--submit`` to create it non-interactively.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from model_pr.content import (
    branch_name,
    build_agents_md,
    build_security_md,
    ensure_asf_header,
    merge_ratignore,
)

# Markers that say a repo runs Apache RAT (so a RAT-ignore is worth creating
# when no ignore file exists yet).
_RAT_MARKERS = ("apache-rat", "org.apache.rat", "rat-plugin", "ratcheck", "creadur")


def _detect_rat_ignore(clone: Path) -> Path | None:
    """Return the RAT-ignore file to update so the scaffold's Markdown files
    don't trip a license check, or ``None`` if the repo has no RAT check.

    Prefers an existing ignore file (``.ratignore`` / ``.rat-excludes``); if
    none exists, returns ``<clone>/.ratignore`` to be created *only* when the
    repo actually configures Apache RAT (pom/gradle/workflow). A repo with no
    RAT at all needs no exemption, so ``None`` is returned and nothing is
    written.
    """
    for fname in (".ratignore", ".rat-excludes"):
        if (clone / fname).exists():
            return clone / fname
    candidates = [clone / "pom.xml", clone / "build.gradle", clone / "build.gradle.kts"]
    wf = clone / ".github" / "workflows"
    if wf.is_dir():
        candidates += sorted(wf.glob("*.yml")) + sorted(wf.glob("*.yaml"))
    for p in candidates:
        if not p.exists():
            continue
        try:
            txt = p.read_text(errors="ignore").lower()
        except OSError:
            continue
        if any(m in txt for m in _RAT_MARKERS):
            return clone / ".ratignore"
    return None


def _run(cmd: list[str], cwd: str | None = None, capture: bool = False) -> str:
    """Run a command, echoing it; raise on non-zero. Returns stdout if captured."""
    print(f"$ {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=capture, check=False)
    if result.returncode != 0:
        if capture:
            sys.stderr.write(result.stdout or "")
            sys.stderr.write(result.stderr or "")
        raise SystemExit(f"command failed ({result.returncode}): {' '.join(cmd)}")
    return (result.stdout or "").strip() if capture else ""


def _read_or_none(path: Path) -> str | None:
    return path.read_text() if path.exists() else None


def cmd_open(args: argparse.Namespace) -> int:
    repo = args.repo if "/" in args.repo else f"apache/{args.repo}"
    owner, name = repo.split("/", 1)
    if bool(args.model) == bool(args.pointer):
        raise SystemExit("exactly one of --model / --pointer is required")

    fork_owner = args.fork_owner or _run(["gh", "api", "user", "--jq", ".login"], capture=True)
    kind = "threat-model" if args.model else "discoverability"
    branch = args.branch or branch_name(kind, args.date)

    workroot = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="model-pr-"))
    clone = workroot / name
    if clone.exists():
        _run(["rm", "-rf", str(clone)])

    # Ensure the fork exists (no-op if it already does), then clone the upstream.
    _run(["gh", "repo", "fork", repo, "--clone=false"], capture=True)
    _run(
        ["git", "clone", "--depth", "1", f"https://github.com/{repo}.git", str(clone)], capture=True
    )
    base = args.base or _run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(clone), capture=True
    )
    _run(["git", "checkout", "-q", "-b", branch], cwd=str(clone))

    # Build the discoverability scaffold (idempotent create-or-append).
    # Track which files we *create* (vs append a section to) — only created
    # files need a RAT exemption; appended-to files already existed and passed.
    created: list[str] = []
    if args.model:
        model_name = args.model_name
        (clone / model_name).write_text(ensure_asf_header(Path(args.model).read_text()))
        model_ref = f"[{model_name}](./{model_name})"
        files = [model_name, "SECURITY.md", "AGENTS.md"]
        created.append(model_name)
    else:
        # Wrap the pointer URL as a markdown autolink so trailing sentence
        # punctuation (the "." the template appends) stays outside the link —
        # otherwise link-checkers (e.g. lychee) grab "<url>." and 404.
        model_ref = f"<{args.pointer}>"
        files = ["SECURITY.md", "AGENTS.md"]

    sec_existing = _read_or_none(clone / "SECURITY.md")
    (clone / "SECURITY.md").write_text(build_security_md(sec_existing, repo, model_ref))
    if sec_existing is None:
        created.append("SECURITY.md")

    ag_existing = _read_or_none(clone / "AGENTS.md")
    (clone / "AGENTS.md").write_text(build_agents_md(ag_existing, name, args.agents_note))
    if ag_existing is None:
        created.append("AGENTS.md")

    # RAT exemption: if the repo runs Apache RAT, list the files we created in
    # its .ratignore. The files carry an SPDX header, but some RAT setups don't
    # scan a header embedded in Markdown and would fail the build regardless.
    rat_path = _detect_rat_ignore(clone)
    if rat_path is not None and created:
        existing_rat = _read_or_none(rat_path)
        new_rat = merge_ratignore(existing_rat, created)
        if new_rat != (existing_rat or ""):
            rat_path.write_text(new_rat)
            files = [*files, rat_path.name]

    _run(["git", "add", *files], cwd=str(clone))
    _run(["git", "diff", "--cached", "--stat"], cwd=str(clone))
    if args.dry_run:
        print(f"\n[dry-run] would commit + push {branch} to {fork_owner} and open a PR on {repo}")
        return 0

    subject = args.title or (
        "Add draft threat model + SECURITY.md + AGENTS.md for security-model discoverability"
        if args.model
        else "Add SECURITY.md + AGENTS.md for security-model discoverability"
    )
    _run(
        ["git", "commit", "-q", "-m", f"{subject}\n\nGenerated-by: Claude Code"],
        cwd=str(clone),
    )
    _run(
        ["git", "remote", "add", "fork", f"https://github.com/{fork_owner}/{name}.git"],
        cwd=str(clone),
    )
    _run(["git", "push", "-q", "-u", "fork", branch], cwd=str(clone), capture=True)

    pr_cmd = [
        "gh",
        "pr",
        "create",
        "--repo",
        repo,
        "--head",
        f"{fork_owner}:{branch}",
        "--base",
        base,
        "--title",
        subject,
    ]
    pr_cmd += ["--body-file", args.body_file] if args.body_file else ["--body", subject]
    pr_cmd += [] if args.submit else ["--web"]
    out = _run(pr_cmd, cwd=str(clone), capture=True)
    if out:
        print(out)
    print(f"\nDone: {repo} branch {branch} (base {base}) pushed to {fork_owner}.", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="model-pr",
        description="Open a threat-model / discoverability PR on a PMC repo.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("open", help="Open one model/discoverability PR.")
    p.add_argument("--repo", required=True, help="apache/<repo> or bare <repo>.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--model", help="Path to a THREAT_MODEL.md to land in-repo.")
    g.add_argument("--pointer", help="Cross-repo umbrella model URL (pointer mode).")
    p.add_argument("--model-name", default="THREAT_MODEL.md", help="In-repo model filename.")
    p.add_argument("--date", required=True, help="Date stamp for the branch (YYYY-MM-DD).")
    p.add_argument("--branch", help="Override the branch name.")
    p.add_argument("--base", help="Base branch (default: the repo's default branch).")
    p.add_argument("--fork-owner", help="Fork owner to push to (default: gh-authenticated user).")
    p.add_argument(
        "--agents-note", default="", help="Extra note for the AGENTS.md Security section."
    )
    p.add_argument("--title", help="PR title (and commit subject).")
    p.add_argument("--body-file", help="Path to the PR body markdown.")
    p.add_argument("--workdir", help="Where to clone (default: a temp dir).")
    p.add_argument("--submit", action="store_true", help="Create the PR directly instead of --web.")
    p.add_argument(
        "--dry-run", action="store_true", help="Build files + show the diff; no commit/push/PR."
    )
    return parser


DISPATCH = {"open": cmd_open}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return DISPATCH[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
