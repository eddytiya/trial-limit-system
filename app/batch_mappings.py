"""Approved links live here, never in enrollment/trial/capacity sources."""
import hashlib
import json
import re
import threading
from datetime import datetime
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

LOCK=threading.RLock()
TARGET_FIELDS=('academy_id','academy','center','sport')


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def definition(batch):
    return {k:batch.get(k) for k in ('center','city','sport','weekday','time','division','capacity','days')}


def source_key(batch,source_name):
    base={k:batch.get(k) for k in ('center','city','sport','weekday','time','division')}
    if not batch.get('center'):base.update(source_name=source_name,row=batch['source_row'])
    return digest(base)


def club_key(batch):
    return digest({k:batch.get(k) for k in ('center','city','sport')}) if batch.get('center') else None


def target_identity(target):return {k:target[k] for k in TARGET_FIELDS}


def read_store(path):
    if path is None or not path.exists():return {'version':1,'clubs':{},'batches':{}}
    value=json.loads(path.read_text(encoding='utf-8'))
    if value.get('version')!=1 or not isinstance(value.get('clubs'),dict) or not isinstance(value.get('batches'),dict):
        raise ValueError('Mapping file is invalid; restore a valid mapping file before using saved links')
    return value


def saved_link(store,batch,options,source_name,source_hash):
    saved=store['batches'].get(source_key(batch,source_name))
    if not saved:return None,'Unmapped'
    club=store['clubs'].get(club_key(batch))
    if club and club['target']!=saved['target']:
        return None,'Needs review — approved club link changed'
    if saved['definition']!=definition(batch) or not batch.get('center') and saved.get('source_hash')!=source_hash:
        return None,'Needs review — capacity definition changed'
    target=next((t for t in options if target_identity(t)==saved['target']),None)
    if target is None:return None,'Needs review — enrollment club changed or missing'
    allowed={(m['age'],m['course']) for m in target['proficiency_memberships']}
    if any(tuple(p) not in allowed for p in saved['proficiency_pairs']) or saved['age'] and saved['age'] not in target['ages']:
        return None,'Needs review — age/course membership changed'
    return {**saved,'target_id':target['id']},'Approved batch mapping'


def attach_mappings(batches,options,path,source_name,source_hash):
    with LOCK:store=read_store(path)
    for target in options:
        target['club_label']=target['center']
        target['club_id']=digest(target['center'])[:16]
    for b in batches:
        b['club_label']=' · '.join(v for v in (b.get('center') or 'Source center missing',b.get('city')) if v)
        saved,status=saved_link(store,b,options,source_name,source_hash)
        club=store['clubs'].get(club_key(b))
        preferred=next((t for t in options if club and target_identity(t)==club['target']),None)
        if status=='Unmapped' and preferred:status='Club approved — batch scope needs confirmation'
        b['mapping_status']=status;b['approved_mapping']=saved
        b['club_target_id']=preferred['id'] if preferred else None
        # Similarity changes no values and grants no approval; these are suggestions only.
        sport=lambda s:re.sub('[^a-z0-9]','',(s or '').lower())
        candidates=[]
        for t in options:
            if sport(t['sport'])!=sport(b['sport']):continue
            score=SequenceMatcher(None,(b.get('center') or '').lower(),t['center'].lower()).ratio()
            if b.get('center') and score>=0.25:candidates.append((score,t['id']))
        b['suggested_target_ids']=[i for _,i in sorted(candidates,reverse=True)[:3]]
    return {'approved_batches':sum(b['approved_mapping'] is not None for b in batches),
        'total_rows':len(batches),'club_linked_rows':sum(b['club_target_id'] is not None for b in batches),
        'needs_review_rows':sum(b['approved_mapping'] is None for b in batches),
        'named_source_clubs':len({(b['center'],b.get('city')) for b in batches if b.get('center')})}


def save_mapping(path,batch,target,age,pairs,source_name,source_hash):
    if path is None:raise ValueError('Mapping persistence is not configured')
    value={'definition':definition(batch),'target':target_identity(target),'age':age or '',
        'proficiency_pairs':[] if batch['division'] in ('Open','Open Age') else pairs,
        'source_name':source_name,'source_hash':source_hash,
        'approved_at':datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(timespec='seconds')}
    with LOCK:
        store=read_store(path);store['batches'][source_key(batch,source_name)]=value
        key=club_key(batch)
        if key:store['clubs'][key]={'target':target_identity(target),'approved_at':value['approved_at']}
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(store,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(path)
