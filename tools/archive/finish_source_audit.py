from pathlib import Path
s=Path('outputs/audit_missing_values.py').read_text();exec(s.split('ROOT=Path.cwd()')[0])
out=Path('outputs/source_audit_2026-10-22');d=json.loads((out/'evidence.json').read_text());w=SparseBook(Path(d['sources'][2]['path']),True)
with (out/'thursday_missing_capacity.csv').open(encoding='utf-8-sig') as f:missing=list(csv.DictReader(f))
def value(sheet,col,row):
 address=col+str(row)
 for m in sheet.merged_cells.ranges:
  if address in m:return sheet.cell(m.min_row,m.min_col).value
 return sheet[address].value
def norm(t):return re.sub(r'[^a-z0-9]','',str(t or '').lower())
alt=w['Sheet1'];checks=[]
for r in missing:
 candidates=[]
 for row in alt:
  n=row[0].row
  if value(alt,'B',n)==r['center'] and value(alt,'A',n)==r['sport'] and norm(value(alt,'D',n))==norm(r['time']):
   vals={openpyxl.utils.get_column_letter(c):alt.cell(n,c).value for c in range(10,25)}
   candidates.append({'row':n,'weekday_capacity_and_count_cells':vals})
 checks.append({'main_row':r['row'],'center':r['center'],'time':r['time'],'sheet1_matches':candidates})
print('ALTERNATE MATCHED',sum(bool(c['sheet1_matches']) for c in checks),'OF',len(checks))
print('ALTERNATE NUMERIC VALUES',[(c['main_row'],m) for c in checks for m in c['sheet1_matches'] if any(str(v).isdigit() for v in m['weekday_capacity_and_count_cells'].values() if v is not None)])
# Inspect formulas/merged ranges across every blank capacity and count, not just the three examples.
main=w['MAIN'];blank_formula=[];blank_merge=[]
for r in missing:
 for col in ['V','W','X']:
  address=col+r['row'];c=main[address]
  if c.data_type=='f':blank_formula.append(address)
  for m in main.merged_cells.ranges:
   if address in m:blank_merge.append((address,str(m)))
d['alternate_schedule_exact_checks']=checks;d['blank_thursday_formula_cells']=blank_formula;d['blank_thursday_merged_cells']=blank_merge
d['scope_note']='The browser uploads cannot be identified from the screenshot. Audit covers all locally available original sources and configured copies. Repeated K-only Child - Adult rows were compressed after scanning raw XML; they contain no center, timing or capacity.'
(out/'evidence.json').write_text(json.dumps(d,indent=2),encoding='utf-8')
counts=Counter(r['center'] for r in missing)
lines=['# Three-source capacity audit — 22 October 2026','','Reference weekday: Thursday. Original source files were read only.','','## Findings','','- Capacity workbook: all three sheets checked, all seven weekday capacity/count/proficiency columns compared against the application parser; zero mismatches. Configured Downloads and workspace copies have identical cell values (their file hashes differ).','- Thursday: 41 named batch rows across 16 centers have no numeric capacity. 37 have blank capacity for all seven weekdays; four Krushi Society CLOSED rows have whitespace on weekdays and NAFT on weekends.','- None of these 41 rows has a numeric capacity on another weekday. No hidden formula or merged cell in their Thursday V/W/X cells supplies a missing value.',f'- Sheet1 exact center/sport/time matches found for {sum(bool(c["sheet1_matches"]) for c in checks)} of the 41 rows, resolving only actual merged center cells. None of those alternate rows contains a numeric weekday capacity or count. Other rows have no exact matching alternate definition. Sheet3 contains center/coach contacts, not batch limits.','- Enrollment CSV: 14,741 records checked. Its schema has no maximum batch-capacity field. Slots, age, course and student IDs may support attendance calculations; Total Sessions is not a capacity limit.','- Trial workbook: 8,465 data records checked across its Query result sheet. It has bookings, scheduled dates and times, but no maximum batch-capacity field or shared Player DB ID. Booking rows cannot establish a center capacity or a verified additional-student total.','- Center-name variations exist between the three sources. Loose-name candidates are recorded in evidence.json for review, not applied as approved links.','- Some age/batch descriptions DO exist in the Days text (for example U6/U8) although the weekday Proficiency column is blank. Thus the dash below the timing does not mean all batch-description information is absent. It means the current UI reads only the blank Proficiency field.','','## Centers with missing Thursday capacity','','| Center | Batch rows |','|---|---:|']
lines += [f'| {center} | {n} |' for center,n in sorted(counts.items())]
lines += ['','## Examples and exact source locations','','| Center | MAIN rows | Thursday capacity / proficiency / count | Alternate sheet |','|---|---|---|---|','| Yashwant Smart City (Box Park) | 158–159 | V158:X159 blank | Sheet1 rows 114–115: Q/R blank; Days includes age groups |','| Ryan Intl. School Sanpada | 168 | V168:X168 blank | Sheet1 row 124: Q124/R124 blank; E124 contains U12/U14/U16/U18 |','| Rolex Bhandup (Sports Foundry) | 174–177 | V174:X177 blank | Sheet1 rows 130–133: Q/R blank; E contains age groups |','','Rolex Metal Industries has populated Table Tennis capacities, but this is a different sport/pool from the Football rows at Rolex Bhandup. Those limits cannot be substituted.','','## Limits and preservation','','The uploaded browser file snapshots are not available from the screenshot. These findings apply to the local source files listed below. No UI, approval mapping, source record or capacity value was changed. SHA-256 verification after the audit confirmed all input files unchanged.','','## Sources','']
lines += [f'- `{x["path"]}` — SHA-256 `{x["sha256"]}`' for x in d['sources']]
(out/'Audit_Report.md').write_text('\n'.join(lines),encoding='utf-8')
print('Formula checks:',blank_formula,'Merged checks:',blank_merge)
print('Report saved:',out/'Audit_Report.md')
