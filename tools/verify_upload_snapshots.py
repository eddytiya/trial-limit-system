"""Verify existing approved pools against independent source-row filtering; never write inputs."""
import sys,json,hashlib
from pathlib import Path
from datetime import date,datetime
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'app'))
from slot_thresholds import slot_snapshot,evaluate,enrollment_sport
from automatic_capacity import read_source,ENROLLMENT_FIELDS
from raw_trial_source import read_trial_xlsx
from session_capacity import parse_slots
from workbook_capacity import minutes
p=PROJECT/'input';e=next(p.glob('*enrollment*.csv'));t=next(p.glob('*trial_booking*.xlsx'));c=p/'Greenfield Batch & Coach details (2).xlsx'
before={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in p.iterdir() if x.is_file()}
reference=date(2026,10,19)
r=slot_snapshot({'reference_date':reference.isoformat()},e,t,c,PROJECT/'mapped/approved_batch_mappings.json')
rows,_=read_source(e,ENROLLMENT_FIELDS);trials,_=read_trial_xlsx(t)
checks=[];zero=[]
for b in r['batches']:
 m=b.get('approved_mapping')
 if not m or b['issues']:continue
 target=next(x for x in r['targets'] if x['id']==m['target_id'])
 result=evaluate(b,target,m['age'],rows,trials,reference,m['proficiency_pairs'])
 independent=set()
 for _,row in rows:
  if (row.get('Academy ID'),row.get('Coaching Center Location'),enrollment_sport(row))!=(target['academy_id'],target['center'],target['sport']):continue
  if b['division'] not in ('Open','Open Age'):
   if m['age'] and row.get('Age Category')!=m['age']:continue
   if [row.get('Age Category'),row.get('Course Name')] not in m['proficiency_pairs']:continue
  try:
   def source_date(value):
    return datetime.strptime(value,'%d-%m-%Y' if len(value)==10 and value[2]=='-' else '%Y-%m-%d').date()
   if not source_date(row['Start Date'])<=reference<=source_date(row['End Date']):continue
   if not any(day=='Monday' and (minutes(start),minutes(end))==(b['start'],b['end']) for day,_,start,end in parse_slots(row.get('Slots'))):continue
  except (ValueError,KeyError):continue
  if row.get('Player DB ID'):independent.add(row['Player DB ID'])
 assert len(independent)==result['enrolled'],(b['center'],len(independent),result['enrolled'])
 check={'center':b['center'],'sport':b['sport'],'time':b['time'],'capacity':b['capacity'],'independent_enrolled':len(independent),'result':result}
 (checks if independent else zero).append(check)
 if len(checks)==3:break
assert before=={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in p.iterdir() if x.is_file()}
report={'reference_date':reference.isoformat(),'source_hashes_unchanged':True,'source_hashes':before,'batch_count':len(r['batches']),'validation_issue_count':len(r['validation']['issues']),'real_batch_checks':(checks+zero)[:3]}
(PROJECT/'outputs/upload_workflow_verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps({**{k:v for k,v in report.items() if k not in ('source_hashes','real_batch_checks')},'examples':[{k:v for k,v in x.items() if k!='result'} for x in report['real_batch_checks']]}))
