## Weekly center view

The Weekly center view is a separate tab beside Daily report and Over-capacity batches. After uploading the three snapshots, choose a center and a sport (or All sports). The view shows Monday through Sunday for the week containing Analysis date, including days without scheduled batches. Batches are ordered by timing and retain sport, proficiency, capacity, reported count, places left and review issues. Counts remain the uploaded schedule's reported weekday snapshot, not live attendance or a date-specific enrollment/trial calculation. Missing proficiency may display the original Days note as context without converting it into an approved proficiency definition.

The schedule API accepts `include_weekly: true` to return this view from the same parsed capacity snapshot. Existing missing-center and closed-center exclusions apply to every weekday. Exact source center labels and cities stay separate. On-hold definitions remain visible with review status and unavailable remaining places. No source files or approved mappings are modified.

## User-confirmed missing-center reference

The user confirmed MAIN rows 79-84 belong to Acres Racquet Arena (row 78). capacity_center_overrides.json records only this specific exception, bound to the exact original workbook SHA-256, row numbers, city and sport. Matching blank cells are resolved in memory on a fresh copy of parsed records; the workbook and parser cache are not filled in. source_center and center_resolution retain provenance in schedule exports. Different times, weekdays and proficiency pools remain separate. Other missing centers remain excluded. A changed or different workbook needs renewed confirmation; no general forward-fill rule was added.

## Missing center exclusion

Capacity rows with missing or whitespace-only center names are excluded from the slot schedule, mapping menus/totals, exports and calculations. No center is invented or forward-filled. The response retains excluded source row numbers and reasons in excluded_rows, and the website reports the excluded count. Existing blank-row mappings are not applied. Original source rows remain unchanged. Historical reports may include these rows and therefore show larger totals.

## Approved club and batch mappings

The slot screen now has a Club & batch mapping review table and a Save approved club & batch mapping button. A club keeps the full exact enrollment center-and-location label together. The capacity-side label includes Centre and CITY when provided; no location is guessed by splitting enrollment labels. Club IDs use exact full labels; academy and sport stay explicit on each approved target.

Mappings are stored only in `approved_batch_mappings.json`, outside all source exports. Similarity-based candidates are suggestions and never grant approval. Review the exact full location, academy, sport, age and proficiency combinations, tick confirmation, then save. The approved club link becomes available on related slots, while their batch/proficiency scopes still need explicit approval. Approved batch definitions prefill the calculation form on later loads. Changing a target club link invalidates conflicting earlier batch links. Target identities are stable even when menu ordering changes.

A changed capacity definition, missing target club or changed approved age/course membership requires review. A named, unchanged definition can be reused after a new export; a row with a missing center is tied to its source filename, row and exact workbook hash so it cannot silently attach to a new snapshot. An explicit row-level approval resolves that blank center only for calculation; the source cell stays blank. Other schedule/data-quality problems remain visible and can still withhold confirmed totals. Approval means the link was confirmed, not that missing source data or enrollment/trial overlap has been fixed.

Metabase, its SQL and all original files remain untouched. Do not hand-edit the approval file during server writes. Keep backups of it when sharing or moving the local application. Initial registry contains no approved real mappings; approvals are made through the review screen.

## Proficiency grouping

Workbook pools are keyed by exact center + sport + selected weekday + start/end time + exact Proficiency label. Distinct proficiency labels at the same time are separate pools. Duplicate definitions of the same pool, and an unrestricted Open pool overlapping other pools at the same time, require review. Blank proficiency definitions are flagged.

Only exact `Open` means no proficiency filter. For other labels, select the exact Age Category + Course Name / Course Details combinations in the slot form. Choices come from the selected enrollment group and matching trial source. This explicit mapping supports Beginner, Intermediate, Advanced, Beginner + Intermediate, Child Beginner and Adult Beginner without rewriting labels, inferring age from names, or silently correcting spellings. Combined categories share one capacity and student IDs are deduplicated across all selected combinations. Open ignores the proficiency mapping but retains the separately selected age scope, date, center/sport and time filters.

