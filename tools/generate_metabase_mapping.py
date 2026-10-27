"""Carry forward only capacity definitions that match approved mappings exactly."""
import json
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from workbook_capacity import read_main
from batch_mappings import definition, digest
from generate_metabase_capacity import literal, number
from session_capacity import WEEKDAYS

records, _ = read_main(ROOT / 'input/Greenfield Batch & Coach details (2).xlsx')
store = json.loads((ROOT / 'mapped/approved_batch_mappings.json').read_text(encoding='utf-8'))
index = {}
for entry in store['batches'].values():
    index.setdefault(digest(entry['definition']), []).append(entry)
links = []
for r in records:
    for i, day in enumerate(WEEKDAYS):
        candidate = dict(center=r['center'], city=r['city'], sport=r['sport'],
                         weekday=day, time=r['time'], division=r['proficiency'][i],
                         capacity=number(r['capacities'][i]), days=r['days'])
        matches = index.get(digest(definition(candidate)), [])
        if len(matches) != 1:
            continue
        m = matches[0]
        club = store['clubs'].get(digest({k:candidate[k] for k in ('center','city','sport')}))
        if club and club['target'] != m['target']:
            continue
        t = m['target']
        links.append([f'MAIN:{r["row"]}:{i+1}',t['academy_id'],t['academy'],t['center'],
                      t['sport'],m['age'],json.dumps(m['proficiency_pairs'],ensure_ascii=False)])
assert links and len({r[0] for r in links}) == len(links)
values = ',\n'.join('('+','.join(literal(v) for v in row)+')' for row in links)
query = '''-- Match verified capacity definitions to existing approved mappings.
-- Live age/course membership and trial coverage still require verification.
WITH approved_links AS (
  SELECT * FROM (VALUES
'''+values+'''
  ) AS x(capacity_row_id, academy_id, academy_name, enrollment_center,
         enrollment_sport, approved_age, approved_course_pairs_json)
), capacity AS {{#448}}
SELECT c.*, m.academy_id AS mapped_academy_id,
       m.academy_name AS mapped_academy_name,
       m.enrollment_center AS mapped_enrollment_center,
       m.enrollment_sport AS mapped_enrollment_sport,
       m.approved_age, m.approved_course_pairs_json,
       CASE WHEN m.capacity_row_id IS NULL THEN 'Needs mapping review'
            ELSE 'Prior approved definition verified' END AS definition_mapping_status
FROM capacity c
LEFT JOIN approved_links m ON m.capacity_row_id = c.capacity_row_id
'''
out = ROOT / 'outputs/metabase_capacity/capacity_mapped_metabase.sql'
out.write_text(query,encoding='utf-8')
expanded_size = len(query.encode()) + (ROOT / 'outputs/metabase_capacity/capacity_master_athena.sql').stat().st_size
assert expanded_size < 250000, expanded_size
print(f'Verified prior definitions: {len(links)} / {len(records)*7}')
print(f'Conservative expanded query size: {expanded_size} bytes')
print(out)
