"""Capacity per exact age/course group and listed session on a selected date."""
import re
from datetime import datetime
from trial_limit import GROUP_FIELDS, Group, RULE, eligible, result

WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
SLOT_PATTERN = re.compile(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) (\d{1,2}:\d{2} [AP]M) - (\d{1,2}:\d{2} [AP]M)')


def parse_slots(raw):
    """Validate complete cell; retain exact labels. Never repair malformed text."""
    if not raw or not raw.strip():
        raise ValueError('Missing Slots; session attendance cannot be established')
    slots = []
    for label in raw.split(', '):
        match = SLOT_PATTERN.fullmatch(label)
        if not match:
            raise ValueError('Invalid Slots format; no source values corrected')
        weekday, start, end = match.groups()
        try:
            start_time = datetime.strptime(start, '%I:%M %p').time()
            end_time = datetime.strptime(end, '%I:%M %p').time()
        except ValueError:
            raise ValueError('Invalid time in Slots') from None
        if end_time <= start_time:
            raise ValueError('Reversed, zero-length, or overnight Slots requires review')
        slots.append((weekday, label, start, end))
    return slots


def analyze_sessions(rows, reference):
    groups, issues, unresolved, session_labels = {}, [], [], {}
    weekday = WEEKDAYS[reference.weekday()]
    for line, row in rows:
        key = tuple(row.get(k) for k in GROUP_FIELDS)
        reasons = []
        missing = [k for k in (*GROUP_FIELDS, 'Player DB ID') if not row.get(k) or not row[k].strip()]
        if missing:
            reasons.append('Missing required fields: ' + ', '.join(missing))
        if None in row or any(row.get(k) is None for k in (*GROUP_FIELDS, 'Player DB ID', 'Start Date', 'End Date', 'Slots')):
            reasons.append('Malformed CSV record (column count)')
        try:
            slots = [s for s in parse_slots(row.get('Slots')) if s[0] == weekday]
        except ValueError as exc:
            reasons.append(str(exc))
            slots = None
        if all(v is not None and v.strip() for v in key) and slots is not None:
            for _, label, start, end in slots:
                session_key = (*key, label)
                group = groups.setdefault(session_key, Group(session_key))
                group.academies.add(row.get('Academy Name') or '')
                session_labels[session_key] = (start, end)
        possible = True
        try:
            possible = eligible(row, reference, RULE)
        except ValueError as exc:
            reasons.append(str(exc))
        if reasons:
            issues.append({'Source row number':line, 'Enrollment ID':row.get('Enrollment ID'),
                           **{k:row.get(k) for k in GROUP_FIELDS}, 'Player DB ID':row.get('Player DB ID'),
                           'Slots':row.get('Slots'), 'Slot Type':row.get('Slot Type'),
                           'Reason':'; '.join(reasons), 'Could affect counts':possible and (slots is None or bool(slots))})
            if possible and (slots is None or slots):
                unresolved.append((key, None if slots is None else {s[1] for s in slots}))
        elif possible:
            for _, label, _, _ in slots:
                groups[(*key, label)].students.add(row['Player DB ID'])
    for group in groups.values():
        group.complete = not any(
            all(v is None or not v.strip() or v == actual for v,actual in zip(key,group.key))
            and (labels is None or group.key[-1] in labels)
            for key,labels in unresolved)
    return list(groups.values()), issues, session_labels


def session_result(group, reference, capacity, labels):
    start, end = labels[group.key]
    return {**result(group, reference, capacity, RULE), 'Session date':reference.isoformat(),
            'Session weekday':WEEKDAYS[reference.weekday()], 'Session start':start,
            'Session end':end, 'Session slot':group.key[-1],
            'Capacity scope':'Age category + course + listed session'}
