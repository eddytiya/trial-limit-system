"""Local UI. Run: python frontend.py"""
import argparse
import csv
import hashlib
import io
import json
import zipfile
from xml.etree.ElementTree import ParseError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from datetime import date
from trial_limit import GROUP_FIELDS, RULE, analyze, load, nonnegative, result, today, can_book
from session_capacity import analyze_sessions, session_result
from workbook_capacity import read_main, catalog, enrollment_targets, check_batch
from automatic_capacity import automatic_snapshot
from slot_thresholds import slot_snapshot

from app_paths import APP_DIR, INPUT_DIR, MAPPED_DIR, project_path

ROOT = APP_DIR


def workbook_calculate(payload, default_source, capacity_source):
    reference = date.fromisoformat(payload.get('reference_date') or today().isoformat())
    capacity = nonnegative(json.loads((ROOT/'config.json').read_text())['capacity'])
    if not capacity:
        raise ValueError('Capacity must be positive')
    if 'csv_text' in payload:
        reader = csv.DictReader(io.StringIO(payload['csv_text'].lstrip('\ufeff'), newline=''))
        from trial_limit import REQUIRED
        missing = set((*REQUIRED,'Slots'))-set(reader.fieldnames or [])
        if missing:
            raise ValueError('Missing columns: '+', '.join(sorted(missing)))
        rows=[]
        while True:
            line=reader.line_num+1
            try:
                row=next(reader)
            except StopIteration:
                break
            rows.append((line,row))
        csv_digest=hashlib.sha256(payload['csv_text'].encode()).hexdigest()
    else:
        rows,csv_digest=load(default_source)
    records,workbook_digest=read_main(capacity_source)
    if payload.get('workbook_digest') and payload['workbook_digest'] != workbook_digest:
        raise ValueError('Workbook was updated by its owner. Reload schedules and confirm the link again.')
    batches,quality=catalog(records,reference)
    targets=enrollment_targets(rows)
    output=None
    if payload.get('batch_id'):
        batch=next((b for b in batches if b['id']==payload['batch_id']),None)
        if batch is None:
            raise ValueError('Batch is no longer available for this date; reload schedules')
        target=next((t for t in targets if t['id']==payload.get('target_id')),None)
        age=payload.get('age')
        course=payload.get('course') or None
        if target and (age not in target['ages'] or course is not None and course not in target['ages'][age]):
            raise ValueError('Select an existing exact CSV age/course')
        output=check_batch(batch,rows,reference,capacity,target,age,course,
                           payload.get('confirmed') is True,payload.get('trials'),payload.get('proposed'))
        quality.extend(output['issues'])
    if 'csv_text' not in payload and hashlib.sha256(default_source.read_bytes()).hexdigest()!=csv_digest:
        raise ValueError('Enrollment CSV changed while reading; reload')
    if hashlib.sha256(capacity_source.read_bytes()).hexdigest()!=workbook_digest:
        raise ValueError('Capacity workbook changed while calculating; reload')
    return {'batches':batches,'targets':targets,'result':output,'quality':quality,
            'source':payload.get('filename',default_source.name),'capacity_source':capacity_source.name,
            'workbook_digest':workbook_digest,'csv_digest':csv_digest,
            'reference_date':reference.isoformat(),'capacity':capacity,'record_count':len(rows)}