Missing age/course data that could belong to a restricted pool is unresolved and prevents confirmed totals. Source labels such as Advance, Advanced, Beginner and Beginner-with-trailing-space remain distinct until explicitly included. The table and exports retain the original Proficiency label. Source files remain read-only.

## Capacity file uploads and automatic snapshot classifier

The slot screen accepts a read-only XLSX (MAIN sheet) or CSV upload. A CSV may be an unmodified MAIN export with both header rows, or the downloadable one-row-per-weekday template: `Sport,Centre,Batch Time,Weekday,Total Capacity,Actual Capacity,Proficiency`. The template's example row is fictional. A new upload replaces the previous snapshot in memory, invalidates the prior link/calculation and regenerates the selected day's thresholds. Source labels are preserved. Uploaded schedules remain snapshots and must be reselected after disk edits. Use configured local capacity file returns to the path in config.json.

The automatic schedule classifier compares each row's Total Capacity against its supplied Actual Capacity: below = Available, equal = Full, above = Over Capacity; missing counts = Count not supplied; invalid/ambiguous definitions = Needs review. This is explicitly a workbook/CSV snapshot classification, not a claim of current enrollment-plus-trial occupancy. Independent linked enrollment/trial calculations remain below it and still withhold confirmed totals when attendance, source identity or enrollment overlap is unresolved. Blank and NA capacities never fall back to 100 or 35.

# Workbook slot thresholds — 21 October 2026 update

Open http://127.0.0.1:8765/schedule after running `python frontend.py`. `config.json` now points `slot_capacity_source` to the new read-only Downloads workbook. The screen reads MAIN only and uses the selected weekday's Total Capacity as the threshold for that center/sport/time row. Actual Capacity is displayed only as an undated workbook reference count. It is never added to enrollment, treated as remaining capacity, or assumed to be the current live count. The older center-age monitor remains at `/` with its separate 35 test setting.

Select a date, a workbook row, the corresponding exact enrollment academy/center/sport, and the age scope covered by that workbook capacity. Confirm the temporary link, then calculate. Approved links can be saved separately in approved_batch_mappings.json; source labels are never rewritten. All ages are combined only when explicitly selected as the pool's scope. Do not apply a whole-slot capacity independently to each age. Different center labels require explicit user mapping. Weekends follow the workbook definitions too; NA is not zero. Missing capacities, conflicting weekday definitions, ambiguous times, closed centers and duplicate center/sport/time definitions are flagged rather than given a 100-place fallback.

Enrollment counts require inclusive validity dates and exact matching weekday/start/end CSV Slots, deduplicated by Player DB ID across courses. Active is ignored. Missing slots or uncertain records can make the slot incomplete. Raw booked trials require the same date and exact start/end time. Sport mapping must be unambiguous. Shared IDs remove enrollment overlap when available; otherwise the user-approved exact name/mobile match removes repeated trial rows within this linked slot and produces a provisional preview. Missing name/mobile rows stay separate. Confirmed totals and remaining places are withheld for incomplete records or unresolved enrollment overlap. Booking creation is not integrated.

The linked slot refreshes every 15 seconds while the page is open and its link is confirmed. If the workbook changes, reload the schedule and reconfirm. Source hashes are verified after each calculation. The source workbook is never edited. Download schedule CSV creates a separate output. The slot screen has three independent source pickers: enrollment CSV, raw trial CSV/XLSX, and capacity CSV/XLSX. Uploading one source retains the other two. Uploaded snapshots remain local in memory, are hash-checked as payload snapshots, and never overwrite the original files. Use configured local files resets all three sources.

---

# Trial Limit System — version 1

Python 3.10+ command-line application. The enrollment CSV is the only enrollment source. No trial bookings are inferred.

## Current automatic center age dashboard

Shared-ID matching rule: **combined occupancy = unique enrolled Player DB IDs + unique booked trial Player DB IDs not in that enrolled set**, within the same Academy ID, exact center, sport, age category and reference date. The raw trial CSV/XLSX adapter now uses a `Player DB ID` column automatically when it is supplied. It reports already-enrolled trials excluded and removes duplicate trial IDs. Player IDs remain exact strings; names and phone numbers are not matching keys. A Trial Booking ID, when present, is used to flag conflicting booking versions, but a shared student ID is what establishes student overlap.

