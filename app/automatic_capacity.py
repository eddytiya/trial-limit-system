"""Automatic read-only age-batch occupancy from enrollment and trial snapshots."""
import csv
import hashlib
import io
import base64
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from trial_limit import eligible, RULE, nonnegative
from session_capacity import parse_slots, WEEKDAYS

BATCH_FIELDS = ('Academy ID','Coaching Center Location','Sports','Age Category')
ENROLLMENT_FIELDS = (*BATCH_FIELDS,'Academy Name','Player DB ID','Start Date','End Date')
TRIAL_FIELDS = ('Trial Booking ID',*BATCH_FIELDS,'Academy Name','Player DB ID',
                'Trial Date','Status')


def analyze_center_batches(enrollments, trials, reference, capacity=100):
    """One unique student per center/sport/age batch; slots and courses never split it."""
    capacity=nonnegative(capacity)
    if capacity<1:
        raise ValueError('Capacity must be positive')
    groups,issues,unresolved={},[],[]
    versions={}
    for _,row in trials or []:
        if row.get('Trial Booking ID'):
            versions.setdefault(row['Trial Booking ID'],set()).add(tuple(row.get(k) for k in TRIAL_FIELDS))
    conflicts={key for key,values in versions.items() if len(values)>1}
    for source,records in [('Enrollment',enrollments),('Trial',trials or [])]:
        for line,row in records:
            key=tuple(row.get(k) for k in BATCH_FIELDS)
            reasons=[]
            possible=True
            if source=='Enrollment':
                try:
                    possible=eligible(row,reference,RULE)
                except ValueError as exc:
                    reasons.append(str(exc))
            else:
                status=(row.get('Status') or '').casefold()
                conflicting=row.get('Trial Booking ID') in conflicts
                if status in ('cancelled','canceled') and not conflicting:
                    continue
                if conflicting:
                    reasons.append('Conflicting rows for the same Trial Booking ID; current booking state is unresolved')
                if status!='scheduled':
                    reasons.append('Missing/invalid Status; use Scheduled or Cancelled')
                try:
                    possible=date.fromisoformat(row.get('Trial Date') or '')==reference
                except ValueError:
                    reasons.append('Missing/invalid Trial Date')
                if not row.get('Trial Booking ID') or not row['Trial Booking ID'].strip():
                    reasons.append('Missing Trial Booking ID')
            missing=[k for k in (*BATCH_FIELDS,'Player DB ID') if not row.get(k) or not row[k].strip()]
            if missing:
                reasons.append('Missing required fields: '+', '.join(missing))
            if None in row:
                reasons.append('Malformed CSV record')
            # Preserve every existing complete center/age key, including historical groups.
            if all(v and v.strip() for v in key) and (source=='Enrollment' or possible):
                group=groups.setdefault(key,{'enrolled':set(),'trials':set(),'names':set(),'courses':set()})
                group['names'].add(row.get('Academy Name') or '')
                if row.get('Course Name') is not None:
                    group['courses'].add(row['Course Name'])
                if possible and not reasons:
                    group['enrolled' if source=='Enrollment' else 'trials'].add(row['Player DB ID'])
            if reasons:
                issues.append({'Source':source,'Source row number':line,
                               'Record ID':row.get('Enrollment ID') if source=='Enrollment' else row.get('Trial Booking ID'),
                               **{k:row.get(k) for k in BATCH_FIELDS},'Player DB ID':row.get('Player DB ID'),
                               'Start Date':row.get('Start Date'),'End Date':row.get('End Date'),
                               'Trial Date':row.get('Trial Date'),'Reason':'; '.join(reasons),
                               'Could affect counts':possible})
                if possible:
                    unresolved.append(key)
    result=[]
    for key,group in sorted(groups.items()):
        affected=sum(all(v is None or not v.strip() or v==actual for v,actual in zip(other,key)) for other in unresolved)
        enrolled=len(group['enrolled'])
        additional=len(group['trials']-group['enrolled']) if trials is not None else None
        known=enrolled+(additional or 0)
        assessed=not affected and trials is not None
        status=('Over Capacity' if known>capacity else 'Full' if known==capacity else 'Available') if assessed else (
            'Over Capacity — known count' if known>capacity else 'Not confirmed')
        result.append({**dict(zip(BATCH_FIELDS,key)),'Academy Name':sorted(group['names']),
                       'Reference date':reference.isoformat(),'Scope':'Center sport age batch; slots ignored',
                       'Courses combined':sorted(group['courses']),'Unique enrolled students':enrolled,
                       'Trial students':additional,
                       'Trial students already enrolled':len(group['trials']&group['enrolled']) if trials is not None else None,
                       'Trial data':'Supplied' if trials is not None else 'Not supplied',
                       'Total occupancy':known if trials is not None else None,'Known occupancy':known,'Capacity':capacity,
                       'Remaining places':max(0,capacity-known) if assessed else None,
                       'Known excess students':max(0,known-capacity),'Capacity status':status,
                       'Enrollment status':'Over Capacity' if enrolled>capacity else 'Full' if enrolled==capacity else 'Below limit',
                       'Data completeness':'Incomplete' if affected else 'Complete','Unresolved records':affected,
                       'Booking assessment':'Ready for capacity check' if assessed else 'Approval withheld',
                       'Eligibility rule':RULE})
    return result,issues


