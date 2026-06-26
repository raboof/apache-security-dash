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
"""model-pr — open threat-model / discoverability PRs on Apache PMC repos.

Collapses the repeated fork -> clone -> write the AGENTS.md -> SECURITY.md ->
model discoverability scaffold (create or append) -> commit -> push ->
``gh pr create`` flow used by ``frontier-model-preparation-model-verify`` and the path-3
threat-model rollout into a single ``model-pr open`` invocation.
"""

__version__ = "0.1.0"
