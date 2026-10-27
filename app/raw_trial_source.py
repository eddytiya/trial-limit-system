"""Read-only trials; exact name/mobile matching is a provisional, user-approved fallback."""
import hashlib
import io
import csv
import zipfile
from datetime import date,datetime
from xml.etree import ElementTree as ET
from collections import Counter
from automatic_capacity import BATCH_FIELDS
from trial_limit import eligible,RULE

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
RAW_FIELDS=('Academy','Coaching Center','Age Category','Trial Scheduled Date','Status')


def read_raw_trial_csv(path,text=None):
    raw=path.read_bytes() if text is None else text.encode('utf-8')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''))
    headers=reader.fieldnames or []
    if len(headers)!=len(set(headers)):raise ValueError('Duplicate trial CSV header labels')
    missing=set(RAW_FIELDS)-set(headers)
    if missing:raise ValueError('Missing raw trial CSV columns: '+', '.join(sorted(missing)))
    rows=[]
    while True:
        line=reader.line_num+1
        try:row=next(reader)
        except StopIteration:break
        if any(row.values()):rows.append((line,row))
    return rows,hashlib.sha256(raw).hexdigest()


def read_trial_xlsx(path,raw=None):
    raw=path.read_bytes() if raw is None else raw
    digest=hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        shared=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared=[''.join(t.text or '' for t in si.iter('{'+NS['m']+'}t'))
                    for si in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        workbook=ET.fromstring(archive.read('xl/workbook.xml'))
        sheet=next((s for s in workbook.find('m:sheets',NS) if s.get('name')=='Query result'),None)
        if sheet is None:
            raise ValueError('Raw trial workbook requires the Query result sheet')
        relations=ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        member=next(r.get('Target') for r in relations if r.get('Id')==sheet.get('{'+REL+'}id'))
        member=member.lstrip('/') if member.startswith('/') else 'xl/'+member
        records=[];headers={}
        for element in ET.fromstring(archive.read(member)).find('m:sheetData',NS):
            number=int(element.get('r'));cells={}
            for cell in element:
                value=cell.find('m:v',NS);value=value.text if value is not None else ''
                kind=cell.get('t')
                if kind=='s' and value:value=shared[int(value)]
                elif kind=='inlineStr':value=''.join(t.text or '' for t in cell.iter('{'+NS['m']+'}t'))
                column=''.join(c for c in cell.get('r') if c.isalpha())
                cells[column]=value
            if not headers and any(cells.values()):
                headers=cells
                if len(set(headers.values()))!=len(headers):
                    raise ValueError('Duplicate trial workbook header labels')
                missing=set(RAW_FIELDS)-set(headers.values())
                if missing:raise ValueError('Missing trial workbook columns: '+', '.join(sorted(missing)))
            elif any(cells.values()):
                records.append((number,{label:cells.get(col,'') for col,label in headers.items()}))
    return records,digest


def source_date(raw):
    if not raw:raise ValueError('Missing Trial Scheduled Date')
    try:return date.fromisoformat(raw)
    except ValueError:raise ValueError('Invalid Trial Scheduled Date') from None


def _combine_unidentified_raw_trials(batches,enrollments,raw_trials,reference,capacity,rule='pending',source_kind='Raw trial workbook'):
    """Booked rows are a preview, not unique additional students without shared IDs."""
    identities={};center_identities={}
    for _,row in enrollments:
        name=row.get('Academy Name');pair=(row.get('Academy ID'),row.get('Sports'))
        if name and all(pair):
            identities.setdefault(name,set()).add(pair)
            center_identities.setdefault((name,row.get('Coaching Center Location')),set()).add(pair)
    groups={tuple(b[k] for k in BATCH_FIELDS):b for b in batches}
    issues=[];pending=[];statuses=Counter();booked_rows=0
    matched_booked=0;seen_contacts={};duplicates=0
    def empty(key,name):
        return {**dict(zip(BATCH_FIELDS,key)),'Academy Name':[name], 'Reference date':reference.isoformat(),
            'Scope':'Center sport age batch; slots ignored','Courses combined':[],
            'Unique enrolled students':0,'Known occupancy':0,'Capacity':capacity,'Enrollment status':'Below limit',
            'Data completeness':'Complete','Unresolved records':0,'Eligibility rule':'dates_inclusive'}
    for line,row in raw_trials:
        reasons=[];possible=False
        try:possible=source_date(row.get('Trial Scheduled Date'))==reference
        except ValueError as exc:
            possible=True;reasons.append(str(exc))
        moved=row.get('Rescheduled Date & Time') or ''
        if moved:
            try:
                if datetime.fromisoformat(moved).date()==reference:
                    possible=True;reasons.append('Rescheduled to selected date; rescheduling rule needs confirmation')
            except ValueError:
                possible=True;reasons.append('Invalid rescheduled date; effective trial date unresolved')
        if not possible:
            continue
        status=row.get('Status','')
        if row.get('Trial Scheduled Date')==reference.isoformat():
            statuses[status]+=1
        booked=status=='booked' and row.get('Trial Scheduled Date')==reference.isoformat()
        if booked:booked_rows+=1
        name=row.get('Academy','');center=row.get('Coaching Center','');age=row.get('Age Category','')
        choices=center_identities.get((name,center)) or identities.get(name,set())
        identity=next(iter(choices)) if len(choices)==1 else (None,None)
        key=(identity[0],center or None,identity[1],age or None)
        if len(choices)!=1:reasons.append('Academy name cannot be matched to one exact Academy ID and Sports value')
        if not center or not center.strip():reasons.append('Missing Coaching Center')
        if not age or not age.strip():reasons.append('Missing Age Category')
        reasons.append('No shared Player DB ID or Trial Booking ID; unique students and enrollment overlap cannot be established')
        if rule!='booked_only':reasons.append('Trial status eligibility rule awaiting confirmation')
        elif status!='booked':reasons.append('Non-booked trial status requires review: '+(status or '(blank)'))
        if all(k is not None and k.strip() for k in key):
            group=groups.setdefault(key,empty(key,name))
            group.setdefault('Trial source status counts',{})[status]=group.get('Trial source status counts',{}).get(status,0)+1
            group['Trial source row count']=group.get('Trial source row count',0)+1
            if booked:
                group['Booked trial rows']=group.get('Booked trial rows',0)+1
                matched_booked+=1
                player=row.get('Player Name','');mobile=row.get('Mobile number','')
                contact=(key,row.get('Trial Scheduled Date'),player,mobile)
                if player.strip() and mobile.strip() and contact in seen_contacts:
                    duplicates+=1
                    group['Duplicate trial rows excluded']=group.get('Duplicate trial rows excluded',0)+1
                    reasons.append('Exact name + mobile duplicate of source row '+str(seen_contacts[contact])+'; excluded from provisional trial count')
                else:
                    group['Provisional trial students']=group.get('Provisional trial students',0)+1
                    if player.strip() and mobile.strip():seen_contacts[contact]=line
                    else:reasons.append('Missing name or mobile; retained separately without provisional identity matching')
        pending.append(key)
        issues.append({'Source':source_kind,'Source sheet':'Query result' if source_kind=='Raw trial workbook' else None,'Source row number':line,
                       'Record ID':None,'Academy Name':name,'Coaching Center Location':center,'Age Category':age,
                       'Trial Scheduled Date':row.get('Trial Scheduled Date'),'Status':status,
                       'Reason':'; '.join(reasons),'Could affect counts':True})
    for key,b in groups.items():
        affected=sum(all(v is None or not v.strip() or v==actual for v,actual in zip(other,key)) for other in pending)
        b['Trial students']=None;b['Trial students already enrolled']=None
        b['Trial data']='Raw workbook — identities unavailable'
        b['Trial source row count']=b.get('Trial source row count',0)
        b['Booked trial rows']=b.get('Booked trial rows',0)
        b['Duplicate trial rows excluded']=b.get('Duplicate trial rows excluded',0)
        b['Provisional trial students']=b.get('Provisional trial students',0)
        b['Enrolled plus booked rows preview']=b['Unique enrolled students']+b['Provisional trial students']
        b['Preview excess']=max(0,b['Enrolled plus booked rows preview']-capacity)
        b['Trial source status counts']=b.get('Trial source status counts',{})
        b['Total occupancy']=None;b['Remaining places']=None
        b['Trial status rule']='booked_only' if rule=='booked_only' else 'Awaiting confirmation'
        b['Capacity status']='Over Capacity — known count' if b['Known occupancy']>capacity else 'Not confirmed'
        b['Known excess students']=max(0,b['Known occupancy']-capacity)
        b['Booking assessment']='Approval withheld'
        b['Unresolved records']+=affected
        b['Data completeness']='Incomplete' if b['Unresolved records'] else 'Complete'
    return list(groups.values()),issues,{'selected_date_statuses':dict(statuses),
        'booked_rows_on_date':booked_rows,'matched_booked_rows':matched_booked,
        'duplicate_trial_rows_excluded':duplicates,'matched_trial_rows_after_dedup':matched_booked-duplicates,
        'provisional_identity_rule':'Exact Player Name + Mobile number within date and capacity group; missing identities retained separately',
        'unique_trial_students_confirmed':False,'identity_header_present':False,'status_rule':rule}


def combine_raw_trials(batches,enrollments,raw_trials,reference,capacity,rule='pending',source_kind='Raw trial workbook'):
    """Use shared IDs when supplied; never infer them from names or phone numbers."""
    if not any('Player DB ID' in row for _,row in raw_trials):
        return _combine_unidentified_raw_trials(batches,enrollments,raw_trials,reference,capacity,rule,source_kind)
    identities={};centers={};enrolled_ids={}
    for _,row in enrollments:
        pair=(row.get('Academy ID'),row.get('Sports'));name=row.get('Academy Name')
        if name and all(pair):
            identities.setdefault(name,set()).add(pair)
            centers.setdefault((name,row.get('Coaching Center Location')),set()).add(pair)
        key=tuple(row.get(k) for k in BATCH_FIELDS)
        if not all(v and v.strip() for v in (*key,row.get('Player DB ID'))):continue
        try:valid=eligible(row,reference,RULE)
        except ValueError:continue
        if valid and None not in row:enrolled_ids.setdefault(key,set()).add(row['Player DB ID'])
    groups={tuple(b[k] for k in BATCH_FIELDS):b for b in batches}
    trial_ids={};pending=[];issues=[];statuses=Counter();booked_count=matched=0
    versions={}
    for _,row in raw_trials:
        booking=row.get('Trial Booking ID')
        if booking and booking.strip():
            values=tuple(row.get(k) for k in (*RAW_FIELDS,'Player DB ID','Rescheduled Date & Time'))
            versions.setdefault(booking,set()).add(values)
    conflicts={key for key,values in versions.items() if len(values)>1}
    for line,row in raw_trials:
        reasons=[]
        try:possible=source_date(row.get('Trial Scheduled Date'))==reference
        except ValueError as exc:possible=True;reasons.append(str(exc))
        moved=row.get('Rescheduled Date & Time')
        if moved:
            try:
                if datetime.fromisoformat(moved).date()==reference:
                    possible=True;reasons.append('Rescheduled to selected date; rescheduling rule needs confirmation')
                elif possible:
                    reasons.append('Trial has a rescheduled date; effective booking date requires review')
            except ValueError:possible=True;reasons.append('Invalid rescheduled date')
        if not possible:continue
        status=row.get('Status','')
        on_date=row.get('Trial Scheduled Date')==reference.isoformat()
        if on_date:statuses[status]+=1
        booked=status=='booked' and on_date
        if booked:booked_count+=1
        if rule!='booked_only':reasons.append('Trial status eligibility rule awaiting confirmation')
        elif status!='booked':reasons.append('Non-booked trial status requires review: '+(status or '(blank)'))
        if row.get('Trial Booking ID') in conflicts:reasons.append('Conflicting Trial Booking ID records')
        name=row.get('Academy','');center=row.get('Coaching Center','');age=row.get('Age Category','')
        choices=centers.get((name,center)) or identities.get(name,set())
        pair=next(iter(choices)) if len(choices)==1 else (None,None)
        key=(pair[0],center or None,pair[1],age or None)
        if len(choices)!=1:reasons.append('Academy name cannot be matched to one exact Academy ID and Sports value')
        if not center or not center.strip():reasons.append('Missing Coaching Center')
        if not age or not age.strip():reasons.append('Missing Age Category')
        student=row.get('Player DB ID')
        if not student or not student.strip():reasons.append('Missing shared Player DB ID; student identity unresolved')
        if None in row:reasons.append('Malformed trial record')
        if all(v is not None and v.strip() for v in key):
            b=groups.setdefault(key,{**dict(zip(BATCH_FIELDS,key)),'Academy Name':[name],
                'Reference date':reference.isoformat(),'Scope':'Center sport age batch; slots ignored',
                'Courses combined':[],'Unique enrolled students':0,'Known occupancy':0,'Capacity':capacity,
                'Enrollment status':'Below limit','Data completeness':'Complete','Unresolved records':0,
                'Eligibility rule':RULE})
            b['Trial source row count']=b.get('Trial source row count',0)+1
            b.setdefault('Trial source status counts',{})[status]=b.get('Trial source status counts',{}).get(status,0)+1
            if booked:b['Booked trial rows']=b.get('Booked trial rows',0)+1;matched+=1
            if booked and not reasons:trial_ids.setdefault(key,set()).add(student)
        if reasons:
            pending.append(key)
            issues.append({'Source':source_kind,'Source sheet':'Query result' if source_kind=='Raw trial workbook' else None,
                'Source row number':line,'Record ID':row.get('Trial Booking ID'),'Player DB ID':student,
                'Academy Name':name,'Coaching Center Location':center,'Age Category':age,
                'Trial Scheduled Date':row.get('Trial Scheduled Date'),'Status':status,
                'Reason':'; '.join(reasons),'Could affect counts':True})
    overlap_total=unique_total=additional_total=0
    for key,b in groups.items():
        affected=sum(all(v is None or not v.strip() or v==actual for v,actual in zip(other,key)) for other in pending)
        enrolled=enrolled_ids.get(key,set());ids=trial_ids.get(key,set())
        overlap=len(ids&enrolled);additional=len(ids-enrolled)
        unique_total+=len(ids);additional_total+=additional;overlap_total+=overlap
        b['Known occupancy']=b['Unique enrolled students']+additional
        b['Known additional trial students']=additional
        b['Trial students']=additional if not affected else None
        b['Trial students already enrolled']=overlap
        b['Unique booked trial students identified']=len(ids)
        b['Trial source row count']=b.get('Trial source row count',0)
        b['Booked trial rows']=b.get('Booked trial rows',0)
        b['Enrolled plus booked rows preview']=b['Unique enrolled students']+b['Booked trial rows']
        b['Preview excess']=max(0,b['Enrolled plus booked rows preview']-capacity)
        b['Unresolved records']+=affected
        b['Data completeness']='Incomplete' if b['Unresolved records'] else 'Complete'
        complete=b['Data completeness']=='Complete'
        b['Total occupancy']=b['Known occupancy'] if complete else None
        b['Remaining places']=max(0,capacity-b['Known occupancy']) if complete else None
        b['Trial data']='Supplied' if not affected else 'Raw source — unresolved identities or eligibility'
        b['Trial status rule']=rule
        b['Known excess students']=max(0,b['Known occupancy']-capacity)
        b['Capacity status']=('Over Capacity' if b['Known occupancy']>capacity else 'Full' if b['Known occupancy']==capacity else 'Available') if complete else (
            'Over Capacity — known count' if b['Known occupancy']>capacity else 'Not confirmed')
        b['Booking assessment']='Ready for capacity check' if complete else 'Approval withheld'
    return list(groups.values()),issues,{'selected_date_statuses':dict(statuses),'booked_rows_on_date':booked_count,
        'matched_booked_rows':matched,'unique_trial_students_confirmed':not pending,'identity_header_present':True,
        'unique_trial_group_memberships_identified':unique_total,'overlap_group_memberships_removed':overlap_total,
        'additional_trial_group_memberships_identified':additional_total,'status_rule':rule}
