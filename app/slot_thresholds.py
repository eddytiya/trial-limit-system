"""Read-only weekday thresholds; explicit links never rewrite source center labels."""
import hashlib
import base64
import csv
import io
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import Counter
from automatic_capacity import read_source, ENROLLMENT_FIELDS
from workbook_capacity import read_main, time_range, weekdays, minutes, DAY_WORDS
from session_capacity import parse_slots, WEEKDAYS
from trial_limit import eligible, RULE, today
from app_paths import MAPPED_DIR


def integer(value):
    if value is None or not str(value).isdigit():
        raise ValueError('Missing or invalid non-negative whole-number capacity')
    return int(value)


def read_capacity_csv(raw):
    """Accept a MAIN-sheet CSV export or explicitly labelled one-row-per-day slots."""
    rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'),newline='')))
    header_index=next((i for i,r in enumerate(rows[:3]) if all(k in r for k in ('Sport','Centre','Batch Time'))),None)
    if header_index is None:raise ValueError('Capacity CSV needs Sport, Centre and Batch Time headers')
    header=rows[header_index]
    def val(row,key):
        i=header.index(key) if key in header else len(row)
        return row[i] if i<len(row) else ''
    long='Weekday' in header
    if long and 'Total Capacity' not in header:raise ValueError('Capacity CSV requires Total Capacity')
    total_indexes=[i for i,h in enumerate(header) if h=='Total Capacity']
    if not long and len(total_indexes)!=7:
        raise ValueError('CSV must be a MAIN export with seven weekday Total Capacity columns, or use Sport, Centre, Batch Time, Weekday, Total Capacity, Actual Capacity, Proficiency')
    if not long:
        if header_index==0:raise ValueError('MAIN CSV export needs its weekday header row')
        day_header=rows[header_index-1]
        if any(i>=len(day_header) or day_header[i]!=WEEKDAYS[d] for d,i in enumerate(total_indexes)):
            raise ValueError('MAIN CSV weekday headers must be Monday through Sunday in order')
    output=[]
    for number,row in enumerate(rows[header_index+1:],header_index+2):
        if not any(row):continue
        capacities=['']*7;counts=['']*7;proficiency=['']*7;defined=None
        if long:
            day=DAY_WORDS.get(val(row,'Weekday').lower())
            if day is None:raise ValueError('Invalid Weekday in capacity CSV source row '+str(number))
            capacities[day]=val(row,'Total Capacity');counts[day]=val(row,'Actual Capacity')
            proficiency[day]=val(row,'Proficiency');defined=[day]
        else:
            for day,i in enumerate(total_indexes):
                capacities[day]=row[i] if i<len(row) else ''
                proficiency[day]=row[i+1] if i+1<len(row) else ''
                counts[day]=row[i+2] if i+2<len(row) else ''
        output.append({'row':number,'sport':val(row,'Sport'),'center':val(row,'Centre'),
            'city':val(row,'CITY'),
            'time':val(row,'Batch Time'),'days':val(row,'Days') or (val(row,'Weekday') if long else ''),
            'capacities':capacities,'reported_counts':counts,'proficiency':proficiency,'defined_weekdays':defined})
    return output,hashlib.sha256(raw).hexdigest()


