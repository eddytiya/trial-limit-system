"""Export the capacity snapshot as Trino/Presto-style SQL; never modify inputs."""
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from workbook_capacity import read_main, weekdays, time_range
from session_capacity import WEEKDAYS

SOURCE = ROOT / 'input/Greenfield Batch & Coach details (2).xlsx'
OUT = ROOT / 'outputs/metabase_capacity'

def literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"

def number(value):
    try:
        n = int(str(value).strip())
        return n if n >= 0 else None
    except (ValueError, TypeError):
        return None

def build():
    records, digest = read_main(SOURCE)
    rows = []
    for r in records:
        errors = []
        try:
            days = weekdays(r['days'])
        except ValueError as e:
            days = None
            errors.append(str(e))
        try:
            start, end = time_range(r['time'])
        except (ValueError, TypeError) as e:
            start = end = None
            errors.append(str(e))
        if not r['center'] or not r['sport']:
            errors.append('Missing center or sport')
        import re
        if re.search('closed|on hold|renovation', r['center'] or '', re.I):
            errors.append('Center unavailable; review source')
        for i, day in enumerate(WEEKDAYS):
            capacity = number(r['capacities'][i])
            scheduled = None if days is None else int(i in days)
            issues = list(errors)
            if scheduled == 1 and capacity is None:
                issues.append('Missing or nonnumeric capacity')
            # Approved rule: explicit weekday capacity takes precedence over
            # the prose days list. Keep raw days/capacity for source auditing.
            if scheduled == 0 and capacity is not None:
                scheduled = 1
            state = 'Needs Review' if issues else ('Not Scheduled' if scheduled == 0 else 'Valid Source Capacity')
            rows.append([f'MAIN:{r["row"]}:{i+1}',r['row'],r['center'],r['city'],r['sport'],
                         i+1,day,r['time'],start,end,r['days'],scheduled,r['proficiency'][i],
                         r['capacities'][i],capacity,r['reported_counts'][i],number(r['reported_counts'][i]),
                         state,'; '.join(issues), 'Requires approved enrollment/trial mapping',SOURCE.name,digest])
    # Duplicate definitions stay visible and cannot silently form separate capacity pools.
    signatures = Counter((r[2],r[3],r[4],r[5],r[8],r[9],r[12]) for r in rows if r[11] == 1)
    for r in rows:
        key = (r[2],r[3],r[4],r[5],r[8],r[9],r[12])
        if r[11] == 1 and signatures[key] > 1:
            r[17] = 'Needs Review'
            r[18] = '; '.join(filter(None,[r[18],'Overlapping source definitions; verify division before combining']))
    columns = ['capacity_row_id','source_row','coaching_center','city','sport','weekday_number','weekday',
               'batch_time_raw','start_minute','end_minute','days_raw','scheduled_flag','division_raw',
               'capacity_raw','capacity','workbook_count_raw','workbook_reported_count','source_status',
               'review_reason','mapping_status','source_file','source_sha256']
    integers = {1,5,8,9,11,14,16}
    values = ',\n'.join('    (' + ', '.join(literal(v) for v in row) + ')' for row in rows)
    projection = ',\n'.join(f'  CAST({c} AS {"BIGINT" if i in integers else "VARCHAR"}) AS {c}' for i,c in enumerate(columns))
    query = ('-- Assumes the Trino/Presto SQL dialect used by the supplied reports.\n'
             '-- Snapshot only: regenerate when workbook changes. No live occupancy is calculated here.\n'
             '-- Mapping approvals from other workbook hashes are intentionally not applied.\n'
             'SELECT\n' + projection + '\nFROM (\n  VALUES\n' + values + '\n) AS capacity_source (\n  ' + ', '.join(columns) + '\n)')
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'capacity_master_metabase.sql').write_text(query+'\n',encoding='utf-8')
    # Athena caps query text at 262144 characters. Dictionary-encode repeated
    # text once, decoding in SELECT without altering the output dataset.
    texts = list(dict.fromkeys(v for row in rows for i,v in enumerate(row)
                               if i not in integers and v is not None))
    lookup = {v:i+1 for i,v in enumerate(texts)}
    compact_values = ',\n'.join('('+','.join(
        literal(v if i in integers or v is None else lookup[v])
        for i,v in enumerate(row))+')' for row in rows)
    compact_projection = ',\n'.join(
        f'  CAST(v.{c} AS BIGINT) AS {c}' if i in integers else
        f'  element_at(d.texts, CAST(v.{c} AS INTEGER)) AS {c}'
        for i,c in enumerate(columns))
    dictionary_sql = 'concat(' + ','.join('ARRAY[' + ','.join(literal(t) for t in texts[j:j+100]) + ']'
                                         for j in range(0,len(texts),100)) + ')'
    compact = ('-- Athena capacity snapshot. Save as Academy Capacity Master.\n'
               'WITH text_dictionary AS (SELECT '+dictionary_sql+' AS texts),\n'
               'capacity_values AS (SELECT * FROM (VALUES\n'+compact_values+
               '\n) AS src('+','.join(columns)+'))\nSELECT\n'+compact_projection+
               '\nFROM capacity_values v CROSS JOIN text_dictionary d\n')
    assert len(compact.encode('utf-8')) < 262144
    decoded = [[v if i in integers or v is None else texts[lookup[v]-1]
                for i,v in enumerate(row)] for row in rows]
    assert decoded == rows
    (OUT/'capacity_master_athena.sql').write_text(compact,encoding='utf-8')
    print(f'Athena compact SQL: {len(compact.encode("utf-8"))} bytes; all {len(rows)} rows round-trip verified')
    (OUT/'create_capacity_master.sql').write_text(
        '-- Run only with CREATE privileges in the intended catalog/schema.\n'
        '-- Qualify academy_capacity_master with your catalog/schema if necessary.\n'
        '-- Fails if the table exists; does not replace existing data.\n'
        'CREATE TABLE academy_capacity_master AS\n'+query+';\n',encoding='utf-8')
    counts = Counter(r[17] for r in rows)
    assert len(rows) == len(records)*7
    assert len({r[0] for r in rows}) == len(rows)
    assert all(r[14] is None or r[14] >= 0 for r in rows)
    (OUT/'README.txt').write_text(
        'CAPACITY MASTER FOR METABASE\n\n'
        'Dialect assumption: Trino/Presto, inferred from the supplied SQL; not verified on your server.\n'
        '1. Open New > SQL query and select the SAME connection used by enrollment/trials.\n'
        '2. Paste capacity_master_metabase.sql, run, and save as Academy Capacity Master.\n'
        '   This is a saved query dataset, not a physical MongoDB collection.\n'
        '3. If a stored table is required, an administrator can run create_capacity_master.sql\n'
        '   through a write-enabled Trino connection, after confirming target catalog/schema.\n'
        '   Then query SELECT * FROM academy_capacity_master in Metabase.\n\n'
        f'Source: {SOURCE.name}\nSHA256: {digest}\n'
        f'Source schedule rows: {len(records)}; weekday rows: {len(rows)}\nStatus totals: {dict(counts)}\n\n'
        'Each row represents one original workbook row and weekday. No age divisions are\n'
        'expanded into extra capacity pools. Capacity_raw preserves NA/blank source values;\n'
        'capacity is NULL when not a nonnegative integer. Zero remains zero.\n'
        'Minutes are local wall-clock minutes after midnight in Asia/Kolkata.\n'
        'workbook_reported_count is a snapshot reference, never the live enrollment count.\n'
        'Not Scheduled rows are retained for audit. Use scheduled_flag=1 and\n'
        "source_status='Valid Source Capacity' to inspect usable source capacities.\n"
        'All rows still require verified enrollment/trial mappings before occupancy joins.\n'
        'No database IDs, effective dates, or ambiguous centers are invented. Existing\n'
        'snapshot-specific approvals are not transferred to this new workbook hash.\n'
        'Do not join live enrollments or trials on center name alone or sum duplicate pools.\n'
        'No remote database execution or SQL-engine syntax validation has been performed.\n',encoding='utf-8')
    print(f'Generated {len(rows)} weekday rows from {len(records)} source rows; {dict(counts)}')
    print(OUT)

if __name__ == '__main__':
    build()
