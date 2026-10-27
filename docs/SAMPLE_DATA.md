# Fictional sample data

All records in the files below are invented demonstration data. They contain no real students, contact details, source identifiers or company mapping records. Use the analysis date **2026-10-27 (Tuesday)**.

## Upload the samples

Start the application using the README instructions and select:

| Upload field | File |
| --- | --- |
| Enrollment CSV | `input/sample_enrollment.csv` |
| Trial bookings | `input/sample_trials.csv` |
| Capacity schedule | `input/sample_capacity.csv` |

For each selected batch, choose the academy, centre and sport shown in `mapped/sample_matching.csv`, confirm the source link, and calculate. Both capacity pools are **Open**, covering all ages and courses.

## Matching records

`mapped/sample_matching.csv` is a human-readable matching reference. It is not an application upload format.

`mapped/sample_batch_mappings.json` contains application-compatible approved links for these fictional batches only. Uploading the CSVs does not automatically load this JSON. To demonstrate restored mappings in a separate fresh clone, copy it to `mapped/approved_batch_mappings.json` before starting the app. Do not overwrite an existing real approval file; use the manual selections instead. The sample does not change `app/config.json` or any existing real mappings.

## Expected calculations

Each centre has two enrolled students and three trial rows: one booked student already enrolled, one new booked student, and one cancelled trial. The already-enrolled trial and cancelled trial add no occupancy.

| Centre | Sport | Enrolled | Additional trials | Confirmed occupancy | Capacity | Remaining | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Demo Centre 1 | Football | 2 | 1 | 3 | 5 | 2 | Available |
| Demo Centre 2 | Badminton | 2 | 1 | 3 | 3 | 0 | Full |

Reported capacity snapshot counts are 2 for each centre; these are separate from calculated occupancy. Dates outside the sample period or weekdays without a supplied session will produce different or empty results.

Only these explicitly named sample files are allowed through `.gitignore`. Keep real exports, personal data and local approval records excluded from GitHub.
