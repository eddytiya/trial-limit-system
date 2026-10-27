import unittest
import io
import zipfile
from pathlib import Path
from datetime import date
from automatic_capacity import analyze_center_batches,automatic_snapshot
from raw_trial_source import combine_raw_trials,read_trial_xlsx,read_raw_trial_csv
from test_automatic_capacity import enrolled

REF=date(2026,10,19)


def raw(**changes):
    return {'Academy':' Academy ','Coaching Center':'Center','Age Category':'U8',
            'Trial Scheduled Date':'2026-10-19','Status':'booked',**changes}


class RawTrialTests(unittest.TestCase):
    def test_exact_name_mobile_provisional_duplicates(self):
        person={'Player Name':'Child A','Mobile number':'123'}
        batches,issues,info=self.combine([raw(**person),raw(**person),
            raw(**{**person,'Player Name':'Child B'}),
            raw(**{**person,'Player Name':'Child A '}),raw(),raw()])
        self.assertEqual(batches[0]['Booked trial rows'],6)
        self.assertEqual(batches[0]['Provisional trial students'],5)
        self.assertEqual(batches[0]['Duplicate trial rows excluded'],1)
        self.assertEqual(batches[0]['Enrolled plus booked rows preview'],6)
        self.assertIsNone(batches[0]['Total occupancy'])
        self.assertEqual(info['matched_trial_rows_after_dedup'],5)
        self.assertTrue(any('duplicate of source row' in q['Reason'] for q in issues))

    def test_name_mobile_matching_does_not_cross_groups_or_dates(self):
        person={'Player Name':'Child A','Mobile number':'123'}
        batches,_,info=self.combine([raw(**person),raw(**{**person,'Age Category':'U10'}),
            raw(**{**person,'Trial Scheduled Date':'2026-10-20'})])
        self.assertEqual(info['duplicate_trial_rows_excluded'],0)
        self.assertEqual(info['matched_trial_rows_after_dedup'],2)

    def test_shared_ids_only_trials_on_selected_date_contribute(self):
        batches,_,info=self.combine([
            raw(**{'Player DB ID':'today'}),
            raw(**{'Player DB ID':'tomorrow','Trial Scheduled Date':'2026-10-20'}),
            raw(**{'Player DB ID':'yesterday','Trial Scheduled Date':'2026-10-18'})])
        self.assertEqual(batches[0]['Total occupancy'],2)
        self.assertEqual(info['booked_rows_on_date'],1)

    def test_shared_ids_separate_centers_and_sports(self):
        enrollments=[enrolled(),enrolled(identifier='other',Sports='Tennis',
            **{'Academy Name':'Tennis Academy','Academy ID':'tennis-academy'})]
        batches,_,_=self.combine([
            raw(**{'Player DB ID':'p1','Coaching Center':'Other Center'}),
            raw(**{'Player DB ID':'p1','Academy':'Tennis Academy'})],enrollments)
        other=next(b for b in batches if b['Coaching Center Location']=='Other Center')
        tennis=next(b for b in batches if b['Sports']=='Tennis')
        self.assertEqual(other['Trial students'],1)
        self.assertEqual(tennis['Trial students'],1)
        self.assertEqual(tennis['Total occupancy'],2)

    def test_shared_ids_deduplicate_trials_and_remove_enrollment_overlap(self):
        batches,issues,info=self.combine([raw(**{'Player DB ID':'p1'}),raw(**{'Player DB ID':'p1'}),
                                         raw(**{'Player DB ID':'trial-child'}),raw(**{'Player DB ID':'trial-child'})])
        b=batches[0]
        self.assertEqual(b['Unique enrolled students'],1)
        self.assertEqual(b['Booked trial rows'],4)
        self.assertEqual(b['Unique booked trial students identified'],2)
        self.assertEqual(b['Trial students already enrolled'],1)
        self.assertEqual(b['Trial students'],1)
        self.assertEqual(b['Total occupancy'],2)
        self.assertTrue(info['unique_trial_students_confirmed'])
        self.assertFalse(issues)

    def test_same_id_in_other_group_not_removed(self):
        batches,issues,info=self.combine([raw(**{'Player DB ID':'p1','Age Category':'U10'})])
        b=next(b for b in batches if b['Age Category']=='U10')
        self.assertEqual(b['Trial students'],1)
        self.assertEqual(b['Trial students already enrolled'],0)

    def test_expired_enrollment_does_not_remove_trial(self):
        batches,_,_=self.combine([raw(**{'Player DB ID':'p1'})],
                                 [enrolled(**{'End Date':'2026-10-18'})])
        self.assertEqual(batches[0]['Unique enrolled students'],0)
        self.assertEqual(batches[0]['Trial students'],1)

    def test_partial_shared_ids_withhold_confirmed_total(self):
        b,q,info=self.combine([raw(**{'Player DB ID':'trial-child'}),raw(**{'Player DB ID':''})])
        self.assertEqual(b[0]['Known additional trial students'],1)
        self.assertIsNone(b[0]['Total occupancy'])
        self.assertFalse(info['unique_trial_students_confirmed'])
        self.assertIn('Missing shared Player DB ID',q[0]['Reason'])

    def test_ids_are_exact_and_not_replaced_by_names_or_mobile(self):
        b,_,_=self.combine([raw(**{'Player DB ID':'p1 ','Player Name':'Same name','Mobile number':'111'})])
        self.assertEqual(b[0]['Trial students'],1)
        self.assertEqual(b[0]['Trial students already enrolled'],0)

    def test_old_xlsx_text_upload_has_refresh_instructions(self):
        with self.assertRaisesRegex(ValueError,'Ctrl\\+Shift\\+R'):
            automatic_snapshot({'trials_text':'binary decoded as text','trials_filename':'trial.xlsx'},Path('unused'),None)

    def test_original_raw_csv_headers_supported(self):
        text='Academy,Coaching Center,Age Category,Trial Scheduled Date,Status\n Academy ,Center,U8,2026-10-19,booked\n'
        rows,_=read_raw_trial_csv(Path('unused.csv'),text)
        self.assertEqual(rows[0][1]['Academy'],' Academy ')
        self.assertEqual(rows[0][1]['Status'],'booked')

    def combine(self,records,enrollments=None):
        rows=list(enumerate(enrollments if enrollments is not None else [enrolled()],2))
        batches,_=analyze_center_batches(rows,None,REF,10)
        return combine_raw_trials(batches,rows,list(enumerate(records,2)),REF,10,'booked_only')

    def test_booked_preview_not_unique_students(self):
        batches,issues,info=self.combine([raw(),raw()])
        b=batches[0]
        self.assertEqual(b['Booked trial rows'],2)
        self.assertEqual(b['Enrolled plus booked rows preview'],3)
        self.assertIsNone(b['Trial students']);self.assertIsNone(b['Total occupancy'])
        self.assertEqual(b['Booking assessment'],'Approval withheld')
        self.assertEqual(len(issues),2)
        self.assertEqual(info['matched_booked_rows'],2)

    def test_status_and_selected_date(self):
        b,issues,info=self.combine([raw(),raw(Status='attended'),raw(Status='rescheduled'),
                                  raw(**{'Trial Scheduled Date':'2026-10-20'})])
        self.assertEqual(b[0]['Booked trial rows'],1)
        self.assertEqual(info['selected_date_statuses'],{'booked':1,'attended':1,'rescheduled':1})
        self.assertEqual(len(issues),3)

    def test_missing_age_not_guessed(self):
        b,q,info=self.combine([raw(**{'Age Category':''})])
        self.assertEqual(info['booked_rows_on_date'],1)
        self.assertEqual(info['matched_booked_rows'],0)
        self.assertEqual(b[0]['Data completeness'],'Incomplete')
        self.assertIn('Missing Age Category',q[0]['Reason'])

    def test_ambiguous_academy_sport_not_merged(self):
        records=[enrolled(),enrolled(Sports='Different Sport')]
        b,q,info=self.combine([raw()],records)
        self.assertEqual(info['matched_booked_rows'],0)
        self.assertTrue(all(x['Booked trial rows']==0 for x in b))
        self.assertIn('cannot be matched',q[0]['Reason'])

    def test_exact_center_and_academy_values_preserved(self):
        b,q,info=self.combine([raw(**{'Coaching Center':'Center '})])
        target=next(x for x in b if x['Coaching Center Location']=='Center ')
        self.assertEqual(target['Unique enrolled students'],0)
        self.assertEqual(target['Booked trial rows'],1)

    def test_rescheduled_effective_date_unresolved(self):
        b,q,info=self.combine([raw(**{'Trial Scheduled Date':'2026-10-18',
                                     'Rescheduled Date & Time':'2026-10-19 18:00'})])
        self.assertEqual(info['booked_rows_on_date'],0)
        self.assertEqual(b[0]['Data completeness'],'Incomplete')
        self.assertIn('rescheduling rule',q[0]['Reason'])

    def test_xlsx_reader_is_read_only_and_keeps_original_headers(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Query result" sheetId="1" r:id="rId1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            headers=['Academy','Coaching Center','Age Category','Trial Scheduled Date','Status']
            def row(number,values):
                return '<row r="'+str(number)+'">'+''.join(f'<c r="{chr(65+i)}{number}" t="inlineStr"><is><t>{value}</t></is></c>' for i,value in enumerate(values))+'</row>'
            z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+row(1,headers)+row(2,[' Academy ','Center','U8','2026-10-19','booked'])+'</sheetData></worksheet>')
        content=stream.getvalue()
        rows,digest=read_trial_xlsx(Path('never-written.xlsx'),content)
        self.assertEqual(rows[0][1]['Academy'],' Academy ')
        self.assertEqual(rows[0][0],2)
        self.assertEqual(stream.getvalue(),content)


if __name__=='__main__':unittest.main()
