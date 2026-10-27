# Trial Limit System

A local dashboard for reviewing trial bookings, enrollment, batch capacity,
and occupancy. Source snapshots and approved mapping records stay local.

## Quick start (Windows CMD)

Requires Python 3.10 or newer.

```cmd
cd /d "C:\Users\biswajit.das\Desktop\Trial limit System"
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r app\requirements.txt
start.cmd
```

Open http://127.0.0.1:8765/ and upload your source exports. Stop the server
with Ctrl+C. Local input files, mapping records, and generated reports are
excluded from Git. A fresh clone requires your own exports; configured-file
views also require matching paths in `app/config.json` and applicable mappings.

See [GitHub publishing instructions](docs/GITHUB_SETUP.md) for Windows CMD
commands to publish under `eddytiya/trial-limit-system`.

## Project layout

```text
Trial limit System/
  app/           Application Python modules, HTML views, config and requirements
  input/         Original enrollment CSV and trial/capacity XLSX snapshots
  mapped/        Approved mappings, center overrides and mapping-review CSV exports
  tests/         Automated tests and test runner
  tools/         UI verification scripts
    archive/     Historical audit, approval and document-generation scripts
  outputs/       Generated reports, audit evidence and exports
    previews/    UI screenshots
    logs/        Previous validation logs
  docs/          Historical development notes
  start.ps1      Dashboard launcher
```

## Start the dashboard

From the project directory:

```powershell
python -m pip install -r app/requirements.txt
.\start.ps1
```

Or run `python app/frontend.py` and open http://127.0.0.1:8765/.
Python 3.10 or newer is required. Runtime code uses the Python standard library plus `tzdata` for Windows timezone support; dependencies are listed in `app/requirements.txt`. No spreadsheet or document-generation packages are required to run the app.

## Source files and mappings

`app/config.json` points to the local files in `input/`. Relative paths resolve from the project folder, regardless of the terminal working directory. Original filenames and source contents are preserved. The capacity file named `Greenfield Batch & Coach details (1).xlsx` is the configured snapshot copied from Downloads; the earlier reference workbook is also retained in `input/`.

Approved mappings are persisted in `mapped/approved_batch_mappings.json`; source-specific center overrides are in `mapped/capacity_center_overrides.json`. The mapping-review CSVs are reference exports, not replacements for the approval registry. Source CSVs and XLSX files belong in `input/`; generated data-quality and audit CSVs stay in `outputs/`.

The screen accepts uploads from `input/`. Uploads are snapshots; reselect them after a source file changes. Views include Daily report, Over-capacity batches, Weekly center view and Sport view with All data / Over capacity sections. Reported counts are taken from the uploaded weekday capacity snapshot.

## Checks

```powershell
python tests/run_tests.py
node tools/sport-view-check.js
node tools/sport-overcapacity-check.js
```

Historical scripts in `tools/archive/` are retained for traceability. They contain old snapshot paths and assumptions and are not production entry points; approval scripts must not be rerun casually. Previous documentation is in `docs/HISTORY.md`. The move manifest and verified file hashes are in `outputs/filesystem_migration_2026-10-22.json`.


## Read-only upload workflow

Upload the original enrollment CSV, trial CSV / Query result XLSX, and capacity CSV / MAIN XLSX. The **Batch calculation** panel provides blank CSV templates and calculation controls; diagnostics are saved separately under `reports/`. Templates are separate downloads: existing input files are never converted or overwritten. Enrollment dates accept YYYY-MM-DD and the original export's DD-MM-YYYY format; trial dates use YYYY-MM-DD. Slots retain their original weekday/time strings.

Choose the capacity batch and exact enrollment academy/center/sport. For a restricted proficiency pool, select all exact age/course memberships covered by its capacity; Open covers every age/course. Confirm the source link, then click **Calculate selected batch**. This temporary link does not edit sources or save mapping approvals. Missing/ambiguous links need review; similarity never approves a match.

The result separates enrolled students, booked trial rows, duplicate trials, trials already enrolled, occupancy preview, confirmed occupancy, remaining places, and known excess. Shared student IDs deduplicate within the selected pool across courses. Cancelled trial records are excluded; conflicting booking IDs require review. Missing IDs, malformed records and unresolved eligibility withhold confirmed totals and remaining places. Name/mobile fallback remains provisional. Reported capacity-file counts stay in the inventory views and are not added to calculated occupancy.

Download the selected calculation as CSV, including the analysis date, scope, source SHA-256 fingerprints and review issues. Changing a file, date or selected scope clears the prior calculation. Browser storage remembers uploaded snapshots; replace a snapshot when its owner provides a new export.

Validation: `python tests/run_tests.py`, `node tools/upload-workflow-check.js`. The read-only real-snapshot check is `python tools/verify_upload_snapshots.py`; its report is `outputs/upload_workflow_verification.json`. That script explicitly uses the available capacity `(2)` snapshot and existing approved links; it does not grant new approvals. The older configured capacity filename may be absent, so use uploads for the current workflow.


Upload diagnostics are stored in `reports/`, outside the dashboard. Each analysis creates a folder containing `report.md` (grouped summary and source fingerprints) and `details.json` (every issue and any selected calculation). Identical snapshots reuse their report; different inputs, analysis dates or calculation results create a separate folder. The dashboard API does not send the detailed validation list to the page. Source files and mapping approvals remain read-only.

Selecting a batch restores its current approved academy/center/sport and age/course scope. Review and confirm before calculating. Editing the target or memberships creates a temporary manual selection; **Restore approved mapping** resets it. Backend checks still reject saved mappings when capacity definitions or approved membership targets change. This workflow reads approval records without modifying them.
