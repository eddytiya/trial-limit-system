import json,collections
from pathlib import Path
p=Path('outputs/turnup_20261023');d=json.loads((p/'analysis.json').read_text());rows=[r for r in d['data'] if not r[11] and r[5] and r[5]<='2026-10-23']
sports=sorted({r[3] for r in rows if r[3]!='Unmapped'})
def counts(a):
 c=collections.Counter(r[9] for r in a)
 return [len(a),c['attended'],c['not_attended'],c['rescheduled'],sum(v for k,v in c.items() if k not in ['attended','not_attended','rescheduled'])]
result={}
for grain,idx in [('Daily',5),('Monthly',6)]:
 groups=collections.defaultdict(list)
 for r in rows:
  if r[3]!='Unmapped':groups[(r[3],r[idx])].append(r)
 result[grain]=[[s,t,*counts(a),None] for (s,t),a in sorted(groups.items())]
summary=[]
for s in sports:
 a=[r for r in rows if r[3]==s];line=[s]
 for sub in [a,[r for r in a if '2026-07-23'<=r[5]<='2026-10-23'],[r for r in a if '2026-06-01'<=r[5]<'2026-09-01']]:line.extend(counts(sub)[:2]+[None])
 summary.append(line)
result['summary']=summary
result['unmapped']=sum(r[3]=='Unmapped' for r in rows)
(p/'daily_monthly.json').write_text(json.dumps(result));print('rows', {k:len(v) for k,v in result.items() if isinstance(v,list)},'unmapped',result['unmapped'])

