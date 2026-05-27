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
"""Playwright form-submission orchestration.

End-to-end browser code; not covered by the test suite (pure-function
tests live in ``plan.py`` / ``repos.py``). Manual smoke testing
documented in README.md.
"""

from __future__ import annotations

import datetime
import re
import sys

from form_submitter import FORM_URL, PROFILE_DIR
from form_submitter.plan import FormFill


class ProfileNotInitialized(Exception):
    """Persistent Chromium profile is missing; run `form-submitter setup`."""


def submit_one(page, fill: FormFill) -> str:
    """Fill one form and submit. Returns the post-submit URL."""
    page.goto(FORM_URL)
    page.wait_for_load_state("networkidle")

    page.get_by_role("textbox", name=re.compile(r"Name of the Open Source Project", re.I)).fill(
        fill.project_name
    )
    page.get_by_role("textbox", name=re.compile(r"URL of the Repository", re.I)).fill(fill.repo_url)
    page.get_by_role("textbox", name=re.compile(r"Your Name", re.I)).fill(fill.your_name)
    page.get_by_role("textbox", name=re.compile(r"Your Email Address", re.I)).fill(fill.your_email)
    page.get_by_role("textbox", name=re.compile(r"URL of your Github profile", re.I)).fill(
        fill.github_profile
    )
    page.get_by_role("textbox", name=re.compile(r"Your Role within the Project", re.I)).fill(
        fill.your_role
    )
    page.get_by_role("textbox", name=re.compile(r"Additional information", re.I)).fill(
        fill.additional_info
    )

    # Google Forms checkboxes are custom <div role="checkbox"> elements,
    # not native <input type="checkbox">. Playwright's .check() verifies
    # aria-checked flips after click, but Google Forms' state update can
    # lag the click microtask — .check() then fails with "did not change
    # its state" even though the click registered. Use .click() instead
    # and trust that the click took. If the state doesn't actually flip
    # (rare in practice), the form's required-field validation catches
    # it at Submit time and we surface the error.
    if fill.confirm_authorized:
        page.get_by_role(
            "checkbox", name=re.compile(r"authorized to request this scan", re.I)
        ).click()
    if fill.confirm_security_md:
        page.get_by_role(
            "checkbox",
            name=re.compile(r"security\.txt or SECURITY\.md", re.I),
        ).click()
    if fill.confirm_claude_max:
        page.get_by_role("checkbox", name=re.compile(r"Claude Max 20x", re.I)).click()

    page.get_by_role("button", name=re.compile(r"^(Submit|Wyślij)$", re.I)).click()
    page.wait_for_url(re.compile(r"formResponse|viewscore"), timeout=30000)
    return page.url


def run_live(plan: list[FormFill], starting_from: str | None) -> dict:
    """Submit every form in ``plan`` via headless Chromium.

    Raises:
        ProfileNotInitialized: persistent profile dir is missing.
    """
    from playwright.sync_api import sync_playwright

    if not PROFILE_DIR.exists():
        raise ProfileNotInitialized(
            f"Persistent profile not initialised at {PROFILE_DIR}. Run: form-submitter setup"
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
        "submitted_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "submitted": submitted,
        "skipped": skipped,
    }


def run_setup() -> None:
    """Launch a non-headless Chromium so the operator can sign in to Google.

    The persistent profile populated by this flow is what subsequent
    headless ``run_live`` calls use to authenticate against the form.
    """
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
        try:
            ctx.wait_for_event("close", timeout=0)
        except Exception:  # noqa: BLE001
            # ctx.close() during shutdown raises a generic Exception;
            # we don't care about the specific type.
            pass
        else:
            print("(Browser closed.)", file=sys.stderr)
    print(f"Profile populated at {PROFILE_DIR}.")
