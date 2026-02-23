# SAP Datasphere – Cross-Tenant Space/Object Compare

This project collects modeling objects from multiple SAP Datasphere tenants and produces one consolidated CSV comparison file.

The result uses tenant presence flags (`X`) per row so differences are easy to spot across environments.

## Audience and Use Case

This tool is primarily intended for **Datasphere administrators**.

Typical use case:
- Get a complete cross-tenant overview of available objects
- Compare object inventories across landscapes such as **Test**, **Q**, and **Prod**
- Quickly identify gaps, drift, or missing deployments between tenants

## Purpose

- Run once against all configured tenants
- Generate one consolidated result across all spaces/objects
- Keep per-run logs for traceability

## What the Script Does

1. Reads all secret files from `DSP_login_secrets`.
2. Logs in tenant by tenant.
3. Reads all spaces in the current tenant.
4. Reads all configured object groups per space (paginated).
5. Consolidates all records across tenants.
6. Writes a timestamped CSV to `results`.
7. Writes a run log file to `results/Logs`.

## Project Structure

- `Model_Objects_all_tenants.py` – main orchestration (CLI calls, collection, consolidation)
- `constants.py` – shared constants (retry settings, output naming, markers, messages)
- `logging_setup.py` – logger setup (console + file)
- `DSP_login_secrets/` – tenant secret files
- `results/` – generated output files
- `results/Logs/` – per-run log files

## Folder Behavior (Created vs. Required)

- `results/` is created automatically at runtime.
- `results/Logs/` is created automatically at runtime.
- `DSP_login_secrets/` must exist before running the script.
- `DSP_login_secrets/` must contain at least one tenant file named `DSP_login_secrets_<TENANT>.json`.

## Prerequisites

- Python 3.10+ (venv recommended)
- SAP Datasphere CLI available in `PATH`
  - On Windows this is usually `datasphere.cmd`
- Valid secret files for each tenant

## Tenant Secrets

Filename convention:

- `DSP_login_secrets_<TENANT>.json`

The tenant column name in the output is derived from `<TENANT>`.

Template source file in this repo:

- `DSP_login_secrets_TENANT.json.template`

Expected JSON structure (same keys as template):

```json
{
  "client_id": "",
  "client_secret": "",
  "authorization_url": "",
  "token_url": "",
  "access_token": "",
  "refresh_token": "",
  "host": "https://<your-datasphere-host>",
  "browser": "",
  "authorization_flow": ""
}
```

Important:
- `host` must be set (the script validates this explicitly).
- Other fields depend on your Datasphere CLI authentication flow.
- Keep real secret values only in `DSP_login_secrets/*.json` (already ignored by `.gitignore`).

## Run

From the project folder:

```powershell
py .\Model_Objects_all_tenants.py
```


## Output

### CSV

Generated file:

- `results/MODELING_OBJECTS_ALL_TENANTS_<YYYYMMDD_HHMMSS>.csv`

Column layout:

- `Space ID`
- `Technical Name`
- `Type`
- one column per tenant containing `X` (present) or empty (not present)

### Logs

Per-run log file:

- `results/Logs/run_<YYYYMMDD_HHMMSS>.log`

## Error and Partial-Read Behavior

- CLI calls use retries with exponential backoff on transient failures.
- Timeout is applied only on retry attempts (not on the first attempt).
- Spaces that are discovered but not readable due to missing access rights are still listed in the output.
- For those spaces, object-level details are not listed, and this state is explicitly represented in the CSV.
- If no object group can be read for a space:
  - a marker row is added
  - `Technical Name = COULD NOT READ OBJECTS`
  - `Type = E_SPACE_OBJECT_LIST_FAILED`

## Important Functional Note

Shared objects are only shown in the source space.

This is expected behavior and can lead to apparent “gaps” in target spaces.

## Configuration (via Constants)

In `constants.py` you can adjust:

- object groups (`ASSET_TYPES`)
- retry behavior (`CLI_MAX_ATTEMPTS`, `CLI_RETRY_BASE_SECONDS`)
- retry timeout (`CLI_RETRY_TIMEOUT_SECONDS`)
- output naming (`OUTPUT_CSV_BASENAME`, `LOG_FILE_PREFIX`)

## Troubleshooting

### `Datasphere CLI not found in PATH`

- Verify that Datasphere CLI is installed
- Verify that `datasphere` / `datasphere.cmd` is available in `PATH`

### `No tenant secrets found`

- Check folder `DSP_login_secrets`
- Check file naming pattern `DSP_login_secrets_<TENANT>.json`

### `Missing 'host' in secret file`

- Open the referenced secret file and add a valid `host`

### JSON parse errors

- Inspect CLI output in the run log
- Common cause: temporary platform or authorization issues

## Further Improvements

- Add extended functional docs and screenshots if needed.
- Add tests for consolidation and edge-case handling for production use.