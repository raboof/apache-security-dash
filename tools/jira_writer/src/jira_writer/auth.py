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
"""PAT loading + mode-0600 enforcement.

The PAT lives at ~/.config/asf-security/jira/token. The file MUST have
mode 0o600 — anything looser is rejected with an actionable error so
the operator notices before they paste a token into a world-readable
file.
"""

from __future__ import annotations

import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "asf-security" / "jira"
TOKEN_PATH = CONFIG_DIR / "token"


class PATError(Exception):
    """PAT file missing, wrong mode, or empty."""


def load_pat(token_path: Path | None = None) -> str:
    """Read the PAT from disk after verifying its file mode.

    Args:
        token_path: optional override. When None, resolves to the
            module-level ``TOKEN_PATH`` *at call time* (not at
            function-definition time) — so monkeypatching
            ``jira_writer.auth.TOKEN_PATH`` in tests works.

    Raises:
        PATError: if the file is missing, has mode other than 0o600,
            or contains only whitespace.

    The mode check is enforced even on filesystems that don't carry
    real permission bits (Windows). On those platforms set the env
    var ``JIRA_WRITER_SKIP_MODE_CHECK=1`` to bypass; never set it on
    POSIX where the check is meaningful.
    """
    if token_path is None:
        token_path = TOKEN_PATH

    if not token_path.exists():
        raise PATError(
            f"No PAT at {token_path}.\n"
            f"\nSetup (one-time):\n"
            f"  1. Generate a PAT at "
            f"https://issues.apache.org/jira/secure/ViewProfile.jspa\n"
            f"     -> Personal Access Tokens tab -> Create token\n"
            f"     -> name it 'claude-glasswing', set an expiry, "
            f"copy the token (shown once)\n"
            f"  2. Save it locally:\n"
            f"       mkdir -p {token_path.parent}\n"
            f"       printf '%s' '<PAT>' > {token_path}\n"
            f"       chmod 600 {token_path}\n"
            f"  3. Verify with `jira-writer whoami`."
        )

    if not os.environ.get("JIRA_WRITER_SKIP_MODE_CHECK"):
        mode = token_path.stat().st_mode & 0o777
        if mode != 0o600:
            raise PATError(
                f"{token_path} has mode {oct(mode)}, expected 0o600. "
                f"Fix with: chmod 600 {token_path}"
            )

    pat = token_path.read_text().strip()
    if not pat:
        raise PATError(f"{token_path} is empty; re-paste the PAT and re-chmod.")
    return pat


def auth_header(token_path: Path | None = None) -> dict[str, str]:
    """Build the Authorization header for a Bearer-auth JIRA API call.

    The optional ``token_path`` is forwarded to ``load_pat``, which
    resolves None to the module-level ``TOKEN_PATH`` at call time.
    """
    return {"Authorization": f"Bearer {load_pat(token_path)}"}