def schedule(records, reference):
    output=[]
    day=reference.weekday()
    for record in records:
        if record.get('defined_weekdays') is not None and day not in record['defined_weekdays']:continue
        raw=record['capacities'][day]
        # NA is not a zero-capacity session. Retain missing definitions for review.
        # Owner confirmed NA/NAFT indicate no scheduled session on this weekday.
        markers={'NA','N/A','NAFT'}
        if any(str(value or '').strip().upper() in markers for value in
               (raw,record['proficiency'][day],record['reported_counts'][day])):
            continue
        issues=[];capacity=None;times=None
        try:days=weekdays(record['days'])
        except ValueError as exc:days=None;issues.append(str(exc))
        if days is not None and day not in days and not raw:
            continue
        # Owner confirmed populated weekday capacity columns override Days prose.
        try:capacity=integer(raw)
        except ValueError as exc:issues.append(str(exc))
        try:times=time_range(record['time'])
        except ValueError as exc:issues.append(str(exc))
        if not record['sport'] or not record['center']:issues.append('Missing Sport or Centre')
        if not record['proficiency'][day] or not record['proficiency'][day].strip():
            issues.append('Missing Proficiency; batch division needs review')
        if any(word in (record['center'] or '').lower() for word in ('on hold','closed','renovation')):
            issues.append('Source marks center unavailable; review before use')
        try:reported=integer(record['reported_counts'][day])
        except ValueError:reported=None
        output.append({'id':str(record['row']),'source_row':record['row'],'sport':record['sport'],
            'center':record['center'],'time':record['time'],'days':record['days'],
            'city':record.get('city'),
            'source_center':record.get('source_center',record['center']),
            'center_resolution':record.get('center_resolution','Original source label'),
            'weekday':WEEKDAYS[day],'reference_date':reference.isoformat(),
            'division':record['proficiency'][day],'capacity':capacity,'raw_capacity':raw,
            'workbook_reported_count':reported,
            'reference_status':('Needs review' if issues else 'Count not supplied' if reported is None else
                'Over Capacity' if reported>capacity else 'Full' if reported==capacity else 'Available'),
            'reference_remaining':max(0,capacity-reported) if not issues and reported is not None else None,
            'reference_excess':max(0,reported-capacity) if not issues and reported is not None else None,
            'start':times[0] if times else None,
            'end':times[1] if times else None,'issues':issues})
    signatures=Counter((r['center'],r['city'],r['sport'],r['start'],r['end'],r['division']) for r in output if r['start'] is not None)
    for r in output:
        same_slot=[o for o in output if (o['center'],o['city'],o['sport'],o['start'],o['end'])==(r['center'],r['city'],r['sport'],r['start'],r['end'])]
        duplicate=signatures[r['center'],r['city'],r['sport'],r['start'],r['end'],r['division']]>1
        open_overlap=len(same_slot)>1 and any(o['division'] in ('Open','Open Age') for o in same_slot)
        if duplicate or open_overlap:
            r['issues'].append('Duplicate proficiency pool or overlapping unrestricted Open pool at this center/sport/time; capacity needs review')
            r['reference_status']='Needs review';r['reference_remaining']=None;r['reference_excess']=None
    return output


def enrollment_sport(row):
    # User confirmed these two labels refer to the same sport at CNS Amanora.
    if (row.get('Academy ID')=='6818b03fe167f7292b3407e4'
            and row.get('Coaching Center Location')=='CNS Amanora, Hadapsar'
            and row.get('Sports') in ('Table tennis','TableTennis')):
        return 'TableTennis'
    return row.get('Sports')


def enrollment_target_key(row):
    return tuple(row.get(k) for k in ('Academy ID','Academy Name','Coaching Center Location'))+(enrollment_sport(row),)


def targets(enrollments, trials=None):
    groups={}
    for _,r in enrollments:
        key=enrollment_target_key(r)
        if not all(key):continue
        groups.setdefault(key,set())
        if r.get('Age Category'):groups[key].add(r['Age Category'])
    output=[]
    for i,(k,ages) in enumerate(sorted(groups.items())):
        pairs=sorted({(r.get('Age Category') or '',r.get('Course Name') or '') for _,r in enrollments
            if enrollment_target_key(r)==k
            and r.get('Age Category') and r.get('Course Name')})
        trial_pairs={(r['Age Category'],r['Course Details']) for _,r in trials or []
            if r.get('Academy')==k[1] and r.get('Coaching Center')==k[2]
            and r.get('Age Category') and r.get('Course Details')}
        pairs=sorted(set(pairs)|trial_pairs)
        output.append({'id':str(i),'academy_id':k[0],'academy':k[1],'center':k[2],'sport':k[3],
            'ages':sorted(ages|{a for a,c in pairs}),'proficiency_memberships':[{'age':a,'course':c} for a,c in pairs]})
    return output


