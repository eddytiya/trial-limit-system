from pathlib import Path
s=Path('outputs/audit_missing_values.py').read_text();exec(s.split('ROOT=Path.cwd()')[0])
p=Path(json.loads(Path('config.json').read_text())['slot_capacity_source']);w=SparseBook(p,True)
for row in w['Sheet1']:
 if row[0].row<=2 or 75<=row[0].row<=173:print(row[0].row,{c.column_letter:c.value for c in row if c.value is not None and c.column_letter not in ['F','G','H','I']})
