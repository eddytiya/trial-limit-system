"""Independent read-only source audit; counting does not call application parsers."""
import csv
import hashlib
import html
import io
import json
import re
import zipfile
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'outputs'/'validation_2026-10-21'
CAP=Path(r'C:\Users\biswajit.das\Downloads\Greenfield Batch & Coach details (1).xlsx')
ENR=ROOT/'academy___enrollment_data___formatted_report_2026-10-15T15_16_51.527944248+05_30.csv'
TRIAL=ROOT/'academy___trial_booking___raw_data_2026-10-19T13_17_51.456488991+05_30.xlsx'
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
DAYS=('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')


def workbook(path,sheet):
    with zipfile.ZipFile(path) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(t.text or '' for t in si.iter('{'+NS['m']+'}t')) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        meta=ET.fromstring(z.read('xl/workbook.xml'))
        entry=next(s for s in meta.find('m:sheets',NS) if s.get('name')==sheet)
        rid=entry.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        target=next(r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')) if r.get('Id')==rid)
        member=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        tree=ET.fromstring(z.read(member));cells={};rows=[]
        for r in tree.find('m:sheetData',NS):
            number=int(r.get('r'));row={}
            for cell in r:
                v=cell.find('m:v',NS);value=v.text if v is not None else ''
                if cell.get('t')=='s' and value:value=strings[int(value)]
                if cell.get('t')=='inlineStr':value=''.join(t.text or '' for t in cell.iter('{'+NS['m']+'}t'))
                column=re.match('[A-Z]+',cell.get('r'))[0]
                row[column]=value;cells[cell.get('r')]=value
            rows.append((number,row))
        merges=tree.find('m:mergeCells',NS)
        return rows,cells,[m.get('ref') for m in merges] if merges is not None else []


def clock(value):
    return datetime.strptime(value,'%I:%M %p').hour*60+datetime.strptime(value,'%I:%M %p').minute


def slot_times(value,day):
    if not value or not value.strip():raise ValueError('Missing Slots')
    times=[]
    for part in value.split(', '):
        m=re.fullmatch(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) (\d{1,2}:\d{2} [AP]M) - (\d{1,2}:\d{2} [AP]M)',part)
        if not m:raise ValueError('Invalid Slots')
        d,s,e=m.groups();start,end=clock(s),clock(e)
        if end<=start:raise ValueError('Invalid Slots interval')
        if d==day:times.append((start,end))
    return times


def independent(case,reference,enrollments,trials):
    ids=set();booked=[];unknown=[];enrollment_rows=[];duplicates=[];seen={}
    def issue(source,line,reason):unknown.append({'case':case['name'],'date':str(reference),'source':source,'row':line,'reason':reason})
    def membership(row,field,line,source):
        pairs=case['pairs']
        if pairs is None:return True
        a,c=row.get('Age Category'),row.get(field)
        if not a or not c:
            if any((not a or a==pa) and (not c or c==pc) for pa,pc in pairs):issue(source,line,'Missing age/course; possible proficiency membership')
            return False
        return (a,c) in pairs
    for line,row in enrollments:
        if any(row.get(k) and row[k]!=v for k,v in [('Academy ID',case['academy_id']),('Coaching Center Location',case['center']),('Sports',case['sport'])]):continue
        try:
            start=date.fromisoformat(row.get('Start Date') or '');end=date.fromisoformat(row.get('End Date') or '')
            if end<start:raise ValueError()
        except ValueError:issue('Enrollment',line,'Missing/invalid/reversed enrollment dates');continue
        if not start<=reference<=end:continue
        try:times=slot_times(row.get('Slots'),DAYS[reference.weekday()])
        except ValueError as exc:issue('Enrollment',line,str(exc));continue
        if case['times'] not in times:continue
        if not membership(row,'Course Name',line,'Enrollment'):continue
        if any(not row.get(k) or not row[k].strip() for k in ('Academy ID','Coaching Center Location','Sports','Player DB ID')):
            issue('Enrollment',line,'Missing ID/group field');continue
        ids.add(row['Player DB ID']);enrollment_rows.append(line)
    for line,row in trials:
        if row.get('Academy') and row['Academy']!=case['academy'] or row.get('Coaching Center') and row['Coaching Center']!=case['center']:continue
        try:scheduled=date.fromisoformat(row.get('Trial Scheduled Date') or '')
        except ValueError:issue('Trials',line,'Missing/invalid scheduled date');continue
        moved=row.get('Rescheduled Date & Time')
        if moved:
            try:relevant=datetime.fromisoformat(moved).date()==reference or scheduled==reference
            except ValueError:relevant=True
            if relevant:issue('Trials',line,'Reschedule needs review');continue
        if scheduled!=reference:continue
        try:times=(clock(row.get('Start Time') or ''),clock(row.get('End Time') or ''))
        except ValueError:issue('Trials',line,'Missing/invalid time');continue
        if times!=case['times']:continue
        if not membership(row,'Course Details',line,'Trials'):continue
        if not row.get('Academy') or not row.get('Coaching Center'):issue('Trials',line,'Missing trial group');continue
        if row.get('Status')!='booked':issue('Trials',line,'Non-booked status needs review');continue
        booked.append(line)
        contact=(row.get('Player Name'),row.get('Mobile number'))
        if all(v and v.strip() for v in contact):
            if contact in seen:duplicates.append({'source_row':line,'first_row':seen[contact]})
            else:seen[contact]=line
        else:seen[('missing',line)]=line;issue('Trials',line,'Missing trial name/mobile')
    return {'enrolled':len(ids),'booked_rows':len(booked),'duplicates_excluded':len(duplicates),
        'additional_trials':len(booked)-len(duplicates),'preview':len(ids)+len(booked)-len(duplicates),
        'enrollment_rows':enrollment_rows,'trial_rows':booked,'issues':unknown}


def export_csv(name,rows,fields=None):
    fields=fields or list(rows[0]) if rows else fields or ['Result']
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (CAP,ENR,TRIAL)}
    with ENR.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);enrollments=[]
        while True:
            line=reader.line_num+1
            try:row=next(reader)
            except StopIteration:break
            enrollments.append((line,row))
    tr,tc,_=workbook(TRIAL,'Query result');headers=tr[0][1]
    trials=[(n,{h:r.get(c,'') for c,h in headers.items()}) for n,r in tr[1:] if any(r.values())]
    cr,cells,merges=workbook(CAP,'MAIN')
    # Application code is invoked only for comparison after independent source extraction/counting.
    from slot_thresholds import slot_snapshot
    cases=[{'name':'Open pool','row':3,'center':'Rolex Metal Industries Compound, Bhandup','sport':'TableTennis',
        'academy':'SFL Table Tennis Academy','academy_id':'6818b03fe167f7292b3407e4','times':(960,1020),'pairs':None,
        'mapping':'Candidate center/sport link: Rolex Metal Industries / Table Tennis → Rolex Metal Industries Compound, Bhandup / TableTennis. Confirm with center owner.'},
        {'name':'Intermediate pool','row':78,'center':'The Acres Club, Chembur','sport':'Tennis',
        'academy':'SFL Racquet Arena','academy_id':'67b584591b4d3ac03fb15230','times':(360,420),'pairs':[('Open Age','Intermediate')],
        'mapping':'Candidate center link: Acres Racquet Arena → The Acres Club, Chembur. Exact selected membership Open Age + Intermediate; confirm with center owner.'},
        {'name':'Combined Beginner/Intermediate pool','row':72,'center':'ProPlayX - Lush, Mira Road ','sport':'Badminton',
        'academy':'SFL Badminton Academy','academy_id':'68e651e21919ab1d9ce04e8e','times':(960,1020),'pairs':[('Open Age','Beginner'),('Open Age','Intermediate')],
        'mapping':'Candidate center link: Lush, Mira Road → ProPlayX - Lush, Mira Road [source has trailing space]. Selected Beginner + Intermediate in one pool; confirm with center owner.'}]
    cases.append({**cases[0],'name':'Open pool with booked trials (7-8 PM)','row':6,'times':(1140,1200)})
    cases.append({**cases[2],'name':'Combined pool with missing trial course (6-7 PM)','row':74,'times':(1080,1140)})
    results=[];issues=[];evidence=[];differences=[]
    for reference in (date(2026,10,19),date(2026,10,21)):
        snapshot=slot_snapshot({'reference_date':str(reference)},ENR,TRIAL,CAP)
        for case in cases:
            expected=independent(case,reference,enrollments,trials)
            target=next(t for t in snapshot['targets'] if t['academy_id']==case['academy_id'] and t['center']==case['center'] and t['sport']==case['sport'])
            batch=next(b for b in snapshot['batches'] if b['source_row']==case['row'])
            if batch['issues']:
                results.append({'Case':case['name'],'Date':str(reference),'Check':'Blocked by schedule issues','Mapping':case['mapping']});continue
            payload={'reference_date':str(reference),'batch_id':str(case['row']),'target_id':target['id'],'confirmed':True,
                'age':'','workbook_hash':snapshot['workbook_hash'],'proficiency_pairs':[list(p) for p in case['pairs'] or []]}
            actual=slot_snapshot(payload,ENR,TRIAL,CAP)['result']
            match=all(actual[k]==expected[k] for k in ('enrolled','booked_rows','duplicates_excluded','additional_trials','preview'))
            if not match:differences.append({'case':case['name'],'date':str(reference),'independent':expected,'app':actual})
            cap_col=('M','P','S','V','Y','AB','AE')[reference.weekday()]
            raw_cap=cells.get(f'{cap_col}{case["row"]}')
            assert batch['capacity']==int(raw_cap)
            results.append({'Case':case['name'],'Date':str(reference),'Workbook row':case['row'],
                'Workbook center':batch['center'],'Enrollment center':case['center'],'Sport':case['sport'],
                'Proficiency':batch['division'],'Time':batch['time'],'Threshold':int(raw_cap),
                'Independent enrolled':expected['enrolled'],'App enrolled':actual['enrolled'],
                'Independent booked rows':expected['booked_rows'],'App booked rows':actual['booked_rows'],
                'Repeated trials excluded':expected['duplicates_excluded'],'Independent preview':expected['preview'],
                'App preview':actual['preview'],'Unresolved source rows':len(expected['issues']),
                'Check':'PASS — counts agree for stated mapping' if match else 'FAIL',
                'Confirmed total':actual['confirmed_total'],'Mapping':case['mapping']})
            issues.extend(expected['issues'])
            for source,lines in [('Enrollment',expected['enrollment_rows']),('Trials',expected['trial_rows'])]:
                evidence.extend({'Case':case['name'],'Date':str(reference),'Source':source,'Source row':line} for line in lines)
    quality=[]
    for source,rows,fields in [('Enrollment',enrollments,['Player DB ID','Academy ID','Coaching Center Location','Sports','Age Category','Course Name','Slots','Start Date','End Date']),
        ('Trials',trials,['Academy','Coaching Center','Age Category','Course Details','Trial Scheduled Date','Player Name','Mobile number'])]:
        for field in fields:quality.append({'Source':source,'Check':'Blank/whitespace-only '+field,'Rows':sum(not r.get(field) or not r[field].strip() for _,r in rows)})
    quality.append({'Source':'Trials','Check':'No shared Player DB ID column','Rows':len(trials) if 'Player DB ID' not in headers.values() else 0})
    for ref in (date(2026,10,19),date(2026,10,21)):
        quality.append({'Source':'Trials','Check':'Booked rows scheduled '+str(ref),'Rows':sum(r.get('Status')=='booked' and r.get('Trial Scheduled Date')==str(ref) for _,r in trials)})
    export_csv('sample_comparison.csv',results)
    export_csv('source_quality_counts.csv',quality)
    export_csv('sample_unresolved_rows.csv',issues,['case','date','source','row','reason'])
    export_csv('counted_source_rows.csv',evidence,['Case','Date','Source','Source row'])
    unchanged=hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (CAP,ENR,TRIAL)}
    audit={'enrollment_rows':len(enrollments),'trial_rows':len(trials),'sources_unchanged':unchanged,'hashes':hashes,
        'sample_checks':len(results),'comparison_failures':differences,'results':results,'quality':quality}
    (OUT/'audit.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
    def table(rows,fields):
        return '<table><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in fields)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(r.get(k,'')))+'</td>' for k in fields)+'</tr>' for r in rows)+'</table>'
    body='''<!doctype html><html><head><meta charset="utf-8"><title>Three-source validation</title><style>body{font:14px/1.6 Segoe UI,Arial;max-width:1150px;margin:30px auto;padding:0 20px;color:#20343c}h1,h2{color:#12535c}table{border-collapse:collapse;width:100%;margin:15px 0}td,th{border:1px solid #cadadd;padding:8px;text-align:left}th{background:#eaf3f4}.note{background:#fff2dc;padding:15px}code{overflow-wrap:anywhere}</style></head><body><h1>Trial Limit — Three-source validation</h1><p>Checked 21 October 2026. Reference dates tested: 19 and 21 October 2026. All three user-specified sources were read-only.</p>'''
    body+=f'<p><strong>Result: {len(results)-len(differences)}/{len(results)} sample counting comparisons agree. Source hashes unchanged: {unchanged}.</strong></p>'
    body+='<p class="note">This validates counting for the stated candidate mappings, not business approval of those mappings. All samples must still have their workbook center aliases and proficiency membership confirmed by a center owner. Shared student IDs are absent in the trial source, so enrollment–trial overlap cannot be independently established. Old snapshots do not establish current live occupancy.</p>'
    body+='<h2>Sample calculations</h2>'+table(results,['Case','Date','Threshold','Independent enrolled','App enrolled','Independent booked rows','App booked rows','Independent preview','App preview','Unresolved source rows','Check'])
    body+='<h2>Mappings tested — confirmation still required</h2>'+''.join('<p><strong>'+html.escape(c['name'])+':</strong> '+html.escape(c['mapping'])+'</p>' for c in cases)
    body+='<h2>Data limitations found</h2><ul><li>Capacity workbook names and sports differ from enrollment labels. Exact automatic joining cannot establish all aliases.</li><li>Kids/Child Beginner cannot be established from an Open Age + Beginner label alone. Do not treat all Open Age beginners as children without a verified age mapping.</li><li>Blank center cells that are not actual merged cells remain missing; no forward-fill or source repair is performed.</li><li>Enrollment export is dated 15 October; trial export is dated 19 October. Trial records scheduled for later dates can exist, but bookings or changes made after export are not captured.</li><li>Workbook Actual Capacity is an undated reference headcount. A different CSV-derived count is not itself a calculation error.</li></ul>'
    body+='<h2>Source-quality counts</h2><p>Counts overlap; do not add them together as unique bad records.</p>'+table(quality,['Source','Check','Rows'])
    body+='<h2>Source files</h2>'+''.join('<p><code>'+html.escape(str(p))+'</code><br>SHA-256: <code>'+hashes[str(p)]+'</code></p>' for p in (ENR,TRIAL,CAP))
    body+='<p>Separate evidence: sample_comparison.csv, counted_source_rows.csv, sample_unresolved_rows.csv and source_quality_counts.csv. Audit contains no player names or phone numbers. No application business rules or sources were changed by this audit.</p></body></html>'
    (OUT/'Validation_Report.html').write_text(body,encoding='utf-8')
    print(json.dumps({'rows':(len(enrollments),len(trials)),'comparisons':len(results),'failures':len(differences),'unchanged':unchanged,
        'samples':[{k:r.get(k) for k in ('Case','Date','Independent enrolled','Independent booked rows','Independent preview','Unresolved source rows')} for r in results]}))


if __name__=='__main__':main()
