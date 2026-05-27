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
"""Apache JIRA write helper for the ASF Security team's Glasswing pipeline.

Public API:

    from jira_writer.auth import load_pat
    from jira_writer.client import api_call, get_myself, create_issue, add_comment
    from jira_writer.cli import main

CLI:

    jira-writer whoami
    jira-writer create-issue --project HBASE --summary ... --description-file ...
    jira-writer add-comment --issue HBASE-30181 --body ...

Auth: PAT at ~/.config/asf-security/jira/token (mode 0o600). See the
project README for the one-time setup flow.
"""

__version__ = "0.1.0"

JIRA_BASE = "https://issues.apache.org/jira"
