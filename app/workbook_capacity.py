"""Read-only MAIN batch schedule and explicit links to enrollment groups.

Only stdlib XML/ZIP readers are used. No Excel writer is present.
"""
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from trial_limit import RULE, eligible, nonnegative
from session_capacity import WEEKDAYS, parse_slots

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
DAY_WORDS = {'mon':0, 'monday':0, 'tue':1, 'tues':1, 'tuesday':1,
             'wed':2, 'wednesday':2, 'thu':3, 'thur':3, 'thurs':3, 'thursday':3,
             'fri':4, 'friday':4, 'sat':5, 'saturday':5, 'sun':6, 'sunday':6}
_CACHE = {}


def minutes(raw):
    match = re.fullmatch(r'\s*(\d{1,2})(?:[:.](\d{2}))?\s*([ap]m)\s*', raw, re.I)
    if not match:
        raise ValueError('Timing needs review; AM/PM must be explicit')
    hour, minute, meridiem = match.groups()
    hour, minute = int(hour), int(minute or 0)
    if not 1 <= hour <= 12 or minute > 59:
        raise ValueError('Invalid batch timing')
    return (hour % 12 + (12 if meridiem.lower() == 'pm' else 0))*60 + minute


def time_range(raw):
    # Ignore explicit parenthesized description only; retain original for display.
    value = re.sub(r'\([^)]*\)', '', raw or '').strip()
    pieces = re.split(r'\s*\bto\b\s*|\s*-\s*', value, flags=re.I)
    if len(pieces) != 2:
        raise ValueError('Missing or ambiguous batch timing')
    start, end = map(minutes, pieces)
    if end <= start:
        raise ValueError('Reversed or overnight batch timing needs review')
    return start, end


def weekdays(raw):
    # Parse only a recognized leading day list/range. Unrecognized day text stays unresolved.
    leading = re.split(r'\(|\b(?:Elite|Adv|batch|basic|intermediate|advance)\b|\s-\s', raw or '', maxsplit=1, flags=re.I)[0].strip()
    range_match = re.fullmatch(r'([A-Za-z]+)\s+to\s+([A-Za-z]+)', leading, re.I)
    if range_match:
        left, right = [DAY_WORDS.get(x.lower()) for x in range_match.groups()]
        if left is None or right is None or left > right:
            raise ValueError('Unrecognized weekday range')
        return list(range(left, right+1))
    tokens = [x for x in re.split(r'\s*(?:,|&|\band\b)\s*', leading, flags=re.I) if x]
    if not tokens or any(t.lower() not in DAY_WORDS for t in tokens):
        raise ValueError('Missing or ambiguous Days')
    return sorted({DAY_WORDS[t.lower()] for t in tokens})


def divisions(days, proficiency):
    """Only split explicit age lists. Ranges/shorthand are not invented."""
    values = re.findall(r'\bU\d+\b', days or '')
    if values:
        # U6 to U18 and U5,7,9 do not define every separate batch reliably.
        if re.search(r'U\d+\s+to\s+U\d+|U\d+\s*,\s*\d|\babove\b|Girls|Elite|Development', days, re.I):
            return [(days, None, 'Age/course division requires explicit matching')]
        return [(age, age, '') for age in dict.fromkeys(values)]
    if proficiency and proficiency.strip() and proficiency not in ('NA', 'NAFT'):
        return [(proficiency, None, 'Proficiency is not an exact CSV age/course identifier')]
    return [('Division not supplied', None, 'Age/proficiency division is missing or ambiguous')]


