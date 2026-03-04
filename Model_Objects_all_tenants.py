from __future__ import annotations

"""SAP Datasphere cross-tenant object comparison export script.

This module logs into all configured tenants, reads spaces and modeling objects,
consolidates the data into one cross-tenant table, and writes a timestamped CSV
to the results folder.
"""

import csv
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from constants import (
    ASSET_TYPES,
    CLI_MAX_ATTEMPTS,
    CLI_RETRY_BASE_SECONDS,
    CLI_RETRY_TIMEOUT_SECONDS,
    DATASPHERE_CLI_NOT_FOUND_MESSAGE,
    LOG_FILE_PREFIX,
    OUTPUT_CSV_BASENAME,
    SPACE_MARKER_TYPE,
    SPACE_READ_ERROR_TECHNICAL_NAME,
    SPACE_READ_ERROR_TYPE,
    TRANSIENT_ERROR_MARKERS,
)
from logging_setup import configure_logging


def resolve_project_root(script_path: Path) -> Path:
    """
    Resolve the project root robustly by checking known project folders.

    Background:
    - The script may live in the project root or subfolders (e.g. Tests).
    - Instead of relying on fixed parent indexes, it searches parent paths
      for `DSP_login_secrets`.
    """

    override_root = os.environ.get("DSP_PROJECT_ROOT", "").strip()
    if override_root:
        override_path = Path(override_root).expanduser().resolve()
        if override_path.is_dir():
            return override_path

    for candidate in [script_path.parent, *script_path.parents]:
        if (candidate / "DSP_login_secrets").is_dir():
            return candidate

    return script_path.parent


def resolve_datasphere_cli() -> str:
    """
    Resolve the correct Datasphere CLI launcher for the current OS.

    On Windows, the npm CLI is often installed as `datasphere.cmd`.
    """

    configured_cli = os.environ.get("DATASPHERE_CLI", "").strip()
    if configured_cli:
        executable = shutil.which(configured_cli)
        if executable:
            return executable
        configured_path = Path(configured_cli)
        if configured_path.exists():
            return str(configured_path)

    candidates = ["datasphere"]
    if sys.platform.startswith("win"):
        candidates = ["datasphere.cmd", "datasphere", "datasphere.ps1"]

    for candidate in candidates:
        executable = shutil.which(candidate)
        if executable:
            return executable

    raise FileNotFoundError(DATASPHERE_CLI_NOT_FOUND_MESSAGE)


@lru_cache(maxsize=1)
def get_datasphere_cli() -> str:
    """Resolve the CLI lazily on first use and cache the result."""

    return resolve_datasphere_cli()


PROJECT_ROOT = resolve_project_root(Path(__file__).resolve())
SECRETS_DIR = Path(os.environ.get("DSP_SECRETS_DIR", str(PROJECT_ROOT / "DSP_login_secrets"))).expanduser().resolve()
RESULTS_DIR = Path(os.environ.get("DSP_RESULTS_DIR", str(PROJECT_ROOT / "results"))).expanduser().resolve()
LOGS_DIR = RESULTS_DIR / "Logs"
LOGGER = logging.getLogger("sap_dsp_comparespaces")


@dataclass(frozen=True)
class TenantConfig:
    """Technical configuration for exactly one tenant."""

    tenant: str
    host: str
    secrets_file: Path


@dataclass(frozen=True)
class AssetRecord:
    """Represents an asset in a tenant-independent, stable format."""

    space_id: str
    technical_name: str
    object_type: str


class SpaceObjectListingError(RuntimeError):
    """Error while reading one object list for a specific space and object group."""

    def __init__(self, space_id: str, object_group: str, details: str) -> None:
        self.space_id = space_id
        self.object_group = object_group
        self.details = details
        super().__init__(details)


def build_output_csv_path(run_id: str) -> Path:
    """Build the CSV output path with a run ID suffix (date/time)."""

    return RESULTS_DIR / f"{OUTPUT_CSV_BASENAME}_{run_id}.csv"


def get_object_groups() -> list[str]:
    """Return all object groups to process except the space header type."""

    return [asset_type for asset_type in ASSET_TYPES if asset_type != "spaces"]