If some relevant trial rows lack shared IDs, their groups remain incomplete and have no confirmed combined total. The existing raw export lacks Player DB ID entirely, so its original previews remain provisional. Ask TechOps for a new export with the shared identifier; do not modify the protected source to invent IDs.

Actual trial export connected on 19 October 2026: config.json points to the read-only TechOps workbook in Downloads. `raw_trial_source.py` reads its Query result sheet directly. The confirmed trial rule is Status exactly `booked` on Trial Scheduled Date; rescheduled, missing-date and other unclear records are flagged. Trial Booking Date is not used as the session date. Original workbook columns and labels are preserved.

The supplied export has no Player DB ID or booking ID. The dashboard therefore shows **Booked trial rows** and **Enrollment + booked rows preview**, while unique additional trial students, confirmed combined totals, remaining capacity and booking approval stay unavailable. Preview rows may repeat the same person or overlap enrolled students. Names and mobile numbers are never used to deduplicate or infer identity. For verified combined totals, request stable booking and student IDs from TechOps.

Academy is linked to Academy ID and Sports only when its exact academy name and center identify a unique CSV mapping (or the exact academy name alone has one unique mapping). Ambiguous mappings, unknown age groups and missing labels are excluded from matched previews and reported. Differently written center values are not merged or renamed. Both original enrollment and trial sources remain read-only; SHA-256 checks verify unchanged snapshots. XLSX can also be selected in the trial source picker; use `--trials-path` to override the configured source.

The current main dashboard uses **Academy ID + exact Coaching Center Location + Sports + Age Category**. It no longer splits or validates Slots, session timings, Training Frequency or courses. It counts each Player DB ID once per center/sport/age across all matching enrollment records and courses. U8 and U10 remain separate, as do different academies, centers and sports.

The selected reference date must fall between Start Date and End Date, inclusive. This is a selected-date count, not a count of everyone whose enrollment touched that month. Active is ignored. Missing/invalid Slots do not create a data-quality issue or prevent counting. Missing identifiers/group fields and missing/invalid/reversed enrollment dates still make affected results incomplete.

Start with `python frontend.py` and open http://127.0.0.1:8765. Local files refresh every 15 seconds while the page is open. Uploaded files remain snapshots. The temporary test threshold is **35** in config.json; the normal intended limit is 100. The All batches and Exceeded centers tabs both use center age totals. Exports include the scope and reference date and do not claim to measure simultaneous session attendance.

For trials, connect `trial_bookings.csv` beside the program or use `--trials-path`. Required columns are Trial Booking ID, Academy ID, Coaching Center Location, Sports, Age Category, Academy Name, Player DB ID, Trial Date and Status. Start Time and End Time may remain in existing source files, but are optional and ignored. Trials are scheduled on the selected date; Cancelled rows are excluded. Repeated student bookings at different times count once within the center age batch. Enrolled students are not added again as trials. Without a trial source, combined occupancy stays unknown.

The read-only workbook remains a reference and is not used to determine these center age totals. No source names, identifiers, dates, Slots or other values are rewritten. Missing categories are not invented. Only the generated template at outputs/trial_bookings_template.csv is updated to reflect the new trial input format.

## Previous automatic slot dashboard

Temporary threshold test: config.json currently sets capacity to **35** so exceeded sessions are easy to inspect. Restore it to **100** after testing. The **Exceeded centers** tab shows only academy/center groups with a session strictly above the configured threshold, including session counts and excess. It uses the selected date and updates automatically. Counts from different sessions are not summed into a center occupancy.

Run `python frontend.py` in VS Code PowerShell and open http://127.0.0.1:8765. The main page now automatically calculates every batch from CSV Slots; it no longer requires manual workbook reference matching or manual trial counts. It refreshes local file snapshots every 15 seconds while the page is open. The threshold remains 100 in config.json. The workbook is unchanged and is not required by this automatic flow.

