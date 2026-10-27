import csv,json,hashlib,sys
from pathlib import Path
from collections import Counter
import openpyxl
import zipfile,xml.etree.ElementTree as ET,io,re
class SparseSheet:
 def __init__(self,name,root,strings,data_only):
  self.title=name;self._cells={};self.merged_cells=type('M',(),{'ranges':[]})()
  ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
  root,removed=re.subn(rb'<row\b[^>]*r="[0-9]+"[^>]*><c r="K[0-9]+"[^>]*><v>(?:413|1)</v></c></row>',b'',root)
  if removed:print('Compressed repeated K-only rows:',name,removed,'constant:','Child - Adult (shared string index differs between copies)',flush=True)
  for _,el in ET.iterparse(io.BytesIO(root),events=['end']):
   if el.tag.endswith('}c'):
    address=el.get('r');v=el.find('m:v',ns);value=v.text if v is not None else None
    if el.get('t')=='s' and value is not None:value=strings[int(value)]
    if el.get('t')=='inlineStr':value=''.join(x.text or '' for x in el.iter('{'+ns['m']+'}t'))
    formula=el.find('m:f',ns)
    if formula is not None and not data_only:value='='+str(formula.text or '')
    if value is not None:
     col,row=openpyxl.utils.cell.coordinate_from_string(address)
     self._cells[address]=type('C',(),{'value':value,'coordinate':address,'row':row,'column':openpyxl.utils.column_index_from_string(col),'column_letter':col,'data_type':'f' if formula is not None else 's'})()
    el.clear()
   elif el.tag.endswith('}mergeCell'):self.merged_cells.ranges.append(openpyxl.worksheet.cell_range.CellRange(el.get('ref')))
  self.max_row=max((c.row for c in self._cells.values()),default=0);self.max_column=max((c.column for c in self._cells.values()),default=0)
 def __getitem__(self,key):
  if isinstance(key,int):return tuple(self.cell(key,c) for c in range(1,self.max_column+1))
  if key in self._cells:return self._cells[key]
  col,row=openpyxl.utils.cell.coordinate_from_string(key)
  return type('C',(),{'value':None,'coordinate':key,'data_type':'n','row':row,'column':openpyxl.utils.column_index_from_string(col),'column_letter':col})()
 def cell(self,row,col):return self[openpyxl.utils.get_column_letter(col)+str(row)]
 def __iter__(self):
  rows={}
  for c in self._cells.values():rows.setdefault(c.row,[]).append(c)
  for number,cells in sorted(rows.items()):yield tuple(self.cell(number,c) for c in range(1,self.max_column+1))
 @property
 def values(self):return (tuple(c.value for c in row) for row in self)