def extract_space_id(item: Any) -> str:
    """Extract a space ID from the different CLI response formats."""

    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        value = item.get("id") or item.get("technicalName") or item.get("name") or ""
        return str(value).strip()
    return ""


def build_object_list_command(space_id: str, asset_type: str, batch_size: int, skip: int) -> list[str]:
    """Build the CLI command for a paginated object listing."""

    return [
        "datasphere",
        "objects",
        asset_type,
        "list",
        "--space",
        space_id,
        "--json",
        "--top",
        str(batch_size),
        "--skip",
        str(skip),
    ]


def is_transient_cli_failure(stdout: str, stderr: str) -> bool:
    """Heuristic for temporary CLI/API errors where retry is appropriate."""

    text = f"{stdout}\n{stderr}".lower()
    return any(marker in text for marker in TRANSIENT_ERROR_MARKERS)


def run_cli(command: list[str], allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a Datasphere CLI command and return the raw process result."""

    datasphere_cli = get_datasphere_cli()
    resolved_command = command.copy()
    if resolved_command and resolved_command[0] == "datasphere":
        resolved_command[0] = datasphere_cli

    max_attempts = 1 if allow_failure else CLI_MAX_ATTEMPTS

    for attempt in range(1, max_attempts + 1):
        timeout_seconds = None if attempt == 1 else CLI_RETRY_TIMEOUT_SECONDS

        try:
            result = subprocess.run(
                resolved_command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"CLI executable not found for command: {' '.join(command)}\n"
                f"Resolved executable: {datasphere_cli}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            can_retry = attempt < max_attempts
            if can_retry:
                wait_seconds = CLI_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                LOGGER.warning(
                    "CLI command timed out after %ss (attempt %s/%s): %s. Retrying in %.1fs.",
                    CLI_RETRY_TIMEOUT_SECONDS,
                    attempt,
                    max_attempts,
                    " ".join(command),
                    wait_seconds,
                )
                time.sleep(wait_seconds)
                continue

            raise RuntimeError(
                f"CLI command timed out after {CLI_RETRY_TIMEOUT_SECONDS}s: {' '.join(command)}"
            ) from exc

        if result.returncode == 0 or allow_failure:
            return result

        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        can_retry = attempt < max_attempts and is_transient_cli_failure(stdout, stderr)

        if can_retry:
            wait_seconds = CLI_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            LOGGER.warning(
                "Transient CLI failure for command '%s' (attempt %s/%s). Retrying in %.1fs.",
                " ".join(command),
                attempt,
                max_attempts,
                wait_seconds,
            )
            time.sleep(wait_seconds)
            continue

        raise RuntimeError(
            f"CLI command failed: {' '.join(command)}\n"
            f"stdout: {stdout}\n"
            f"stderr: {stderr}"
        )

    raise RuntimeError(f"CLI command failed after retries: {' '.join(command)}")


def run_cli_json(command: list[str]) -> Any:
    """Run a CLI command and parse the response as JSON."""

    result = run_cli(command)
    payload = (result.stdout or "").strip()
    if not payload:
        return []

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Unable to parse JSON output from command: {' '.join(command)}\n"
            f"Output: {payload}"
        ) from exc


def extract_tenant_from_filename(file_path: Path) -> str:
    """Read the tenant name from filenames like DSP_login_secrets_<TENANT>.json."""

    prefix = "DSP_login_secrets_"
    if not file_path.stem.startswith(prefix):
        return file_path.stem.upper()
    return file_path.stem[len(prefix) :].upper()


def load_tenant_configs(secrets_dir: Path) -> list[TenantConfig]:
    """Load all tenant configurations from the secrets directory."""

    if not secrets_dir.exists() or not secrets_dir.is_dir():
        raise FileNotFoundError(
            f"Secrets directory does not exist: {secrets_dir}. "
            "Set DSP_SECRETS_DIR to the folder containing DSP_login_secrets_<TENANT>.json files."
        )

    secret_files = sorted(secrets_dir.glob("DSP_login_secrets_*.json"))
    if not secret_files:
        raise FileNotFoundError(f"No tenant secrets found in: {secrets_dir}")

    configs: list[TenantConfig] = []
    for secret_file in secret_files:
        with secret_file.open("r", encoding="utf-8") as handle:
            secret_payload = json.load(handle)

        host = str(secret_payload.get("host", "")).strip().rstrip("/")
        if not host:
            raise ValueError(f"Missing 'host' in secret file: {secret_file}")

        configs.append(
            TenantConfig(
                tenant=extract_tenant_from_filename(secret_file),
                host=host,
                secrets_file=secret_file,
            )
        )

    return configs


def login_to_tenant(config: TenantConfig) -> None:
    """Ensure a fresh session exists, log in, and verify the session."""

    last_error: RuntimeError | None = None

    for attempt in range(1, CLI_MAX_ATTEMPTS + 1):
        run_cli(["datasphere", "logout"], allow_failure=True)
        run_cli(["datasphere", "config", "host", "set", config.host])
        run_cli(
            [
                "datasphere",
                "login",
                "--host",
                config.host,
                "--secrets-file",
                str(config.secrets_file),
            ]
        )

        try:
            verification_result = run_cli_json(["datasphere", "spaces", "list", "--json"])
            if not isinstance(verification_result, list):
                raise RuntimeError(
                    "Login verification failed: 'datasphere spaces list --json' did not return a list."
                )

            LOGGER.info("Login successful for tenant: %s", config.tenant)
            return
        except RuntimeError as error:
            last_error = error
            can_retry = attempt < CLI_MAX_ATTEMPTS

            if can_retry:
                wait_seconds = CLI_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                LOGGER.warning(
                    "Login verification failed for tenant '%s' (attempt %s/%s). Retrying in %.1fs. Details: %s",
                    config.tenant,
                    attempt,
                    CLI_MAX_ATTEMPTS,
                    wait_seconds,
                    error,
                )
                time.sleep(wait_seconds)
                continue

            break

    raise RuntimeError(
        f"Unable to establish a verified login session for tenant '{config.tenant}' after "
        f"{CLI_MAX_ATTEMPTS} attempts. Last error: {last_error}"
    )


def get_spaces() -> list[str]:
    """Read all available spaces as a list of space IDs."""

    data = run_cli_json(["datasphere", "spaces", "list", "--json"])
    spaces: list[str] = []

    if isinstance(data, list):
        for item in data:
            space_id = extract_space_id(item)

            if space_id:
                spaces.append(space_id)

    # Keep ordering stable and remove duplicates.
    return sorted(set(spaces))


def normalize_object_type(raw_object: dict[str, Any], fallback_asset_type: str) -> str:
    """Determine the business type of an object with sensible fallback logic."""

    value = (
        raw_object.get("type")
        or raw_object.get("objectType")
        or raw_object.get("assetType")
        or fallback_asset_type.rstrip("s")
    )
    return str(value).strip().upper()


def normalize_technical_name(raw_object: dict[str, Any]) -> str:
    """Read the technical name with fallback to common field names."""

    value = raw_object.get("technicalName") or raw_object.get("id") or raw_object.get("name")
    return str(value or "").strip()


def build_space_objects_unreadable_record(space_id: str) -> AssetRecord:
    """Marker record for spaces where no object group could be read."""

    return AssetRecord(
        space_id=space_id,
        technical_name=SPACE_READ_ERROR_TECHNICAL_NAME,
        object_type=SPACE_READ_ERROR_TYPE,
    )


def fetch_modeling_objects_for_space(
    space_id: str,
    asset_type: str,
    batch_size: int = 200,
) -> list[AssetRecord]:
    """
    Load all objects of one asset type in a space via pagination.

    The Datasphere CLI usually returns JSON arrays; pagination continues
    as long as a batch contains data.
    """

    all_records: list[AssetRecord] = []
    skip = 0

    while True:
        command = build_object_list_command(space_id, asset_type, batch_size, skip)
        try:
            data = run_cli_json(command)
        except RuntimeError as error:
            reason = (
                f"Could not list '{asset_type}' for space '{space_id}'. "
                f"Likely missing authorization or unsupported endpoint. Details: {error}"
            )
            raise SpaceObjectListingError(space_id=space_id, object_group=asset_type, details=reason) from error

        if not isinstance(data, list):
            reason = (
                f"Could not list '{asset_type}' for space '{space_id}': "
                "CLI did not return a JSON array."
            )
            raise SpaceObjectListingError(space_id=space_id, object_group=asset_type, details=reason)

        if not data:
            break

        for raw_object in data:
            if not isinstance(raw_object, dict):
                continue

            technical_name = normalize_technical_name(raw_object)
            if not technical_name:
                continue

            all_records.append(
                AssetRecord(
                    space_id=space_id,
                    technical_name=technical_name,
                    object_type=normalize_object_type(raw_object, asset_type),
                )
            )

        skip += batch_size

    return all_records


def collect_assets_for_current_tenant(tenant: str) -> list[AssetRecord]:
    """
    Collect all space and object data for the currently logged-in tenant.

    Includes both space entries and all additional modeling objects from
    ASSET_TYPES.
    """

    spaces = get_spaces()
    all_assets: list[AssetRecord] = []
    object_groups = get_object_groups()
    total_spaces = len(spaces)

    for index, space_id in enumerate(spaces, start=1):
        LOGGER.info("[%s] Processing space %s of %s: %s", tenant, index, total_spaces, space_id)
        per_space_assets: list[AssetRecord] = [
            AssetRecord(
                space_id=space_id,
                technical_name=space_id,
                object_type=SPACE_MARKER_TYPE,
            )
        ]
        skipped_object_groups: list[str] = []

        for asset_type in object_groups:
            try:
                per_space_assets.extend(fetch_modeling_objects_for_space(space_id, asset_type))
            except SpaceObjectListingError as error:
                skipped_object_groups.append(error.object_group)

        if object_groups and len(skipped_object_groups) == len(object_groups):
            LOGGER.warning(
                "Could not read objects for space '%s'. All object groups were skipped.",
                space_id,
            )
            per_space_assets.append(build_space_objects_unreadable_record(space_id))

        all_assets.extend(per_space_assets)

    return all_assets


def build_consolidated_rows(tenant_to_assets: dict[str, list[AssetRecord]]) -> tuple[list[dict[str, str]], list[str]]:
    """
    Build a consolidated table with one row per asset and X-flags per tenant.

    Uniqueness key: Space ID + Technical Name + Type.
    """

    tenant_columns = sorted(tenant_to_assets.keys())
    merged: dict[tuple[str, str, str], dict[str, str]] = {}

    for tenant, assets in tenant_to_assets.items():
        for asset in assets:
            key = (asset.space_id, asset.technical_name, asset.object_type)

            if key not in merged:
                merged[key] = {
                    "Space ID": asset.space_id,
                    "Technical Name": asset.technical_name,
                    "Type": asset.object_type,
                }
                for tenant_column in tenant_columns:
                    merged[key][tenant_column] = ""

            merged[key][tenant] = "X"

    fieldnames = ["Space ID", "Technical Name", "Type", *tenant_columns]
    rows = list(merged.values())
    rows.sort(key=lambda row: (row["Type"], row["Space ID"], row["Technical Name"]))
    return rows, fieldnames


def write_consolidated_csv(rows: list[dict[str, str]], fieldnames: list[str], output_file: Path) -> None:
    """Write consolidated data to CSV."""

    with output_file.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    """Control the end-to-end process: login per tenant, collect, consolidate, export."""

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"{LOG_FILE_PREFIX}_{run_id}.log"
    configure_logging(LOGGER, log_file)
    output_csv = build_output_csv_path(run_id)
    LOGGER.info("Run started: %s", run_id)
    LOGGER.info("Log file: %s", log_file)

    tenant_configs = load_tenant_configs(SECRETS_DIR)
    tenant_to_assets: dict[str, list[AssetRecord]] = {}

    for tenant_config in tenant_configs:
        LOGGER.info("--- Processing tenant: %s ---", tenant_config.tenant)
        login_to_tenant(tenant_config)
        tenant_to_assets[tenant_config.tenant] = collect_assets_for_current_tenant(tenant_config.tenant)

    rows, fieldnames = build_consolidated_rows(tenant_to_assets)
    write_consolidated_csv(rows, fieldnames, output_csv)
    LOGGER.info("Consolidated CSV created: %s", output_csv)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # noqa: BLE001 - centralized, controlled error output for CLI script
        LOGGER.exception("ERROR: %s", error)
        sys.exit(1)