Groups are exact Academy ID + Coaching Center Location + Sports + Age Category + selected-date session interval. Courses are combined and each Player DB ID counts once per batch. Dates are inclusive and Active is ignored. Missing age/ID/dates/Slots are reported and affected counts are incomplete. Source labels are preserved; only dates/times are parsed in memory. Existing counts over 100 are flagged, never altered or deleted.

The enrollment CSV has no trial bookings. Without a separate trial source, trial counts, combined totals and remaining capacity stay unavailable; enrollment-only threshold breaches are still shown. To calculate combined totals automatically, supply a read-only trial-bookings CSV: `python frontend.py --trials-path "path\to\trial_bookings.csv"`, or place trial_bookings.csv beside the program. The page also accepts file snapshots. Uploaded snapshots cannot follow later disk edits; reselect them or use the local file arguments.

Trial CSV columns: `Trial Booking ID`, `Academy ID`, `Coaching Center Location`, `Sports`, `Age Category`, `Academy Name`, `Player DB ID`, `Trial Date`, `Start Time`, `End Time`, `Status`. Use YYYY-MM-DD dates, times such as 6:00 PM, and Scheduled / Cancelled status. Source group values and the student identifier namespace must match the enrollment system exactly. Duplicate trial students count once; students already enrolled in the same batch are not added twice. Conflicting booking rows and invalid fields make the affected result incomplete. An empty template is available in the dashboard and at outputs/trial_bookings_template.csv. The template is not connected automatically and does not establish that there are zero real bookings.

Download summary and quality reports from the page. Both source files stay read-only and SHA-256 checks verify consistent reads. The monitoring dashboard does not create bookings or enforce writes in an external system. `automatic_capacity.booking_decision` implements the capacity gate for future booking integration: approval is unavailable without a supplied trial source and complete data; otherwise the proposed total must be <= capacity. Local files update on each poll; this is not a live CRM/API connection.

## Previous workbook workflow

In VS Code PowerShell run `python frontend.py`, then open http://127.0.0.1:8765. Keep the terminal running; Ctrl+C stops the dashboard. Use `--port 8766` if needed. No extra Python packages are required beyond requirements.txt.

The enrollment CSV owns all academy, sport, center and age labels shown in the main selectors. Those strings are never renamed or normalized. The Excel workbook is strictly a batch timing/division reference. Workbook labels are shown separately and never substituted for CSV names. Both files open read-only and are verified using SHA-256; no spreadsheet writer is used.

1. Choose a session date and the exact CSV sport, academy, center and age.
2. Select the corresponding workbook reference row for that weekday. Review its original center, timing, Days and MAIN row/cell provenance.
3. Confirm this temporary reference link. The program does not guess aliases between centers or sports.
4. Click Calculate enrolled students, or enter current simulated trial students and proposed additional trials, then Check trial capacity.
5. Download the selected result and a separate data-quality report. Downloads use your browser's download location. Source filenames and fields are retained with workbook reference columns separate.

An age batch has one configurable limit (default 100): U6 and U8 at Saturday 6–7 PM each get 100, and U10 at 7–8 PM gets its own 100. Courses within that age batch are combined using unique Player DB ID values. Selecting a course subset for an explicit age batch produces provisional counts and withholds approval because it could understate the full batch. Choose All courses for that case.

Students with inclusive valid enrollment dates and an exact matching weekday/start/end in CSV Slots count. Equivalent unambiguous timing notation is parsed in memory (e.g. 6 pm and 6:00 PM); exact source text is preserved in displays/exports. Students with multiple records or courses count once per selected age batch/session. Trials remain manual simulations and proposed bookings are checks only.

`workbook_capacity.py` reads only the MAIN sheet, preserves labels, and follows actual Excel merged Centre cells using their original anchor addresses. Blank unmerged centers are not forward-filled. It splits explicit age lists such as U6, U8; age ranges, shorthand, missing divisions and unclear proficiency-to-age/course relationships remain unresolved. It reports invalid timings, missing day data, duplicate batch definitions and closed/on-hold centers. Workbook Total Capacity and Actual Capacity fields are not imported as student counts or limits; the agreed limit of 100 remains configurable in config.json.

