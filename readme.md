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

## Quick Start

If you only want results quickly, follow one of these two paths:

### A) Compare multiple tenants (typical)

1. Put one secret file per tenant into `DSP_login_secrets/`.
   - Example: `DSP_login_secrets_TEST.json`, `DSP_login_secrets_Q.json`, `DSP_login_secrets_PROD.json`
2. Run the script:

```powershell
py .\Model_Objects_all_tenants.py
```

3. Open the newest CSV in `results/` and compare `X` flags per tenant column.

### B) Check objects for one tenant only

1. Keep only one secret file in the secrets folder (or point `DSP_SECRETS_DIR` to a folder containing only one file).
2. Run the script:

```powershell
py .\Model_Objects_all_tenants.py
```

3. The output still has the same structure, but only one tenant column is present.

### What to do if it fails

- Check `results/Logs/run_<timestamp>.log` first.
- Verify `host` is set in the secret JSON.
- Verify `datasphere --version` works in the same terminal.

## Useful Terminal Commands

### Check versions
Checks whether Node.js and npm are installed and shows their active versions.

```bash
node -v
npm -v
```

### Install SAP Datasphere CLI
Installs SAP Datasphere CLI globally via npm.

```bash
npm install -g @sap/datasphere-cli
```

### Verify CLI version
Verifies that Datasphere CLI is installed correctly.

```bash
datasphere --version
```

### Login (interactive)
Starts an interactive login against the tenant.

```bash
datasphere login
```

### Required fields for JSON
Shows locally stored secret fields for the JSON file.

```bash
datasphere config secrets show
```

### Clean config
Cleans host, cache, and secret configuration in the CLI.

```bash
datasphere config host clean
datasphere config cache clean
datasphere config secrets reset
```

### Optional: Create Python environment
Creates and activates an optional Python virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell alternative:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Install Git (Debian/Ubuntu-based BAS images)
Installs Git in Debian/Ubuntu-based environments.

```bash
sudo apt-get update
sudo apt-get install -y git
```

### Check Git version
Checks whether Git is available and shows its version.

```bash
git --version
```

### Configure Git user
Sets name and email globally for Git commits.

```bash
git config --global user.name ""
git config --global user.email ""
```

### Clone repository (example)
Clones a repository via HTTPS.

```bash
git clone https://github.com/REPO.git
```

### Change to repository directory
Changes into the local repository folder.

```bash
cd REPO
```

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

### Retrieving Tenant Secrets
Tenant Secrets can be obtained using two supported approaches.
Both options produce the values required for the DSP_login_secrets_<TENANT>.json files (Access Token, Refresh Token, Authorization/Token URLs, etc.).

#### Option 1: Via Datasphere CLI login
Use this option when a local CLI login is available.

Authenticate against the tenant:
```text
datasphere login
```

Display the locally stored authentication secrets:
```text
datasphere config secrets show
```

The output includes:

- access_token
- refresh_token
- authorization_url
- token_url
- additional CLI‑managed metadata

Copy the relevant fields into the corresponding DSP_login_secrets_<TENANT>.json file.
Notes:

- Secrets are stored locally by the CLI (not retrieved from Datasphere).
- Values remain valid until expired or overwritten by a new login.

#### Option 2: Via OAuth Authorization Code Flow (e.g. BAS, Postman)
Use this option when tokens must be retrieved without relying on the CLI or Browser (e.g. for BAS).

Request an Authorization Code via browser redirect:

Open the IAS authorize endpoint:
```text
https://<ias-tenant>/oauth/authorize?response_type=code&client_id=<CLIENT_ID>&redirect_uri=<REDIRECT_URI>&scope=openid
```

Important (`client_id` encoding for Authorization Code flow):

- Your `client_id` may look "wrongly escaped", but this is expected in SAP BTP.
- Example value:

```text
sb-9a17c3e4-2d6f-4b81-a7de-1f2c90ab7e44!b713902|client!b8421
```

- The pipe symbol must be URL-encoded in the authorize URL:
  - `|` → `%7C`
- If not encoded, IAS typically returns HTTP 400.

Log in and capture the code returned in the redirect URL. In the URL search for:
```text
?code=<AUTHORIZATION_CODE>
```

Exchange the code for tokens using the IAS token endpoint (e.g. Postman):
```text
POST https://<ias-tenant>/oauth/token
```

Header:
```text
Content-Type: application/x-www-form-urlencoded
```

Body (x-www-form-urlencoded):
```text
  grant_type=authorization_code
  code=<AUTHORIZATION_CODE>
  redirect_uri=<REDIRECT_URI>
  client_id=<CLIENT_ID>
  client_secret=<CLIENT_SECRET>
```

The response includes:

- access_token
- refresh_token
- token_type, expires_in, scopes

Store the resulting values in DSP_login_secrets_<TENANT>.json.
Optional:

- New Access Tokens can be generated using grant_type=refresh_token if refresh tokens are allowed.

## Run

From the project folder:

```powershell
py .\Model_Objects_all_tenants.py
```

## Run on SAP BTP (Cloud Foundry)

The script can run in a CF app/task container and no longer requires a fixed local folder layout.

### Required runtime prerequisites

- Python 3.10+
- Datasphere CLI installed in the container image
- Tenant secret JSON files available in a container folder

### Relevant environment variables

- `DSP_SECRETS_DIR` (optional, recommended on BTP)
  - Folder containing `DSP_login_secrets_<TENANT>.json`
- `DSP_RESULTS_DIR` (optional)
  - Output folder for CSV + logs (default: `./results`)
- `DATASPHERE_CLI` (optional)
  - Explicit CLI executable/path if not discoverable via `PATH`

### Example (Cloud Foundry task)

```bash
cf set-env <app-name> DSP_SECRETS_DIR /home/vcap/app/secrets
cf set-env <app-name> DSP_RESULTS_DIR /home/vcap/app/results
cf restage <app-name>
cf run-task <app-name> "python Model_Objects_all_tenants.py" --name dsp-compare
```

Note:
- Ensure your deployment process injects secret files into `DSP_SECRETS_DIR`.
- For recurring execution, schedule `cf run-task` via SAP Job Scheduler or an external scheduler.

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

### How to read the CSV quickly

- Each row represents one object in one space (`Space ID`, `Technical Name`, `Type`).
- Tenant columns show `X` when the object exists in that tenant.
- Empty tenant cells mean the object was not found in that tenant.
- Focus on rows where some tenants have `X` and others are empty to find deployment gaps.

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