def evaluate(batch, target, age, enrollments, trials, reference, proficiency_pairs=None):
    """Only the explicitly selected workbook pool and enrollment group are compared."""
    issues=[{'source':'Capacity workbook','row':batch['source_row'],'reason':s} for s in batch['issues']]
    enrolled=set();trial_ids=set();contacts=set();missing_contacts=0;overlap=0;booked_rows=0;duplicates=0
    division=batch.get('division');unrestricted=division in ('Open','Open Age')
    # Owner confirmed Open pools cover all ages and all proficiency levels.
    if unrestricted:age=''
    pairs=set(tuple(p) for p in proficiency_pairs or [])
    if not unrestricted and not pairs:
        raise ValueError('Select exact age/course combinations for proficiency '+str(division or '(missing)')+'; only Open has no proficiency restriction')
    def problem(source,line,reason):issues.append({'source':source,'row':line,'reason':reason})
    def member(r,course_field,source,line):
        if unrestricted:return True
        a,c=r.get('Age Category'),r.get(course_field)
        if not a or not c:
            # Missing dimensions can belong to any compatible selected combination.
            if any((not a or a==pa) and (not c or c==pc) for pa,pc in pairs):
                problem(source,line,'Missing age/course; proficiency membership unresolved')
            return False
        return (a,c) in pairs
    def match(r):
        return (not r.get('Sports') or enrollment_sport(r)==target['sport']) and all(not r.get(k) or r[k]==v for k,v in (
            ('Academy ID',target['academy_id']),('Coaching Center Location',target['center'])))
    for line,r in enrollments:
        if not match(r) or age and r.get('Age Category') and r['Age Category']!=age:continue
        if None in r or any(v is None for v in r.values()):
            problem('Enrollment',line,'Malformed record; column count differs from header');continue
        try:
            if not eligible(r,reference,RULE):continue
        except ValueError as exc:problem('Enrollment',line,str(exc));continue
        try:
            slots=parse_slots(r.get('Slots'))
            fits=any(d==WEEKDAYS[reference.weekday()] and (minutes(s),minutes(e))==(batch['start'],batch['end']) for d,_,s,e in slots)
        except ValueError as exc:problem('Enrollment',line,str(exc));continue
        if not fits:continue
        if not member(r,'Course Name','Enrollment',line):continue
        needed=('Academy ID','Coaching Center Location','Sports','Player DB ID')+ (('Age Category',) if age else ())
        if any(not r.get(k) or not r[k].strip() for k in needed):
            problem('Enrollment',line,'Missing identifier or selected group field');continue
        enrolled.add(r['Player DB ID'])
    identities={(r.get('Academy ID'),enrollment_sport(r)) for _,r in enrollments
        if r.get('Academy Name')==target['academy'] and r.get('Coaching Center Location')==target['center']}
    versions={}
    for _,r in trials or []:
        if r.get('Trial Booking ID'):
            versions.setdefault(r['Trial Booking ID'],set()).add(repr(sorted((str(k),repr(v)) for k,v in r.items())))
    conflicts={key for key,values in versions.items() if len(values)>1}
    for line,r in trials or []:
        if r.get('Academy') and r['Academy']!=target['academy'] or r.get('Coaching Center') and r['Coaching Center']!=target['center']:continue
        if age and r.get('Age Category') and r['Age Category']!=age:continue
        if r.get('Trial Booking ID') in conflicts:
            problem('Trials',line,'Conflicting rows for Trial Booking ID; booking state unresolved');continue
        if r.get('Status') in ('cancelled','canceled'):continue
        if None in r or any(v is None for v in r.values()):
            problem('Trials',line,'Malformed record; column count differs from header');continue
        try:scheduled=date.fromisoformat(r.get('Trial Scheduled Date') or '')
        except ValueError:problem('Trials',line,'Missing or invalid Trial Scheduled Date');continue
        moved=r.get('Rescheduled Date & Time')
        if moved:
            try:relevant=datetime.fromisoformat(moved).date()==reference or scheduled==reference
            except ValueError:relevant=True
            if relevant:problem('Trials',line,'Rescheduled date requires review');continue
        if scheduled!=reference:continue
        try:fits=(minutes(r.get('Start Time') or ''),minutes(r.get('End Time') or ''))==(batch['start'],batch['end'])
        except ValueError:problem('Trials',line,'Missing or ambiguous trial time');continue
        if not fits:continue
        if not member(r,'Course Details','Trials',line):continue
        if not r.get('Academy') or not r.get('Coaching Center'):
            problem('Trials',line,'Missing trial academy or center; could affect this slot');continue
        if len(identities)!=1:problem('Trials',line,'Trial academy/center maps to multiple sports; no sport guessed');continue
        if r.get('Status')!='booked':problem('Trials',line,'Non-booked status requires review: '+str(r.get('Status')));continue
        if age and not r.get('Age Category'):problem('Trials',line,'Missing trial age category');continue
        booked_rows+=1
        student=r.get('Player DB ID')
        if student and student.strip():
            if student in trial_ids:duplicates+=1
            trial_ids.add(student)
        else:
            contact=(r.get('Player Name'),r.get('Mobile number'))
            if all(v and v.strip() for v in contact):
                if contact in contacts:duplicates+=1
                contacts.add(contact)
            else:missing_contacts+=1;problem('Trials',line,'Missing name/mobile; trial retained separately')
    overlap=len(trial_ids&enrolled)
    provisional=len(enrolled)+len(trial_ids-enrolled)+len(contacts)+missing_contacts
    confirmed=trials is not None and not contacts and not missing_contacts and not issues
    total=provisional if confirmed else None;capacity=batch['capacity']
    return {'enrolled':len(enrolled),'booked_rows':booked_rows,'duplicates_excluded':duplicates,
        'already_enrolled_excluded':overlap,'additional_trials':len(trial_ids-enrolled)+len(contacts)+missing_contacts if trials is not None else None,
        'preview':provisional if trials is not None else None,'confirmed_total':total,'capacity':capacity,
        'known_excess':max(0,len(enrolled)+len(trial_ids-enrolled)-capacity) if capacity is not None else None,
        'remaining':max(0,capacity-total) if total is not None and capacity is not None else None,
        'status':('Over Capacity' if total>capacity else 'Full' if total==capacity else 'Available') if total is not None and capacity is not None else 'Not confirmed',
        'proficiency':division,'proficiency_memberships':[list(p) for p in sorted(pairs)] if not unrestricted else [],
        'issues':issues,'completeness':'Incomplete' if issues else 'Complete',
        'note':'Name/mobile trial matching is provisional; enrollment overlap unresolved.' if contacts or missing_contacts else
               'Trial source not supplied.' if trials is None else 'Shared student IDs used; unresolved records still prevent approval.'}


