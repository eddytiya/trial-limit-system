"""Snapshot diagnostics only: no source writes or inferred label mappings."""
from collections import Counter
from datetime import date
from automatic_capacity import ENROLLMENT_FIELDS
from session_capacity import parse_slots
from workbook_capacity import minutes
from trial_limit import enrollment_date

TEMPLATES = {
    'enrollment': [*ENROLLMENT_FIELDS, 'Course Name', 'Slots'],
    'trials': ['Academy', 'Coaching Center', 'Age Category', 'Course Details',
               'Trial Scheduled Date', 'Start Time', 'End Time', 'Status',
               'Player DB ID', 'Trial Booking ID'],
    'capacity': ['Sport', 'Centre', 'CITY', 'Batch Time', 'Weekday',
                 'Total Capacity', 'Actual Capacity', 'Proficiency'],
}


def validate_uploads(enrollments, trials, batches, excluded=()):
    issues=[]
    def add(source, row, reason):
        issues.append({'source':source, 'row':row, 'reason':reason})
    identities={}
    for _,r in enrollments:
        identities.setdefault((r.get('Academy Name'),r.get('Coaching Center Location')),set()).add((r.get('Academy ID'),r.get('Sports')))
    booking_versions={}
    for _,r in trials or []:
        if r.get('Trial Booking ID'):
            booking_versions.setdefault(r['Trial Booking ID'],set()).add(repr(sorted((str(k),repr(v)) for k,v in r.items())))
    for source, records in [('Enrollment', enrollments), ('Trials', trials or [])]:
        seen=set()
        for line, row in records:
            signature=repr(sorted((str(k),repr(v)) for k,v in row.items()))
            if signature in seen:add(source,line,'Duplicate source row; counts use student IDs within each batch')
            seen.add(signature)
            if None in row or any(v is None for v in row.values()):
                add(source,line,'Malformed record: column count differs from header')
            if source=='Enrollment':
                missing=[k for k in ENROLLMENT_FIELDS if not str(row.get(k) or '').strip()]
                if missing:add(source,line,'Missing values: '+', '.join(missing))
                try:
                    start=enrollment_date(row.get('Start Date'))
                    end=enrollment_date(row.get('End Date'))
                    if end<start:raise ValueError()
                except ValueError:add(source,line,'Missing, invalid or reversed enrollment dates; use YYYY-MM-DD or DD-MM-YYYY')
                try:parse_slots(row.get('Slots'))
                except ValueError as exc:add(source,line,str(exc))
            else:
                if len(booking_versions.get(row.get('Trial Booking ID'),()))>1:
                    add(source,line,'Conflicting rows for Trial Booking ID; booking state unresolved')
                if row.get('Status') not in ('booked','cancelled','canceled'):
                    add(source,line,'Non-booked status requires review: '+str(row.get('Status')))
                if row.get('Rescheduled Date & Time'):
                    add(source,line,'Rescheduled date requires review')
                try:date.fromisoformat(row.get('Trial Scheduled Date') or '')
                except ValueError:add(source,line,'Missing or invalid Trial Scheduled Date; use YYYY-MM-DD')
                try:
                    if minutes(row.get('End Time') or '')<=minutes(row.get('Start Time') or ''):raise ValueError()
                except ValueError:add(source,line,'Missing, invalid or reversed trial times')
                for field in ('Academy','Coaching Center','Age Category','Status'):
                    if not str(row.get(field) or '').strip():add(source,line,'Missing '+field)
                if not str(row.get('Player DB ID') or '').strip():
                    add(source,line,'Missing shared Player DB ID; overlap and unique trial totals remain provisional')
                matches=identities.get((row.get('Academy'),row.get('Coaching Center')),set())
                if len(matches)!=1:add(source,line,'Unmatched or ambiguous trial academy/center; review exact source labels')
    for batch in batches:
        for reason in batch['issues']:add('Capacity',batch['source_row'],reason)
        if not batch.get('approved_mapping'):
            add('Capacity',batch['source_row'],'No approved batch mapping; confirm a temporary link before calculating')
    for batch in excluded:add('Capacity',batch['source_row'],batch['exclusion_reason'])
    return {'issues':issues,'counts':dict(Counter(i['source'] for i in issues)),
            'enrollment_rows':len(enrollments),'trial_rows':len(trials) if trials is not None else None,
            'scope':'All enrollment/trial rows; capacity rows for selected weekday',
            'read_only':True}
