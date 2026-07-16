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

"""Where the cache lives.

``report_cache`` owns ``report-cache/`` storage, so it owns the answer to "which
directory is that", rather than each tool spelling out the same path. The root
is a sibling of ``tools/`` in the repo checkout; ``REPORT_CACHE_DIR`` overrides
it, which is what a test or a second checkout uses.
"""

from __future__ import annotations

from os import getenv
from pathlib import Path

# .../tools/report_cache/src/report_cache/paths.py -> the repo checkout.
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CACHE = REPO_ROOT / "report-cache"

CACHE_DIR_ENV = "REPORT_CACHE_DIR"


def cache_dir() -> Path:
    """The cache root: ``$REPORT_CACHE_DIR`` if set, else the repo's ``report-cache/``."""
    override = getenv(CACHE_DIR_ENV)
    return Path(override) if override else DEFAULT_CACHE
