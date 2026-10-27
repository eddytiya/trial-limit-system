import unittest
from unittest.mock import patch
import csv
import io
from pathlib import Path
from datetime import date
from slot_thresholds import evaluate, schedule
from upload_validation import validate_uploads, TEMPLATES
from test_slot_thresholds import record, trial, TARGET
from test_automatic_capacity import enrolled

class UploadWorkflowTests(unittest.TestCase):
    def test_reports_group_rows_and_reuse_identical_snapshots(self):
        import tempfile
        from upload_reports import write_upload_report
        snapshot={'reference_date':'2026-10-27','validation':{'issues':[
            {'source':'Trials','row':2,'reason':'Missing ID'},
            {'source':'Trials','row':2,'reason':'Missing ID'},
            {'source':'Trials','row':3,'reason':'Missing ID'}]}}
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            report=write_upload_report(snapshot,folder)
            text=Path(report['report']).read_text(encoding='utf-8')
            self.assertIn('| Trials | Missing ID | 2 | 3 |',text)
            self.assertTrue((Path(report['folder'])/'details.json').exists())
            self.assertEqual(report,write_upload_report(snapshot,folder))
            changed={**snapshot,'result':{'confirmed_total':None,'status':'Not confirmed'}}
            self.assertNotEqual(report['folder'],write_upload_report(changed,folder)['folder'])

    def test_original_export_dates_are_read_without_rewriting(self):
        from trial_limit import eligible, RULE, enrollment_date
        row=enrolled(**{'Start Date':'01-10-2026','End Date':'19-10-2026'})
        original=dict(row)
        self.assertTrue(eligible(row,date(2026,10,19),RULE))
        self.assertFalse(eligible(row,date(2026,10,20),RULE))
        self.assertEqual(row,original)
        for raw in ('10/01/2026','31-02-2026','2026-02-31'):
            with self.assertRaises(ValueError):enrollment_date(raw)
    def test_template_download_handlers_without_network(self):
        import frontend
        responses=[]
        class Server:
            def __init__(self,address,handler):self.handler=handler
            def serve_forever(self):
                for name,fields in TEMPLATES.items():
                    handler=object.__new__(self.handler)
                    handler.path='/templates/'+name+'.csv'
                    handler.send=lambda status,content,kind:responses.append((status,content,kind))
                    handler.do_GET()
                    status,content,kind=responses[-1]
                    self_check=list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
                    assert status==200 and self_check==[fields] and kind.startswith('text/csv')
            def server_close(self):pass
        with patch('frontend.ThreadingHTTPServer',Server),patch('sys.argv',['frontend.py']):
            frontend.main()
        self.assertEqual(len(responses),3)

    def batch(self):
        return schedule([record(capacities=['2']*7)],date(2026,10,19))[0]

    def test_unique_students_overlap_and_over_capacity(self):
        r=evaluate(self.batch(),TARGET,None,list(enumerate([enrolled(),enrolled()],2)),
            list(enumerate([trial(**{'Player DB ID':'p1'}),trial(**{'Player DB ID':'new'}),
                            trial(**{'Player DB ID':'new'}),trial(**{'Player DB ID':'third'})],2)),date(2026,10,19))
        self.assertEqual((r['enrolled'],r['additional_trials'],r['duplicates_excluded'],r['already_enrolled_excluded']),(1,2,1,1))
        self.assertEqual((r['confirmed_total'],r['remaining'],r['status']),(3,0,'Over Capacity'))

    def test_missing_ids_withhold_remaining(self):
        r=evaluate(self.batch(),TARGET,None,[(2,enrolled())],[(2,trial())],date(2026,10,19))
        self.assertIsNone(r['confirmed_total']);self.assertIsNone(r['remaining'])

    def test_conflicting_booking_and_cancelled(self):
        rows=[(2,trial(**{'Trial Booking ID':'b','Player DB ID':'new'})),
              (3,trial(**{'Trial Booking ID':'b','Player DB ID':'new','Status':'cancelled'}))]
        r=evaluate(self.batch(),TARGET,None,[(2,enrolled())],rows,date(2026,10,19))
        self.assertIsNone(r['confirmed_total']);self.assertTrue(any('Conflicting' in i['reason'] for i in r['issues']))
        r=evaluate(self.batch(),TARGET,None,[(2,enrolled())],[rows[1]],date(2026,10,19))
        self.assertEqual(r['confirmed_total'],1)

    def test_diagnostics_report_duplicates_dates_unmatched_and_ids(self):
        e=enrolled(**{'Start Date':'invalid'})
        t=trial(**{'Academy':'unknown','Trial Scheduled Date':'invalid'})
        report=validate_uploads([(2,e),(3,e)],[(2,t)],[self.batch()])
        reasons=' '.join(i['reason'] for i in report['issues'])
        for word in ('Duplicate','dates','Unmatched','Player DB ID','mapping'):
            self.assertIn(word,reasons)
        self.assertTrue(report['read_only'])
        self.assertIn('Slots',TEMPLATES['enrollment'])

if __name__=='__main__':unittest.main()
