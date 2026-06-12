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

"""Ingest security reports from the Gmail security inbox via the Gmail API.

Downloads each new message into a ``report.md`` bundle under
``report-cache/<date>/<pmc>/<message-id-slug>/`` (or ``<date>/_unsorted/...``
when no PMC can be determined from the recipients), leaving disposition,
labelling and finalisation to the triage-populate-cache SKILL.
"""

__version__ = "0.1.0"
