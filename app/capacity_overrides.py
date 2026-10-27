"""Snapshot-specific, user-confirmed references; source files are never filled in."""
import json


def resolve_centers(records,source_hash,path):
    output=[dict(r) for r in records]
    if not path.exists():return output,[]
    store=json.loads(path.read_text(encoding='utf-8'))
    if store.get('version')!=1:raise ValueError('Invalid capacity center reference version')
    applied=[]
    for override in store.get('overrides',[]):
        if override.get('source_hash')!=source_hash:continue
        for record in output:
            if record['row'] not in override['rows']:continue
            if record.get('center') and record['center'].strip():continue
            if record.get('sport')!=override['sport'] or record.get('city')!=override['city']:
                continue
            record['source_center']=record.get('center')
            record['center']=override['center']
            record['center_resolution']='User-confirmed reference; original center cell remains blank'
            applied.append(record['row'])
    return output,applied