def read_source(path, required, supplied_text=None):
    """Read one snapshot; reject any file modified during that read."""
    path = Path(path)
    raw = path.read_bytes() if supplied_text is None else supplied_text.encode('utf-8')
    digest = hashlib.sha256(raw).hexdigest()
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    headers = reader.fieldnames or []
    if len(headers) != len(set(headers)):
        raise ValueError(f'{path.name}: duplicate column labels')
    missing = set(required)-set(headers)
    if missing:
        raise ValueError(f'{path.name}: missing columns: '+', '.join(sorted(missing)))
    rows=[]
    while True:
        line=reader.line_num+1
        try:
            row=next(reader)
        except StopIteration:
            break
        rows.append((line,row))
    if supplied_text is None and hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise ValueError(f'{path.name} changed during reading. Waiting for a stable file; retry refresh.')
    return rows, digest


def minute(raw):
    try:
        value=datetime.strptime(raw,'%I:%M %p')
    except (ValueError,TypeError):
        raise ValueError('Invalid/missing session time; use 6:00 PM format') from None
    return value.hour*60+value.minute


def analyze_automatic(enrollments, trials, reference, capacity=100):
    capacity=nonnegative(capacity)
    if capacity<1:
        raise ValueError('Capacity must be positive')
    groups,issues,unresolved={},[],[]
    def issue(source,line,row,reasons,possible,base,slots):
        issues.append({'Source':source,'Source row number':line,
                       'Record ID':row.get('Enrollment ID') if source=='Enrollment' else row.get('Trial Booking ID'),
                       **{k:row.get(k) for k in BATCH_FIELDS},'Player DB ID':row.get('Player DB ID'),
                       'Source Slots':row.get('Slots'), 'Trial Date':row.get('Trial Date'),
                       'Start Time':row.get('Start Time'),'End Time':row.get('End Time'),
                       'Reason':'; '.join(reasons),'Could affect counts':possible})
        if possible:
            unresolved.append((base,slots))
    def get(base,slot,row):
        key=(*base,slot[0],slot[1])
        group=groups.setdefault(key,{'enrolled':set(),'trials':set(),'names':set(),'labels':set(),'courses':set()})
        group['names'].add(row.get('Academy Name') or '')
        if row.get('Course Name') is not None:
            group['courses'].add(row['Course Name'])
        return group
    for line,row in enrollments:
        base=tuple(row.get(k) for k in BATCH_FIELDS)
        reasons=[]
        possible=True
        try:
            possible=eligible(row,reference,RULE)
        except ValueError as exc:
            reasons.append(str(exc))
        slots=None
        try:
            parsed=parse_slots(row.get('Slots'))
            slots={(minute(start),minute(end)) for day,_,start,end in parsed if day==WEEKDAYS[reference.weekday()]}
        except ValueError as exc:
            reasons.append(str(exc))
            parsed=[]
        missing=[k for k in (*BATCH_FIELDS,'Player DB ID') if not row.get(k) or not row[k].strip()]
        if missing:
            reasons.append('Missing required fields: '+', '.join(missing))
        if None in row:
            reasons.append('Malformed CSV record')
        # Catalog valid source slots even when that record is historical.
        if all(v and v.strip() for v in base) and slots is not None:
            for slot in slots:
                group=get(base,slot,row)
                group['labels'].update(label for day,label,start,end in parsed
                                       if day==WEEKDAYS[reference.weekday()] and (minute(start),minute(end))==slot)
                if possible and not reasons:
                    group['enrolled'].add(row['Player DB ID'])
        if reasons:
            issue('Enrollment',line,row,reasons,possible and (slots is None or bool(slots)),base,slots)
    booking_versions={}
    for _,row in trials or []:
        if row.get('Trial Booking ID'):
            booking_versions.setdefault(row['Trial Booking ID'],set()).add(tuple(row.get(k) for k in TRIAL_FIELDS))
    conflicts={key for key,versions in booking_versions.items() if len(versions)>1}
    for line,row in trials or []:
        base=tuple(row.get(k) for k in BATCH_FIELDS)
        reasons=[]
        status=(row.get('Status') or '').casefold()
        conflicting=row.get('Trial Booking ID') in conflicts
        if status in ('cancelled','canceled') and not conflicting:
            continue
        if conflicting:
            reasons.append('Conflicting rows for the same Trial Booking ID; current booking state is unresolved')
        if status!='scheduled':
            reasons.append('Missing/invalid Status; use Scheduled or Cancelled')
        try:
            trial_date=date.fromisoformat(row.get('Trial Date') or '')
            if trial_date!=reference:
                continue
        except ValueError:
            reasons.append('Missing/invalid Trial Date')
        slots=None
        try:
            start,end=minute(row.get('Start Time')),minute(row.get('End Time'))
            if end<=start:
                raise ValueError('Invalid/reversed trial interval')
            slots={(start,end)}
        except ValueError as exc:
            reasons.append(str(exc))
        missing=[k for k in (*BATCH_FIELDS,'Player DB ID','Trial Booking ID') if not row.get(k) or not row[k].strip()]
        if missing:
            reasons.append('Missing required fields: '+', '.join(missing))
        if None in row:
            reasons.append('Malformed trial CSV record')
        if all(v and v.strip() for v in base) and slots is not None:
            for slot in slots:
                group=get(base,slot,row)
                group['labels'].add(f'{WEEKDAYS[reference.weekday()]} {row.get("Start Time")} - {row.get("End Time")}')
                if not reasons:
                    group['trials'].add(row['Player DB ID'])
        if reasons:
            issue('Trial',line,row,reasons,True,base,slots)
    def clock(value):
        return datetime.strptime(f'{value//60:02d}:{value%60:02d}','%H:%M').strftime('%I:%M %p').lstrip('0')
    output=[]
    for key,g in sorted(groups.items()):
        affected=sum(all(v is None or not v.strip() or v==actual for v,actual in zip(base,key))
                     and (slots is None or (key[-2],key[-1]) in slots) for base,slots in unresolved)
        enrolled=len(g['enrolled'])
        additional=len(g['trials']-g['enrolled']) if trials is not None else None
        total=enrolled+additional if additional is not None else None
        known=enrolled+(additional or 0)
        complete=affected==0
        assessed=complete and trials is not None
        status=('Over Capacity' if known>capacity else 'Full' if known==capacity else 'Available') if assessed else (
            'Over Capacity — known count' if known>capacity else 'Not confirmed')
        output.append({**dict(zip(BATCH_FIELDS,key[:4])), 'Academy Name':sorted(g['names']),
                       'Session date':reference.isoformat(),'Weekday':WEEKDAYS[reference.weekday()],
                       'Start Time':clock(key[-2]),'End Time':clock(key[-1]), 'Source slot labels':sorted(g['labels']),
                       'Courses combined':sorted(g['courses']),'Unique enrolled students':enrolled,
                       'Trial students':additional,'Trial students already enrolled':len(g['trials']&g['enrolled']) if trials is not None else None,
                       'Trial data':'Supplied' if trials is not None else 'Not supplied',
                       'Total occupancy':total,'Known occupancy':known,'Capacity':capacity,
                       'Remaining places':max(0,capacity-known) if assessed else None,
                       'Known excess students':max(0,known-capacity), 'Capacity status':status,
                       'Enrollment status':'Over Capacity' if enrolled>capacity else 'Full' if enrolled==capacity else 'Below limit',
                       'Data completeness':'Complete' if complete else 'Incomplete', 'Unresolved records':affected,
                       'Booking assessment':'Ready for capacity check' if assessed else 'Approval withheld',
                       'Eligibility rule':RULE})
    return output,issues


