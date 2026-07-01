#!/usr/bin/env bash
# sheet-dump.sh [SHEET] [SPREADSHEET_ID]
#
# Dump the Mythos tracker (default: PMCs sheet) as JSON objects, untruncated, via
# the Sheets API (NOT the Drive MCP, which silently caps output at ~80KB / ~140
# rows and drops in-flight PMCs past "Apache P…").
#
# Run OUTSIDE the sandbox (dangerouslyDisableSandbox): sheets-writer refreshes its
# OAuth token by WRITING ~/.config/asf-security/glasswing/token.json, which is a
# sandbox-denied write path — sandboxed runs fail with
#   PermissionError: [Errno 1] Operation not permitted: '.../token.json'
#
# Prints one JSON object per row (keyed by header). Pipe to jq.
set -u
SHEET="${1:-PMCs}"
ID="${2:-1pxaWKXYtZ-89cKk3OYE99-ewPMh2kXKvSDaqjR-I1o8}"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
uv run --project "$REPO_ROOT/tools/sheets_writer" sheets-writer dump \
  --spreadsheet-id "$ID" --sheet "$SHEET" --objects
