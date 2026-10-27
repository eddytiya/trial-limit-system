"""Apply owner-authorized clear scopes; preserve all original source labels."""
import csv,json,sys,hashlib,re
from pathlib import Path
from datetime import date,timedelta,datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from slot_thresholds import targets,schedule
from workbook_capacity import read_main
from capacity_overrides import resolve_centers
from batch_mappings import club_key,source_key,definition,target_identity,saved_link

ROOT=Path(__file__).resolve().parents[1]
config=json.loads((ROOT/'config.json').read_text())
mp=ROOT/'approved_batch_mappings.json'
store=json.loads(mp.read_text(encoding='utf-8'))
ep=next(ROOT.glob('*enrollment*.csv'));cp=Path(config['slot_capacity_source'])
hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ep,cp)}
with ep.open(encoding='utf-8-sig',newline='') as f:enrollments=list(enumerate(csv.DictReader(f),2))
options=targets(enrollments)
records,chash=read_main(cp)
records,_=resolve_centers(records,chash,ROOT/'capacity_center_overrides.json')

def normal(value):
    return re.sub(r'\s+',' ',value.strip().lower())

def course_level(value):
    value=normal(value)
    return {'advance':'advanced','beginners':'beginner'}.get(value,value)

def scope(batch,target):
    label=normal(batch['division'] or '')
    memberships=[(m['age'],m['course']) for m in target['proficiency_memberships']]
    if batch['center']=='Bavdhan Sports Club' and label in ('kids 5-12yrs','kids/adults 12 +','adults 18+'):
        pairs=[list(p) for p in memberships]
        return (pairs,None) if pairs else (None,'No enrollment memberships available for approved open scope')
    if label in ('open','open age'):
        return [],None
    # Specific owner-approved equivalents; source labels remain unchanged.
    if (batch['center'],label) in (('SMT School, Boosters, Thane','basic'),('CPR Pashan Racquet Arena','elite')):
        expected='beginner' if label=='basic' else 'elite tennis'
        pairs=[list(p) for p in memberships if course_level(p[1])==expected]
        return (pairs,None) if pairs else (None,'Approved equivalent course absent from enrollment data')
    ages=None;levels=None
    if label in ('child beginer','child beginner','kids beginners'):
        ages={'child','kids'};levels={'beginner'}
    elif label in ('adult beginner','adult intermediate','adult advance'):
        ages={'adult','adults'};levels={course_level(label.split(' ',1)[1])}
    elif label in ('beginner','intermediate','advance','basic','elite','open age - beginner'):
        levels={'beginner'} if label=='open age - beginner' else {course_level(label)}
    elif label in ('beginners/intermmediate','beginner + intermediate'):
        levels={'beginner','intermediate'}
    elif label in ('adult','adults'):
        ages={'adult','adults'}
    elif label=='kids':
        ages={'child','kids'}
    elif label=='child-adult':
        ages={'child','kids','adult','adults'}
    elif label=='kids/adults intermediate/advance':
        levels={'intermediate','advanced'}
    else:
        return None,'Missing/placeholder proficiency or age definition requires source clarification'
    pairs=[(a,c) for a,c in memberships if (ages is None or normal(a) in ages)
           and (levels is None or course_level(c) in levels)]
    if not pairs:return None,'No exact compatible age/course memberships in current enrollment data'
    if levels and {course_level(c) for a,c in pairs}!=levels:
        return None,'One or more required proficiency levels absent from enrollment memberships'
    if label=='child-adult' and not ({'child','adult'} <= {normal(a) for a,c in pairs}):
        return None,'Both Child and Adult memberships are not available'
    return [list(p) for p in pairs],None

report=[];approved=[]
for offset in range(7):
    for b in schedule(records,date(2026,10,19)+timedelta(days=offset)):
        if not b.get('center') or not b['center'].strip() or club_key(b) in store.get('excluded_clubs',{}):continue
        club=store['clubs'].get(club_key(b))
        target=next((t for t in options if club and target_identity(t)==club['target']),None)
        pairs,reason=(None,'Center intentionally unmapped or enrollment target unavailable') if target is None else scope(b,target)
        if not reason and b['issues']:reason='Schedule definition needs review: '+'; '.join(b['issues'])
        entry={'center':b['center'],'sport':b['sport'],'weekday':b['weekday'],'row':b['source_row'],
               'time':b['time'],'proficiency':b['division'],'pairs':pairs,'status':'Unresolved' if reason else 'Approved','reason':reason}
        report.append(entry)
        if reason:continue
        store['batches'][source_key(b,cp.name)]={'definition':definition(b),'target':target_identity(target),
            'age':'','proficiency_pairs':pairs,'source_name':cp.name,'source_hash':chash,
            'approved_at':datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(),
            'approval_basis':'Owner authorized mapping all clear basic age/proficiency scopes; preserve exact source labels.'}
        approved.append((b,target))
for b,target in approved:
    link,status=saved_link(store,b,options,cp.name,chash)
    assert link is not None,(b,status)
assert all(hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in hashes.items())
mp.write_text(json.dumps(store,indent=2),encoding='utf-8')
(ROOT/'outputs'/'scope_mapping_results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
from collections import Counter
print(json.dumps({'approved_weekday_pools':len(approved),'approved_labels':dict(Counter(b['division'] for b,t in approved)),
    'unresolved_weekday_pools':sum(r['status']=='Unresolved' for r in report),'source_files_unchanged':True},indent=2))