def calculate(payload, default_source):
    reference = date.fromisoformat(payload.get('reference_date') or today().isoformat())
    capacity = nonnegative(json.loads((ROOT/'config.json').read_text())['capacity'])
    if not capacity:
        raise ValueError('Capacity must be positive')
    if 'csv_text' in payload:
        reader = csv.DictReader(io.StringIO(payload['csv_text'], newline=''))
        from trial_limit import REQUIRED
        missing = set(REQUIRED) - set(reader.fieldnames or [])
        if missing:
            raise ValueError('Missing columns: ' + ', '.join(sorted(missing)))
        rows = []
        while True:
            line = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            rows.append((line, row))
        integrity = 'Uploaded file read in memory; original file is never written.'
    else:
        rows, digest = load(default_source)
        integrity = 'Source SHA-256 unchanged: ' + digest
    if rows and 'Slots' not in rows[0][1]:
        raise ValueError('Missing columns: Slots')
    groups, issues, labels = analyze_sessions(rows, reference)
    if 'csv_text' not in payload and hashlib.sha256(default_source.read_bytes()).hexdigest() != digest:
        raise ValueError('Source file changed during processing')
    selected = payload.get('group_index')
    decision = None
    if selected is not None:
        selected = nonnegative(selected)
        if selected >= len(groups):
            raise ValueError('Select an existing capacity group')
        group = groups[selected]
        if payload.get('trials') is not None:
            group.trials = nonnegative(payload['trials'])
        if payload.get('proposed') is not None:
            decision = can_book(group, payload['proposed'], capacity)
    return {'groups': [session_result(g, reference, capacity, labels) for g in groups], 'issues': issues,
            'decision': decision, 'reference_date': reference.isoformat(),
            'source': payload.get('filename', default_source.name), 'integrity': integrity,
            'fields': [*GROUP_FIELDS, 'Session slot'], 'record_count': len(rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv-path', type=Path)
    parser.add_argument('--capacity-path', type=Path, default=INPUT_DIR/'Greenfield Batch & Coach details(reference for the batch timings).xlsx')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--trials-path', type=Path,
                        help='Optional read-only trial CSV or TechOps raw XLSX')
    args = parser.parse_args()
    settings=json.loads((ROOT/'config.json').read_text())
    args.trials_path=args.trials_path or project_path(settings.get('trial_source') or INPUT_DIR/'trial_bookings.csv')
    sources = sorted(p for p in INPUT_DIR.glob('*.csv') if p.resolve()!=args.trials_path.resolve())
    source = args.csv_path or (project_path(settings['enrollment_source']) if settings.get('enrollment_source') else sources[0] if sources else INPUT_DIR/'enrollment.csv')

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, content, kind):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if self.path == '/upload_workflow.js':
                self.send(200,(ROOT/'upload_workflow.js').read_bytes(),'text/javascript; charset=utf-8');return
            if urlsplit(self.path).path.startswith('/templates/'):
                from upload_validation import TEMPLATES
                name=urlsplit(self.path).path.rsplit('/',1)[-1].removesuffix('.csv')
                if name not in TEMPLATES:
                    self.send(404,b'Unknown template','text/plain');return
                stream=io.StringIO(newline='')
                csv.writer(stream).writerow(TEMPLATES[name])
                self.send(200,stream.getvalue().encode('utf-8-sig'),'text/csv; charset=utf-8');return
            if urlsplit(self.path).path in ('/', '/schedule'):
                self.send(200, (ROOT/'inventory.html').read_bytes(), 'text/html; charset=utf-8')
            elif urlsplit(self.path).path == '/admin':
                self.send(200, (ROOT/'inventory.html').read_bytes(), 'text/html; charset=utf-8')
            elif urlsplit(self.path).path == '/overview':
                self.send(200, (ROOT/'inventory.html').read_bytes(), 'text/html; charset=utf-8')
            elif self.path == '/favicon.ico':
                self.send(204,b'','image/x-icon')
            elif self.path == '/api/info':
                self.send(200, json.dumps({'date': today().isoformat()}).encode(), 'application/json')
            else:
                self.send(404, b'Not found', 'text/plain')

        def do_POST(self):
            if self.path not in ('/api/calculate','/api/workbook','/api/automatic','/api/schedule'):
                self.send(404, b'Not found', 'text/plain')
                return
            # Only this local frontend may initiate calculation requests.
            if self.headers.get('Origin') not in (None, f'http://localhost:{args.port}', f'http://127.0.0.1:{args.port}'):
                self.send(403, b'Forbidden origin', 'text/plain')
                return
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 30_000_000:
                    raise ValueError('Request must be between 1 byte and 30 MB')
                payload = json.loads(self.rfile.read(length))
                if self.path=='/api/schedule':
                    current_settings=json.loads((ROOT/'config.json').read_text())
                    response=slot_snapshot(payload,source,args.trials_path,
                        project_path(current_settings.get('slot_capacity_source') or args.capacity_path),MAPPED_DIR/'approved_batch_mappings.json')
                elif self.path=='/api/automatic':
                    current_settings=json.loads((ROOT/'config.json').read_text())
                    response=automatic_snapshot(payload,source,args.trials_path,
                        nonnegative(current_settings['capacity']),current_settings.get('raw_trial_status_rule','pending'))
                else:
                    response = (workbook_calculate(payload,source,args.capacity_path)
                                if self.path == '/api/workbook' else calculate(payload, source))
                if self.path=='/api/schedule':
                    from upload_reports import write_upload_report
                    response['validation_report']=write_upload_report(response,ROOT.parent/'reports')
                    response.pop('validation',None)
                self.send(200, json.dumps(response, ensure_ascii=False).encode(), 'application/json')
            except (ValueError, OSError, csv.Error, KeyError, TypeError, zipfile.BadZipFile, ParseError) as exc:
                self.send(400, json.dumps({'error': str(exc)}).encode(), 'application/json')

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Trial Limit dashboard: http://127.0.0.1:{args.port}', flush=True)
    print('Keep this terminal open. Press Ctrl+C to stop.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
