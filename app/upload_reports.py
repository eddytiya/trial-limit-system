"""Write immutable diagnostic reports outside read-only input files."""
import hashlib
import json
import threading
from collections import defaultdict
from pathlib import Path

LOCK=threading.Lock()

def write_upload_report(snapshot, report_root):
    validation=snapshot.get('validation',{})
    issues=validation.get('issues',[])
    metadata={k:snapshot.get(k) for k in ('reference_date','weekday','enrollment_source','trial_source','capacity_source','enrollment_hash','trial_hash','workbook_hash')}
    content={'sources':metadata,'validation':validation,'calculation':snapshot.get('result')}
    raw=json.dumps(content,ensure_ascii=False,sort_keys=True,indent=2)
    identity=hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]
    folder=Path(report_root)/(snapshot['reference_date']+'_'+identity)
    grouped=defaultdict(list)
    for issue in issues:
        reason=issue['reason']
        if reason.startswith('Non-booked status requires review:'):reason='Non-booked status requires review'
        grouped[(issue['source'],reason)].append(issue)
    def safe(value):return str(value or '').replace('|','\\|').replace('\n',' ')
    lines=['# Upload validation report','',f"Analysis date: {snapshot['reference_date']}",'',
           'Source files were read only. No input files or approval records were modified.',
           '','## Sources','', '| Source | Filename | SHA-256 |','| --- | --- | --- |']
    for label,name,digest in [('Enrollment','enrollment_source','enrollment_hash'),('Trials','trial_source','trial_hash'),('Capacity','capacity_source','workbook_hash')]:
        lines.append(f'| {label} | {safe(metadata[name])} | {safe(metadata[digest])} |')
    lines+=['','## Validation summary','',f"Enrollment rows: {validation.get('enrollment_rows')}. Trial rows: {validation.get('trial_rows')}. Issue entries: {len(issues)}.",
            '',validation.get('scope',''),'','One row can appear in several groups; grouped counts must not be added as unique students.',
            '','| Source | Issue | Affected rows | Entries |','| --- | --- | ---: | ---: |']
    for (source,reason),entries in sorted(grouped.items(),key=lambda item:(-len({i['row'] for i in item[1]}),item[0])):
        lines.append(f'| {safe(source)} | {safe(reason)} | {len({i["row"] for i in entries})} | {len(entries)} |')
    if not issues:lines+=['','No upload issues detected.']
    if snapshot.get('result') is not None:
        lines+=['','## Selected batch calculation','','```json',json.dumps(snapshot['result'],ensure_ascii=False,indent=2),'```']
    lines+=['','Full source-row details are in details.json. Counts reflect uploaded snapshots, not live attendance.','']
    with LOCK:
        folder.mkdir(parents=True,exist_ok=True)
        if not (folder/'report.md').exists():
            (folder/'details.json').write_text(raw,encoding='utf-8')
            (folder/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    return {'folder':str(folder.resolve()),'report':str((folder/'report.md').resolve()),'issue_count':len(issues)}