def booking_decision(batch, proposed):
    proposed=nonnegative(proposed)
    if batch['Data completeness']!='Complete' or batch['Trial data']!='Supplied':
        return None
    return batch['Total occupancy']+proposed<=batch['Capacity']


def exceeded_centers(batches, capacity):
    """Only centers with a batch strictly above capacity; never sum age groups."""
    centers={}
    for batch in batches:
        if batch['Known occupancy']<=capacity:
            continue
        key=(batch['Academy ID'],batch['Coaching Center Location'])
        center=centers.setdefault(key,{'Academy ID':key[0],'Coaching Center Location':key[1],
            'Academy Name':set(),'Sports':set(),'Exceeded batches':[], 'Threshold':capacity,
            'Highest known batch count':0,'Largest known excess':0})
        center['Academy Name'].update(batch['Academy Name'])
        center['Sports'].add(batch['Sports'])
        center['Exceeded batches'].append(batch)
        center['Highest known batch count']=max(center['Highest known batch count'],batch['Known occupancy'])
        center['Largest known excess']=max(center['Largest known excess'],batch['Known occupancy']-capacity)
    return [{**c,'Academy Name':sorted(c['Academy Name']),'Sports':sorted(c['Sports'])}
            for c in sorted(centers.values(),key=lambda c:(-c['Largest known excess'],c['Coaching Center Location'],c['Academy ID']))]