Incomplete reference details, an unconfirmed link, missing identifiers/group fields, uncertain eligibility and missing/invalid Slots block unconditional approval. The enrollment number on incomplete results is only a known count. Valid CSV Slots on another weekday or interval do not count for this session. Data-quality reports contain workbook findings and enrollment issues relevant to the selected calculation, not a full reconciliation of every student against every reference row.

The source workbook defaults to `Greenfield Batch & Coach details(reference for the batch timings).xlsx` beside frontend.py. Use `--capacity-path "path\to\reference.xlsx"` to choose another MAIN-format reference, and `--csv-path "path\to\enrollment.csv"` for another startup CSV. A changed workbook snapshot requires reloading and reconfirming the reference. Changing UI inputs invalidates previous results. Links and simulations are session-only and do not change the files. The CLI retains the original capacity-group calculation without workbook references.

## Windows setup

Open PowerShell in this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest -v
$source = (Get-ChildItem -File *.csv | Select-Object -First 1).FullName
.\.venv\Scripts\python.exe trial_limit.py "$source"
```

Eligibility updated on **19 October 2026**: the reference date must be between Start Date and End Date, inclusive. **Active is ignored**, including false, blank, missing and invalid values. Invalid or missing dates remain unresolved. This rule is enabled by default. To select a reference date, run:

```powershell
.\.venv\Scripts\python.exe trial_limit.py "$source" --reference-date 2026-10-15
```

Omit `--reference-date` to use the current Asia/Kolkata date. Add `--no-interactive` for exports only. Use `--output-dir "other-results"` to select an export folder. Edit `capacity` in `config.json` to change the default 100, or supply a different JSON file using `--config`.

## Counting and simulation

Capacity groups use the exact Academy ID + Coaching Center Location + Sports + Age Category + Course Name strings. Slots, timings, Slot Type, and Training Frequency do not split groups. `GROUP_FIELDS` is the extension point for future grouping fields. Academy Name is displayed as a JSON list of all exact labels associated with a key; this avoids choosing or merging inconsistent labels.

Each eligible Player DB ID counts once per group. Leading zeros, capitalization, and spaces remain significant. Empty or whitespace-only required values are reported as missing without modifying them. Blank grouping values are never invented as categories. Eligibility lives in `eligible()`. The current policy parses ISO dates and reports missing, invalid or reversed dates. Active is neither required nor interpreted. Rows with valid dates count regardless of Active.

Rows with missing identifiers, missing group fields, malformed column counts, or unresolved eligibility are excluded and reported with the physical starting CSV line number (header is line 1). An unresolved row makes every compatible existing group incomplete; a missing grouping field acts as an unknown when assessing impact. Definitively out-of-date records do not make counts incomplete. Active=false records can affect counts and completeness under the dates-only rule. Entirely unknown groups cannot be listed; review the data-quality export as well as existing group summaries. Counts on incomplete groups are known eligible unique counts, not definitive totals. Calculated capacity statuses on those groups are provisional; booking approval is withheld.

The numbered menu accepts an existing group, a manual simulated trial count, and proposed additional trials. Both trial counts must be non-negative whole numbers and represent students not already counted. A complete group allows a booking only when enrolled + simulated trials + proposed trials <= capacity. Total below/equal/above capacity gives Available/Full/Over Capacity. Remaining places and excess are clamped to zero. Without simulated trials, combined occupancy, remaining places, excess, and status are unconfirmed. Trial simulation is session-only; it is included in that run's summary export.

## Outputs and source protection

Every run creates separate timestamped `summary_*.csv` and `data_quality_*.csv` files in `outputs`. Files are created exclusively, so an existing file is never overwritten. The source opens only for reading; its SHA-256 is compared before and after every successful run. No source labels or identifiers are rewritten. Summary `None` values export as blank cells. Data-quality files contain student identifiers; store them with the same care as the source.

Tests use fictional records for duplicates, separate exact groups, inclusive boundaries, ignored Active values, invalid dates/input, missing fields, incompleteness, capacity totals, pending eligibility, and byte-for-byte source preservation.
