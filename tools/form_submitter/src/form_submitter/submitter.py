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
"""Submitter identity config (Name / @apache.org email / GitHub profile URL).

Stored at ~/.config/asf-security/glasswing/submitter.json (mode 0o600
when written via ``write_submitter``). The form_submitter never
auto-detects the operator's identity — it asks the operator to declare
it explicitly via ``setup-submitter``.
"""

from __future__ import annotations

import json
from pathlib import Path

from form_submitter import CONFIG_DIR, SUBMITTER_PATH


class SubmitterError(Exception):
    """Submitter config missing, malformed, or non-@apache.org."""


def load_submitter(path: Path | None = None) -> dict:
    """Load + validate submitter.json. Raises SubmitterError on any issue."""
    path = path or SUBMITTER_PATH
    if not path.exists():
        raise SubmitterError(
            f"No submitter config at {path}.\n"
            "Run: form-submitter setup-submitter --name 'Your Name' "
            "--email you@apache.org --github https://github.com/you"
        )
    cfg = json.loads(path.read_text())
    for key in ("name", "email", "github"):
        if not cfg.get(key, "").strip():
            raise SubmitterError(f"submitter.json missing {key!r}.")
    if not cfg["email"].endswith("@apache.org"):
        raise SubmitterError(
            f"submitter.email must be an @apache.org address (got {cfg['email']!r})."
        )
    return cfg


def write_submitter(name: str, email: str, github: str, path: Path | None = None) -> None:
    """Write submitter config to disk (mode 0o600). Raises on bad email.

    Idempotent — overwrites any existing file.
    """
    path = path or SUBMITTER_PATH
    if not email.endswith("@apache.org"):
        raise SubmitterError("--email must be an @apache.org address.")
    target_dir = path.parent if path.parent else CONFIG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    cfg = {"name": name, "email": email, "github": github}
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    path.chmod(0o600)
