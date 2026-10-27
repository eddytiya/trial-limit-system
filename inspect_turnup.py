import csv,openpyxl,collections,re,json,datetime
from pathlib import Path
base=Path.cwd(); out=base/'outputs'/'turnup_20261023';out.mkdir(parents=True,exist_ok=True)
norm=lambda x: re.sub(r'[^a-z0-9]','',str(x or '').lower())
f=next((base/'input').glob('academy___*.csv'))
pairs=collections.defaultdict(set); academies=collections.defaultdict(set)
with f.open(encoding='utf-8-sig',newline='') as h:
 for r in csv.DictReader(h):
  if r['Sports'].strip():
   pairs[norm(r['Academy Name']),norm(r['Coaching Center Location'])].add(r['Sports'].strip());academies[norm(r['Academy Name'])].add(r['Sports'].strip())
w=openpyxl.load_workbook(base/'input/trials status vs who actually turned up.xlsx',read_only=True,data_only=True)
rows=list(w['Original'].values);heads=rows.pop(0)
print('academy sports',dict(academies))
print('nonempty',sum(any(v is not None for v in r) for r in rows))
print('exact dup',len(rows)-len(set(rows)))
print('dates',min(str(r[9]) for r in rows if r[9]),max(str(r[9]) for r in rows if r[9]))
print('rescheduled samples',[(r[9],r[12],r[13],r[15]) for r in rows if r[15]=='rescheduled'][:5])
print('missing scheduled',sum(not r[9] for r in rows))
print('academy ambiguities',{a:list(v) for a,v in academies.items() if len(v)>1})
