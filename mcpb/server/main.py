# /// script
# requires-python = ">=3.12"
# dependencies = ["datacharter>=0.10.4"]
# ///
"""MCPB entry point: launch the DataCharter MCP server against the user's workspace.

The host (Claude Desktop) manages the uv runtime and installs `datacharter` from
PyPI on first launch. The workspace directory is supplied via the DATACHARTER_WORKSPACE
environment variable (set from the extension's user config) or a positional argument.
"""

import os
import sys

from datacharter.cli import main

workspace = os.environ.get("DATACHARTER_WORKSPACE") or (sys.argv[1] if len(sys.argv) > 1 else ".")
raise SystemExit(main(["mcp", workspace]))