class SparseBook:
 def __init__(self,path,data_only):
  ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'};self.sheets={}
  with zipfile.ZipFile(path) as z:
   strings=[]
   if 'xl/sharedStrings.xml' in z.namelist():strings=[''.join(t.text or '' for t in si.iter('{'+ns['m']+'}t')) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
   rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
   for s in ET.fromstring(z.read('xl/workbook.xml')).find('m:sheets',ns):
    target=rels[s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')];member=target.lstrip('/') if target.startswith('/') else 'xl/'+target
    self.sheets[s.get('name')]=SparseSheet(s.get('name'),z.read(member),strings,data_only)
  self.sheetnames=list(self.sheets)
 def __iter__(self):return iter(self.sheets.values())
 def __getitem__(self,name):return self.sheets[name]

ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
from workbook_capacity import read_main
from slot_thresholds import schedule
from datetime import date,timedelta
out=ROOT/'outputs'/'source_audit_2026-10-22';out.mkdir(exist_ok=True)
settings=json.loads((ROOT/'config.json').read_text())
paths=[next(ROOT.glob('*enrollment*.csv')),Path(settings['trial_source']),Path(settings['slot_capacity_source']),next(ROOT.glob('Greenfield*.xlsx')),next(ROOT.glob('*trial*.xlsx'))]
manifest=[];books={}
for p in paths:
 if not p.exists():continue
 manifest.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
 if p.suffix=='.xlsx':
  w=SparseBook(p,False);v=SparseBook(p,True)
  books[str(p)]=(w,v)
  print(p.name,[(s.title,s.max_row,s.max_column) for s in w])
with paths[0].open(encoding='utf-8-sig',newline='') as f:
 reader=csv.DictReader(f);headers=reader.fieldnames;enroll=list(reader)
print('ENROLLMENT',len(enroll),'headers',headers)
trial=books[str(paths[1])][1]
print('TRIAL HEADERS',[[c.value for c in s[1]] for s in trial])
# Compare raw cell values in every sheet, not just MAIN.
a,b=books[str(paths[2])][0],books[str(paths[3])][0]
diffs=[]
for name in set(a.sheetnames)|set(b.sheetnames):
 if name not in a.sheetnames or name not in b.sheetnames:diffs.append({'sheet':name,'difference':'Sheet only exists in one copy'});continue
 for row in a[name]:
  for c in row:
   other=b[name][c.coordinate].value
   if c.value!=other:diffs.append({'sheet':name,'cell':c.coordinate,'configured':c.value,'workspace':other})
 for row in b[name]:
  for c in row:
   if c.row>a[name].max_row or c.column>a[name].max_column:
    if c.value is not None:diffs.append({'sheet':name,'cell':c.coordinate,'configured':None,'workspace':c.value})
print('CAPACITY COPY DIFFERENCES',len(diffs),diffs[:10])
records,_=read_main(paths[2]);audit=[];mismatch=[]
cols=['M','P','S','V','Y','AB','AE'];days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
ws=books[str(paths[2])][1]['MAIN'];form=books[str(paths[2])][0]['MAIN']
for r in records:
 for day,col in enumerate(cols):
  for field,offset in [('capacities',0),('proficiency',1),('reported_counts',2)]:
   c=ws.cell(r['row'],openpyxl.utils.column_index_from_string(col)+offset)
   expected=None if c.value is None else str(c.value)
   if r[field][day]!=expected:mismatch.append({'cell':c.coordinate,'parser':r[field][day],'raw':expected})
 for day in range(7):
  batches=schedule([r],date(2026,10,19)+timedelta(days=day))
  for batch in batches:
   if not r['center']:continue
   capcol=openpyxl.utils.column_index_from_string(cols[day]);cell=ws.cell(r['row'],capcol)
   merges=[str(m) for m in ws.merged_cells.ranges if cell.coordinate in m]
   audit.append({'center':r['center'],'city':r['city'],'sport':r['sport'],'row':r['row'],'time':r['time'],'days_text':r['days'],'weekday':days[day],'capacity_cell':cell.coordinate,'capacity':batch['capacity'],'proficiency':batch['division'],'reported_count':batch['workbook_reported_count'],'issues':'; '.join(batch['issues']),'merged_range':'; '.join(merges),'formula':form[cell.coordinate].value if form[cell.coordinate].data_type=='f' else '', 'all_week_capacities':json.dumps(r['capacities'])})
missing=[r for r in audit if r['weekday']=='Thursday' and r['capacity'] is None]
centers={r['center'] for r in missing};terms=['yashwant','sanpada','rolex']
# Scan every cell of every sheet for the affected center labels, including loose name matches.
hits=[]
for name,(w,v) in books.items():
 if 'trial' in Path(name).name:continue
 for s in v:
  for row in s:
   matching=[c for c in row if isinstance(c.value,str) and (c.value in centers or any(t in c.value.lower() for t in terms))]
   if matching:hits.append({'file':name,'sheet':s.title,'row':row[0].row,'matched_cells':[c.coordinate for c in matching],'values':{c.column_letter:str(c.value) for c in row if c.value is not None}})
# Safe aggregate cross-source search; no student details in outputs.
cross=[]
for center in sorted(centers):
 tokens=set(center.lower().replace('(',' ').replace(')',' ').replace('.',' ').split())-{'school','intl','international','sports','the','city','east','west','smart','park','box','center','centre'}
 def match(label):return label==center or any(t in str(label).lower() for t in tokens if len(t)>3)
 er=[r for r in enroll if match(r.get('Coaching Center Location',''))]
 ts=[];trial_headers=[]
 for s in trial:
  rows=list(s.values)
  if not rows:continue
  hh=[str(x or '') for x in rows[0]];trial_headers=hh
  if 'Coaching Center' in hh:
   ts.extend(dict(zip(hh,row)) for row in rows[1:] if match(dict(zip(hh,row)).get('Coaching Center','')))
 cross.append({'capacity_center':center,'enrollment_rows_any_date':len(er),'enrollment_labels':sorted({r.get('Coaching Center Location','') for r in er}),'trial_rows_any_date':len(ts),'trial_labels':sorted({str(r.get('Coaching Center','')) for r in ts}),'enrollment_slots':sorted({r.get('Slots','') for r in er}),'enrollment_courses':sorted({r.get('Course Name','') for r in er}),'note':'Loose-name candidates only; not approved identity matches. Occupancy records do not establish a capacity limit.'})
for name,rows in [('all_weekday_audit',audit),('thursday_missing_capacity',missing)]:
 with (out/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
result={'sources':manifest,'capacity_copy_differences':diffs,'parser_mismatches':mismatch,'enrollment_headers':headers,'enrollment_row_count':len(enroll),'trial_headers':trial_headers,'missing_thursday_batches':len(missing),'affected_centers':len(centers),'weekday_summary':{d:{'batches':sum(r['weekday']==d for r in audit),'missing_capacity':sum(r['weekday']==d and r['capacity'] is None for r in audit)} for d in days},'cross_source_candidates':cross,'all_sheet_center_hits':hits}
(out/'evidence.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
print('PARSER MISMATCHES',len(mismatch),'THURSDAY MISSING',len(missing),'CENTERS',len(centers))
print('CROSS SOURCE',json.dumps([{k:v for k,v in r.items() if k not in ('enrollment_slots','enrollment_courses')} for r in cross]))
print('ALL SHEET HITS',Counter((Path(h['file']).name,h['sheet']) for h in hits))
print('SOURCE HASHES UNCHANGED',all(hashlib.sha256(Path(x['path']).read_bytes()).hexdigest()==x['sha256'] for x in manifest))