def slot_snapshot(payload,enrollment_path,trial_path,capacity_path,mapping_path=None):
    reference=date.fromisoformat(payload.get('reference_date') or today().isoformat())
    if 'csv_text' in payload and Path(payload.get('filename','enrollment.csv')).suffix.lower()!='.csv':
        raise ValueError('Enrollment source must be a CSV export')
    rows,ehash=read_source(enrollment_path,(*ENROLLMENT_FIELDS,'Slots'),payload.get('csv_text'))
    uploaded='capacity_xlsx' in payload or 'capacity_text' in payload
    capacity_name=payload.get('capacity_filename',Path(capacity_path).name)
    if 'capacity_xlsx' in payload:
        records,chash=read_main(Path(capacity_name),base64.b64decode(payload['capacity_xlsx'],validate=True))
    elif 'capacity_text' in payload:
        records,chash=read_capacity_csv(payload['capacity_text'].encode('utf-8'))
    elif Path(capacity_path).suffix.lower()=='.csv':records,chash=read_capacity_csv(Path(capacity_path).read_bytes())
    else:records,chash=read_main(capacity_path)
    from capacity_overrides import resolve_centers
    records,resolved_rows=resolve_centers(records,chash,MAPPED_DIR/'capacity_center_overrides.json')
    listed=schedule(records,reference)
    excluded=[{**b,'exclusion_reason':'Missing center name — excluded by business rule'} for b in listed
        if not b.get('center') or not b['center'].strip()]
    from batch_mappings import read_store,club_key
    closed_keys=read_store(mapping_path).get('excluded_clubs',{})
    closed=[{**b,'exclusion_reason':'User-confirmed closed center'} for b in listed
        if club_key(b) in closed_keys]
    batches=[b for b in listed if b.get('center') and b['center'].strip()
        and club_key(b) not in closed_keys]
    weekly=None
    if payload.get('include_weekly') is True:
        monday=reference-timedelta(days=reference.weekday())
        centers=sorted({(r['center'],r.get('city') or '') for r in records
            if r.get('center') and r['center'].strip() and club_key(r) not in closed_keys})
        days=[]
        for offset in range(7):
            selected=monday+timedelta(days=offset)
            daily=[b for b in schedule(records,selected) if b.get('center') and b['center'].strip()
                and club_key(b) not in closed_keys]
            daily.sort(key=lambda b:(b['start'] is None,b['start'] or 0,b['end'] or 0,b['sport'] or '',b['division'] or '',b['source_row']))
            days.append({'date':selected.isoformat(),'weekday':WEEKDAYS[selected.weekday()], 'batches':daily})
        weekly={'week_start':monday.isoformat(),'week_end':(monday+timedelta(days=6)).isoformat(),
            'centers':[{'center':name,'city':city,'sports':sorted({r['sport'] for r in records
                if r.get('center')==name and (r.get('city') or '')==city and r.get('sport')
                and club_key(r) not in closed_keys})} for name,city in centers],'days':days}
    trials=None;thash=None
    trial_uploaded='trials_xlsx' in payload or 'trials_text' in payload
    if trial_uploaded or trial_path and Path(trial_path).is_file():
        from raw_trial_source import read_trial_xlsx,read_raw_trial_csv
        trial_name=payload.get('trials_filename',Path(trial_path).name if trial_path else 'uploaded_trials.csv')
        if 'trials_xlsx' in payload:
            trials,thash=read_trial_xlsx(Path(trial_name),base64.b64decode(payload['trials_xlsx'],validate=True))
        elif 'trials_text' in payload:
            if Path(trial_name).suffix.lower()!='.csv':raise ValueError('Trial text input must be a CSV export')
            trials,thash=read_raw_trial_csv(Path(trial_name),payload['trials_text'])
        else:
            trials,thash=(read_trial_xlsx(Path(trial_path)) if Path(trial_path).suffix.lower()=='.xlsx' else read_raw_trial_csv(Path(trial_path)))
    result=None
    options=targets(rows,trials)
    from batch_mappings import attach_mappings,save_mapping
    mapping_summary=attach_mappings(batches,options,mapping_path,capacity_name,chash)
    pending_save=None
    if payload.get('batch_id'):
        batch=next((b for b in batches if b['id']==payload['batch_id']),None)
        if batch and payload.get('use_saved_mapping') is True:
            saved=batch['approved_mapping']
            if saved is None:raise ValueError('This batch has no current approved mapping; review and save it first')
            payload={**payload,'target_id':saved['target_id'],'age':saved['age'],
                'target_identity':saved['target'],'proficiency_pairs':saved['proficiency_pairs'],'confirmed':True}
        from batch_mappings import target_identity
        target=next((t for t in options if target_identity(t)==payload['target_identity']),None) if 'target_identity' in payload else next((t for t in options if t['id']==payload.get('target_id')),None)
        if batch is None or target is None:raise ValueError('Choose an existing workbook slot and enrollment group')
        if payload.get('workbook_hash')!=chash:raise ValueError('Workbook changed; reload and confirm the link again')
        if payload.get('confirmed') is not True:raise ValueError('Confirm the source link and capacity scope before calculating')
        age=payload.get('age') or None
        if age and age not in target['ages']:raise ValueError('Choose an existing exact age label')
        pairs=payload.get('proficiency_pairs')
        if pairs is not None:
            allowed={(m['age'],m['course']) for m in target['proficiency_memberships']}
            if not isinstance(pairs,list) or any(not isinstance(p,list) or len(p)!=2 or not all(isinstance(v,str) for v in p) or tuple(p) not in allowed for p in pairs):
                raise ValueError('Choose existing exact age/course combinations for this enrollment group')
            if age and any(p[0]!=age for p in pairs):raise ValueError('Proficiency combinations conflict with selected age scope')
        if batch['division'] not in ('Open','Open Age') and not pairs:raise ValueError('Select exact proficiency age/course combinations before approving this batch')
        if payload.get('mapping_action')=='save':
            pending_save=(batch,target,age,pairs or [])
        else:
            # An explicitly approved row-level link can resolve a blank center in memory.
            calculation_batch={**batch,'issues':[s for s in batch['issues'] if not (
                s=='Missing Sport or Centre' and not batch['center'] and batch['sport'])]}
            if calculation_batch['issues']:raise ValueError('This workbook row needs review: '+'; '.join(calculation_batch['issues']))
            result=evaluate(calculation_batch,target,age,rows,trials,reference,pairs)
    for path,digest in ((capacity_path,None if uploaded else chash),(trial_path,None if trial_uploaded else thash),(enrollment_path,None if 'csv_text' in payload else ehash)):
        if digest and hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Source changed during calculation; reload')
    if pending_save:
        save_mapping(mapping_path,*pending_save,capacity_name,chash)
        mapping_summary=attach_mappings(batches,options,mapping_path,capacity_name,chash)
    # Approved enrollment labels are display metadata; original center keys stay intact.
    display_store=read_store(mapping_path)
    def full_names(source_rows):
        names=set()
        for source_row in source_rows:
            link=display_store.get('clubs',{}).get(club_key(source_row))
            if link and any(all(t.get(k)==v for k,v in link['target'].items()) for t in options):
                names.add(link['target']['center'])
        return sorted(names)
    for batch in batches+([b for day in weekly['days'] for b in day['batches']] if weekly else []):
        names=full_names([batch])
        if names:batch['full_center_names']=names
    if weekly:
        for center in weekly['centers']:
            names=full_names([r for r in records if r.get('center')==center['center'] and (r.get('city') or '')==center['city']])
            if names:center['full_center_names']=names
    from trial_booking_preview import attach_booking_previews, sport_booking_rules, sport_inventory_summary
    from upload_validation import validate_uploads
    validation=validate_uploads(rows,trials,batches,excluded+closed)
    attach_booking_previews(batches, reference.isoformat())
    if weekly:
        for day in weekly['days']:
            attach_booking_previews(day['batches'], day['date'])
    return {'validation':validation,'sport_inventory_summary':sport_inventory_summary(batches), 'sport_booking_rules':sport_booking_rules(), 'batches':batches,'weekly':weekly,'targets':options,'result':result,'reference_date':reference.isoformat(),
        'weekday':WEEKDAYS[reference.weekday()],'capacity_source':capacity_name,'capacity_uploaded_snapshot':uploaded,
        'capacity_sheet':'CSV' if Path(capacity_name).suffix.lower()=='.csv' else 'MAIN',
        'enrollment_source':payload.get('filename',Path(enrollment_path).name),
        'trial_source':trial_name if trials is not None else None,
        'enrollment_uploaded_snapshot':'csv_text' in payload,'trial_uploaded_snapshot':trial_uploaded,
        'mapping_summary':mapping_summary,'mapping_saved':pending_save is not None,
        'listed_source_rows':len(listed),'excluded_missing_center_count':len(excluded),'excluded_rows':excluded,
        'excluded_closed_center_count':len(closed),'excluded_closed_rows':closed,
        'center_reference_rows':resolved_rows,
        'workbook_hash':chash,'enrollment_hash':ehash,'trial_hash':thash}