def read_main(path, raw=None):
    """Read only MAIN; resolve actual merged center cells, never forward-fill blanks."""
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes() if raw is None else raw).hexdigest()
    cached = _CACHE.get((str(path.resolve()), digest))
    if cached is not None:
        return cached, digest
    with zipfile.ZipFile(path if raw is None else io.BytesIO(raw)) as archive:
        shared = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared = [''.join(t.text or '' for t in si.iter('{'+NS['m']+'}t'))
                      for si in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheet = next((s for s in workbook.find('m:sheets', NS) if s.get('name') == 'MAIN'), None)
        if sheet is None:
            raise ValueError('Capacity workbook must contain MAIN sheet')
        relations = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target = next(r.get('Target') for r in relations if r.get('Id') == sheet.get('{'+REL+'}id'))
        member = target.lstrip('/') if target.startswith('/') else 'xl/'+target
        root = ET.fromstring(archive.read(member))
        cells = {}
        for row in root.find('m:sheetData', NS):
            for cell in row:
                value = cell.find('m:v', NS)
                value = value.text if value is not None else None
                if cell.get('t') == 's' and value is not None:
                    value = shared[int(value)]
                elif cell.get('t') == 'inlineStr':
                    value = ''.join(t.text or '' for t in cell.iter('{'+NS['m']+'}t'))
                cells[cell.get('r')] = value
        expected_headers = {'D2':'Sport','E2':'Centre','G2':'Batch Time','H2':'Days'}
        if any(cells.get(address) != label for address,label in expected_headers.items()):
            raise ValueError('MAIN sheet layout differs from the supplied batch reference; headers need review')
        merged_centers = {}
        merges = root.find('m:mergeCells', NS)
        for merged in merges if merges is not None else []:
            match = re.fullmatch(r'E(\d+):E(\d+)', merged.get('ref', ''))
            if match:
                first, last = map(int, match.groups())
                for row in range(first, last+1):
                    merged_centers[row] = (cells.get(f'E{first}'), f'E{first}')
        records = []
        for row in root.find('m:sheetData', NS):
            number = int(row.get('r'))
            if number < 3 or not any(cells.get(f'{c}{number}') for c in ('D','E','G','H')):
                continue
            center, origin = merged_centers.get(number, (cells.get(f'E{number}'), f'E{number}'))
            records.append({'row': number, 'sport': cells.get(f'D{number}'), 'center': center,
                            'city':cells.get(f'F{number}'),
                            'center_cell': origin, 'time': cells.get(f'G{number}'),
                            'days': cells.get(f'H{number}'),
                            'capacities': [cells.get(f'{c}{number}') for c in ('M','P','S','V','Y','AB','AE')],
                            'reported_counts': [cells.get(f'{c}{number}') for c in ('O','R','U','X','AA','AD','AG')],
                            'proficiency': [cells.get(f'{c}{number}') for c in ('N','Q','T','W','Z','AC','AF')]})
    if raw is None and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Capacity workbook changed while reading; reload to get a consistent snapshot')
    _CACHE.clear()
    _CACHE[(str(path.resolve()),digest)] = records
    return records, digest


def catalog(records, reference):
    batches, issues = [], []
    day = reference.weekday()
    for record in records:
        reasons = []
        try:
            days = weekdays(record['days'])
        except ValueError as exc:
            days = None
            reasons.append(str(exc))
        try:
            times = time_range(record['time'])
        except ValueError as exc:
            times = None
            reasons.append(str(exc))
        if not record['sport'] or not record['center']:
            reasons.append('Missing Sport or Centre')
        if re.search(r'closed|on hold|renovation', record['center'] or '', re.I):
            reasons.append('Source marks center closed, on hold, or under renovation')
        if reasons:
            issues.append({'Source file':'Capacity workbook', 'Source sheet':'MAIN', 'Source row number':record['row'],
                           'Sport':record['sport'], 'Centre':record['center'], 'Batch Time':record['time'],
                           'Days':record['days'], 'Reason':'; '.join(reasons)})
        if days is not None and day not in days:
            continue
        for index,(label,age,division_issue) in enumerate(divisions(record['days'],record['proficiency'][day])):
            batch = {**record, 'id':f'MAIN:{record["row"]}:{index}', 'division':label, 'age':age,
                     'start':times[0] if times else None, 'end':times[1] if times else None,
                     'issues':[*reasons, *([division_issue] if division_issue else [])]}
            if division_issue:
                issues.append({'Source file':'Capacity workbook', 'Source sheet':'MAIN', 'Source row number':record['row'],
                               'Sport':record['sport'], 'Centre':record['center'], 'Batch Time':record['time'],
                               'Days':record['days'], 'Reason':division_issue})
            batches.append(batch)
    # Duplicate age/time definitions cannot silently become independent 100-place pools.
    signatures = {}
    for batch in batches:
        signature = (batch['sport'],batch['center'],batch['start'],batch['end'],batch['division'])
        signatures.setdefault(signature,[]).append(batch)
    for repeated in signatures.values():
        if len(repeated)>1:
            for batch in repeated:
                batch['issues'].append('Duplicate workbook definition for this center, time and division')
                issues.append({'Source file':'Capacity workbook','Source sheet':'MAIN','Source row number':batch['row'],
                               'Reason':'Duplicate workbook definition for this center, time and division'})
    return batches, issues


def enrollment_targets(rows):
    targets = {}
    for _,row in rows:
        key = tuple(row.get(k) for k in ('Academy ID','Coaching Center Location','Sports'))
        if not all(v and v.strip() for v in key):
            continue
        target = targets.setdefault(key, {'academy_id':key[0], 'center':key[1], 'sport':key[2], 'academy_names':set(), 'ages':{}})
        target['academy_names'].add(row.get('Academy Name') or '')
        age,course = row.get('Age Category'),row.get('Course Name')
        if age and age.strip() and course and course.strip():
            target['ages'].setdefault(age,set()).add(course)
    return [{'id':json.dumps(key,ensure_ascii=False), **value,
             'academy_names':sorted(value['academy_names']), 'ages':{k:sorted(v) for k,v in value['ages'].items()}}
            for key,value in targets.items()]


def check_batch(batch, rows, reference, capacity, target, age, course=None, confirmed=False,
                trials=None, proposed=None):
    """Course=None aggregates distinct students across all courses in an age batch."""
    reasons = list(batch['issues'])
    if not confirmed or not target:
        reasons.append('CSV group link not confirmed')
    if not age or not age.strip():
        reasons.append('Exact CSV age category not selected')
    if batch['age'] is not None and age != batch['age']:
        reasons.append('Selected age differs from explicit workbook age')
    if batch['age'] is not None and course is not None:
        reasons.append('This workbook age batch shares one limit across courses; select All courses')
    # Division with unclear age/proficiency can only produce a provisional count.
    if target:
        if target['sport'] != batch['sport']:
            # Different labels are acceptable only through the explicit confirmed link.
            if not confirmed:
                reasons.append('Sport label needs explicit matching')
    students, issues = set(), []
    key_fields = ('Academy ID','Coaching Center Location','Sports')
    expected = (target['academy_id'],target['center'],target['sport']) if target else None
    for line,row in rows:
        if not expected:
            break
        if not all(not row.get(k) or not row[k].strip() or row[k] == v for k,v in zip(key_fields,expected)):
            continue
        if row.get('Age Category') and row['Age Category'].strip() and row['Age Category'] != age:
            continue
        if course is not None and row.get('Course Name') and row['Course Name'].strip() and row['Course Name'] != course:
            continue
        row_reasons = []
        possible = True
        try:
            possible = eligible(row,reference,RULE)
        except ValueError as exc:
            row_reasons.append(str(exc))
        if not possible:
            continue
        try:
            slots = parse_slots(row.get('Slots'))
            matches = any(WEEKDAYS.index(day) == reference.weekday()
                          and minutes(start) == batch['start'] and minutes(end) == batch['end']
                          for day,_,start,end in slots)
            if not matches:
                continue
        except ValueError as exc:
            row_reasons.append(str(exc))
        missing = [k for k in (*key_fields,'Player DB ID','Age Category','Course Name') if not row.get(k) or not row[k].strip()]
        if missing:
            row_reasons.append('Missing required fields: '+', '.join(missing))
        if None in row:
            row_reasons.append('Malformed CSV record')
        if row_reasons:
            issues.append({'Source file':'Enrollment CSV', 'Source row number':line, 'Enrollment ID':row.get('Enrollment ID'),
                           'Player DB ID':row.get('Player DB ID'), 'Slots':row.get('Slots'), 'Reason':'; '.join(row_reasons)})
        else:
            students.add(row['Player DB ID'])
    if issues:
        reasons.append(f'{len(issues)} unresolved enrollment records could affect this batch')
    complete = not reasons
    count = len(students) if target and age else None
    trials = nonnegative(trials) if trials is not None else None
    proposed = nonnegative(proposed) if proposed is not None else None
    total = count+trials if count is not None and trials is not None else None
    future = total+proposed if total is not None and proposed is not None else None
    decision = future <= capacity if complete and future is not None else None
    return {'Workbook sheet':'MAIN', 'Workbook row':batch['row'], 'Workbook center cell':batch['center_cell'],
            'Sports':target['sport'] if target else None,
            'Coaching Center Location':target['center'] if target else None,
            'Reference Sport':batch['sport'], 'Reference Centre':batch['center'],
            'Eligibility rule':RULE,
            'Batch Time':batch['time'], 'Days':batch['days'],
            'Batch division':batch['division'], 'Session date':reference.isoformat(),
            'CSV Academy ID':target['academy_id'] if target else None,
            'CSV center':target['center'] if target else None, 'CSV sport':target['sport'] if target else None,
            'CSV age':age, 'CSV course':course if course is not None else 'All courses (unique students)',
            'Unique enrolled students':count, 'Simulated trial students':trials if trials is not None else 'Not supplied',
            'Total occupancy':total, 'Capacity':capacity,
            'Remaining places':max(0,capacity-total) if total is not None else None,
            'Excess students':max(0,total-capacity) if total is not None else None,
            'Capacity status':('Available' if total<capacity else 'Full' if total==capacity else 'Over Capacity') if total is not None else 'Not confirmed',
            'Data completeness':'Complete' if complete else 'Incomplete', 'Reasons':reasons,
            'Proposed occupancy':future, 'Booking allowed':decision, 'issues':issues}