def automatic_snapshot(payload,enrollment_path,trial_path,capacity=100,raw_trial_status_rule='pending'):
    if 'trials_text' in payload and (payload.get('trials_filename') or '').lower().endswith('.xlsx'):
        raise ValueError('This browser tab is outdated and read the XLSX as CSV text. Press Ctrl+Shift+R, then select the trial XLSX again. Do not rename source columns.')
    if 'csv_text' in payload and (payload.get('filename') or '').lower().endswith('.xlsx'):
        raise ValueError('The enrollment input requires a CSV file. Select the enrollment CSV in the first field.')
    reference=date.fromisoformat(payload.get('reference_date') or datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat())
    enrollments,enrollment_hash=read_source(enrollment_path,ENROLLMENT_FIELDS,payload.get('csv_text'))
    raw_xlsx='trials_xlsx' in payload or 'trials_text' not in payload and trial_path is not None and Path(trial_path).suffix.lower()=='.xlsx'
    trial_text=payload.get('trials_text')
    if trial_text is None and not raw_xlsx and trial_path is not None and Path(trial_path).is_file():
        trial_text=Path(trial_path).read_text(encoding='utf-8-sig')
    trial_headers=next(csv.reader(io.StringIO(trial_text.lstrip('\ufeff'))),[]) if trial_text is not None else []
    raw_csv='Trial Scheduled Date' in trial_headers and 'Academy' in trial_headers
    raw_mode=raw_xlsx or raw_csv
    has_trials=raw_xlsx or 'trials_text' in payload or trial_path is not None and Path(trial_path).is_file()
    raw_rows=None;raw_info=None
    if raw_mode:
        from raw_trial_source import read_trial_xlsx,combine_raw_trials
        if raw_xlsx:
            raw_bytes=base64.b64decode(payload['trials_xlsx'],validate=True) if 'trials_xlsx' in payload else None
            raw_rows,trial_hash=read_trial_xlsx(Path(trial_path or 'uploaded_trials.xlsx'),raw_bytes)
        else:
            from raw_trial_source import read_raw_trial_csv
            raw_rows,trial_hash=read_raw_trial_csv(Path(trial_path or 'uploaded_trials.csv'),payload.get('trials_text'))
        trials=None
    else:
        trials,trial_hash=(read_source(trial_path or Path('uploaded_trials.csv'),TRIAL_FIELDS,payload.get('trials_text'))
                           if has_trials else (None,None))
    batches,quality=analyze_center_batches(enrollments,trials,reference,capacity)
    if raw_mode:
        batches,raw_quality,raw_info=combine_raw_trials(batches,enrollments,raw_rows,reference,capacity,raw_trial_status_rule,
                                                     'Raw trial workbook' if raw_xlsx else 'Raw trial CSV')
        quality.extend(raw_quality)
    # Verify again after calculation; source data must be one consistent snapshot.
    for path,expected,uploaded in [(enrollment_path,enrollment_hash,'csv_text' in payload),
                                   (trial_path,trial_hash,'trials_text' in payload or 'trials_xlsx' in payload)]:
        if path is not None and expected is not None and not uploaded and hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Source changed during calculation; retry refresh')
    return {'batches':batches,'exceeded_centers':exceeded_centers(batches,capacity),
            'quality':quality,'capacity':capacity,'reference_date':reference.isoformat(),
            'scope':'center_sport_age',
            'enrollment_source':payload.get('filename',Path(enrollment_path).name),
            'trial_source':payload.get('trials_filename',Path(trial_path).name if trial_path else None) if has_trials else None,
            'enrollment_hash':enrollment_hash,'trial_hash':trial_hash,'enrollment_rows':len(enrollments),
            'trial_rows':len(raw_rows) if raw_rows is not None else len(trials) if trials is not None else None,
            'trial_identity_complete':raw_info['unique_trial_students_confirmed'] if raw_info is not None else True,
            'raw_trial_info':raw_info,
            'updated_at':datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(timespec='seconds'),
            'uploaded_snapshot':'csv_text' in payload or 'trials_text' in payload or 'trials_xlsx' in payload,
            'refresh_seconds':15}
