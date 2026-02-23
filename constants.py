"""Shared constants for Datasphere cross-tenant comparison scripts.

This module contains:
- CLI retry and timeout defaults
- fixed output naming parts
- marker values used in consolidated exports
- reusable user-facing error messages
"""

ASSET_TYPES: list[str] = [
    "spaces",
    # "connections",
    "local-tables",
    "views",
    "analytic-models",
    "replication-flows",
    "remote-tables",
    "task-chains",
    "transformation-flows",
    "data-flows",
    "intelligent-lookups",
    "data-access-controls",
    "er-models",
    "business-entities",
    "fact-models",
    "consumption-models",
]

CLI_MAX_ATTEMPTS = 3
CLI_RETRY_BASE_SECONDS = 1.5
CLI_RETRY_TIMEOUT_SECONDS = 60

DATASPHERE_CLI_NOT_FOUND_MESSAGE = (
    "Datasphere CLI not found in PATH. Please install it and ensure one of "
    "these commands is available: datasphere (or datasphere.cmd on Windows)."
)

PROJECT_ROOT_NOT_FOUND_MESSAGE = (
    "Unable to locate project root: folder 'DSP_login_secrets' not found in parent paths."
)

SPACE_MARKER_TYPE = "SPACE"
SPACE_READ_ERROR_TYPE = "E_SPACE_OBJECT_LIST_FAILED"
SPACE_READ_ERROR_TECHNICAL_NAME = "COULD NOT READ OBJECTS"
OUTPUT_CSV_BASENAME = "MODELING_OBJECTS_ALL_TENANTS"
LOG_FILE_PREFIX = "run"

TRANSIENT_ERROR_MARKERS = (
    "timeout",
    "timed out",
    "temporary",
    "temporarily",
    "try again",
    "rate limit",
    "too many requests",
    "429",
    "connection reset",
    "econnreset",
    "etimedout",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "internal server error",
)
