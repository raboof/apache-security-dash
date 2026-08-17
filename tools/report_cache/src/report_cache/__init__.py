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

"""The single owner of ``report-cache/`` storage.

A report-cache bundle is a directory holding one ``report.md``
(YAML front-matter + the original plain-text body) plus any attachments;
the cache root also carries a shared ``index.json``
mapping each report's Message-ID to where its bundle lives and its triage state.

This package is the one place that reads and writes that layout:

- ``report_cache.report_md`` - (de)serialise a bundle's ``report.md``.
- ``report_cache.index`` - read / write the shared ``index.json``.
- ``report_cache.cli`` - the ``report-cache`` command the triage SKILL runs
  to label / file / spam / digest / non-issue a downloaded bundle.

``populate-cache`` (download) and ``inbox-manager`` (send + archive)
import the first two modules as a Python API
instead of re-implementing the storage.
"""

__version__ = "0.1.0"
