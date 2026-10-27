import json,collections
from pathlib import Path
p=Path('outputs/turnup_20261023');d=json.loads((p/'analysis.json').read_text())
def period(date,k):
 if not date:return False
 return {'All completed months':date<'2026-10-01','Latest 3 completed months':'2026-07-01'<=date<'2026-10-01','Rainy Jun-Aug 2026':'2026-06-01'<=date<'2026-09-01','Other completed months':date<'2026-10-01' and not '2026-06-01'<=date<'2026-09-01'}[k]
periods=['All completed months','Latest 3 completed months','Rainy Jun-Aug 2026','Other completed months']
result=[]
for sport in ['Overall']+sorted({r[3] for r in d['data']}):
 for k in periods:
  a=[r for r in d['data'] if not r[11] and period(r[5],k) and (sport=='Overall' or r[3]==sport)]
  result.append([sport,k,len(a),sum(r[9]=='attended' for r in a),sum(r[9]=='not_attended' for r in a),sum(r[9] in ['booked','unmarked'] for r in a),None])
(p/'period_comparison.json').write_text(json.dumps(result))
print(result[:4])
