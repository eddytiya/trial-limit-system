import unittest
from datetime import date
from slot_thresholds import schedule,evaluate,read_capacity_csv,slot_snapshot
from unittest.mock import patch
from pathlib import Path
import csv
import io
import tempfile
from test_automatic_capacity import enrolled

MON=date(2026,10,19)
TARGET={'academy_id':'001','academy':' Academy ','center':'Center','sport':'Sport'}


def record(**changes):
    return {'row':3,'sport':'Sport','center':'Workbook Center','time':'6pm to 7pm',
        'days':'Monday to Friday','capacities':['16','12','12','12','12','NA','NA'],
        'reported_counts':['5']*7,'proficiency':['Open']*7,**changes}


def trial(**changes):
    return {'Academy':' Academy ','Coaching Center':'Center','Age Category':'U8',
        'Trial Scheduled Date':'2026-10-19','Start Time':'6:00 PM','End Time':'7:00 PM',
        'Status':'booked','Player Name':'Child A','Mobile number':'123',**changes}


class ThresholdTests(unittest.TestCase):
    def test_missing_centers_excluded_from_batches_targets_and_mapping_counts(self):
        payload={'reference_date':'2026-10-19','csv_text':'fixture','capacity_filename':'capacity.csv',
            'capacity_text':'Sport,Centre,Batch Time,Weekday,Total Capacity,Actual Capacity,Proficiency\nSport,,6pm to 7pm,Monday,10,1,Open\nSport,   ,7pm to 8pm,Monday,10,1,Open\nSport,Club,8pm to 9pm,Monday,10,1,Open\n'}
        with patch('slot_thresholds.read_source',return_value=([], 'fixture-hash')):
            r=slot_snapshot(payload,Path('absent.csv'),None,Path('absent.xlsx'))
        self.assertEqual(r['listed_source_rows'],3)
        self.assertEqual(r['excluded_missing_center_count'],2)
        self.assertEqual(len(r['excluded_rows']),2)
        self.assertEqual(len(r['batches']),1)
        self.assertEqual(r['mapping_summary']['total_rows'],1)
        self.assertEqual(r['batches'][0]['center'],'Club')

    def test_identical_center_names_in_different_cities_are_separate_pools(self):
        batches=schedule([record(city='City A'),record(row=4,city='City B')],MON)
        self.assertFalse(any(b['issues'] for b in batches))

    def test_approved_mapping_can_be_reused_and_changed_capacity_is_blocked(self):
        row=enrolled();stream=io.StringIO();w=csv.DictWriter(stream,fieldnames=list(row));w.writeheader();w.writerow(row)
        payload={'reference_date':'2026-10-19','csv_text':stream.getvalue(),'filename':'enrollment.csv',
            'capacity_filename':'schedule.csv','capacity_text':'Sport,Centre,CITY,Batch Time,Weekday,Total Capacity,Actual Capacity,Proficiency\nSport,Workbook Club,City,6pm to 7pm,Monday,4,1,Open\n',
            'trials_filename':'trials.csv','trials_text':'Academy,Coaching Center,Age Category,Trial Scheduled Date,Status\n'}
        absent=Path('absent.csv')
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            mapping_path=Path(folder)/'links.json'
            initial=slot_snapshot(payload,absent,absent,absent,mapping_path)
            saved=slot_snapshot({**payload,'batch_id':'2','target_id':'0','age':'','confirmed':True,
                'workbook_hash':initial['workbook_hash'],'mapping_action':'save'},absent,absent,absent,mapping_path)
            self.assertTrue(saved['mapping_saved'])
            self.assertEqual(saved['mapping_summary']['approved_batches'],1)
            calculated=slot_snapshot({**payload,'batch_id':'2','use_saved_mapping':True,
                'workbook_hash':initial['workbook_hash']},absent,absent,absent,mapping_path)
            self.assertEqual(calculated['result']['enrolled'],1)
            changed={**payload,'capacity_text':payload['capacity_text'].replace('Monday,4,1','Monday,5,1')}
            fresh=slot_snapshot(changed,absent,absent,absent,mapping_path)
            with self.assertRaisesRegex(ValueError,'no current approved mapping'):
                slot_snapshot({**changed,'batch_id':'2','use_saved_mapping':True,
                    'workbook_hash':fresh['workbook_hash']},absent,absent,absent,mapping_path)

    def test_distinct_proficiencies_same_time_are_separate(self):
        a=record(proficiency=['Beginner']*7)
        b=record(row=4,proficiency=['Intermediate']*7)
        pools=schedule([a,b],MON)
        self.assertFalse(any(p['issues'] for p in pools))
        self.assertEqual([p['division'] for p in pools],['Beginner','Intermediate'])
        self.assertTrue(all(p['issues'] for p in schedule([record(),b],MON)))

    def test_restricted_category_requires_explicit_membership(self):
        b=schedule([record(proficiency=['Beginner']*7)],MON)[0]
        with self.assertRaisesRegex(ValueError,'exact age/course'):
            evaluate(b,TARGET,None,[],[],MON)

    def test_combined_proficiency_shares_one_capacity_and_deduplicates(self):
        b=schedule([record(proficiency=['Beginner + Intermediate']*7,capacities=['3']*7)],MON)[0]
        students=[enrolled(**{'Course Name':'Beginner'}),enrolled(**{'Course Name':'Intermediate'}),
            enrolled(identifier='second',**{'Course Name':'Intermediate'}),
            enrolled(identifier='excluded',**{'Course Name':'Advanced'})]
        trials=[trial(**{'Player DB ID':'new','Course Details':'Beginner'}),
            trial(**{'Player DB ID':'other','Course Details':'Advanced'})]
        r=evaluate(b,TARGET,None,list(enumerate(students,2)),list(enumerate(trials,2)),MON,
            [['U8','Beginner'],['U8','Intermediate']])
        self.assertEqual(r['enrolled'],2)
        self.assertEqual(r['additional_trials'],1)
        self.assertEqual(r['status'],'Full')

    def test_child_and_adult_beginner_do_not_mix(self):
        rows=[enrolled(**{'Age Category':'Child','Course Name':'Beginner'}),
            enrolled(identifier='adult',**{'Age Category':'Adult','Course Name':'Beginner'})]
        for scope in ('Child','Adult'):
            b=schedule([record(proficiency=[scope+' Beginner']*7)],MON)[0]
            r=evaluate(b,TARGET,None,list(enumerate(rows,2)),[],MON,[[scope,'Beginner']])
            self.assertEqual(r['enrolled'],1)

    def test_open_has_no_proficiency_restriction(self):
        b=schedule([record()],MON)[0]
        rows=[enrolled(),enrolled(identifier='advanced',**{'Course Name':'Advanced'}),
            enrolled(identifier='missing',**{'Course Name':''})]
        r=evaluate(b,TARGET,None,list(enumerate(rows,2)),[],MON,[['U8','Regular']])
        self.assertEqual(r['enrolled'],3)
        self.assertEqual(r['proficiency_memberships'],[])

    def test_missing_or_differently_spaced_course_not_guessed(self):
        b=schedule([record(proficiency=['Beginner']*7)],MON)[0]
        rows=[enrolled(**{'Course Name':'Beginner '}),enrolled(identifier='missing',**{'Course Name':''})]
        r=evaluate(b,TARGET,None,list(enumerate(rows,2)),[],MON,[['U8','Beginner']])
        self.assertEqual(r['enrolled'],0)
        self.assertEqual(r['completeness'],'Incomplete')
        self.assertIsNone(r['confirmed_total'])

    def test_missing_proficiency_definition_is_flagged(self):
        b=schedule([record(proficiency=['']*7)],MON)[0]
        self.assertIn('Missing Proficiency', '; '.join(b['issues']))

    def test_all_three_csv_uploads_used_without_local_files(self):
        rows=[enrolled()]
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        payload={'reference_date':'2026-10-19','filename':'new_enrollment.csv','csv_text':stream.getvalue(),
            'trials_filename':'new_trials.csv',
            'trials_text':'Academy,Coaching Center,Age Category,Trial Scheduled Date,Status,Start Time,End Time,Player DB ID\n Academy ,Center,U8,2026-10-19,booked,6:00 PM,7:00 PM,new-child\n',
            'capacity_filename':'new_capacities.csv',
            'capacity_text':'Sport,Centre,Batch Time,Weekday,Total Capacity,Actual Capacity,Proficiency\nSport,Workbook Center,6pm to 7pm,Monday,2,1,Open\n'}
        absent=Path('never-read-local-file.csv')
        first=slot_snapshot(payload,absent,absent,absent)
        result=slot_snapshot({**payload,'batch_id':'2','target_id':'0','age':'U8',
            'confirmed':True,'workbook_hash':first['workbook_hash']},absent,absent,absent)
        self.assertEqual(result['enrollment_source'],'new_enrollment.csv')
        self.assertEqual(result['trial_source'],'new_trials.csv')
        self.assertTrue(result['enrollment_uploaded_snapshot'])
        self.assertTrue(result['trial_uploaded_snapshot'])
        self.assertEqual(result['result']['confirmed_total'],2)
        self.assertEqual(result['result']['status'],'Full')

    def test_simple_csv_keeps_labels_and_separates_weekdays(self):
        text='Sport,Centre,Batch Time,Weekday,Total Capacity,Actual Capacity,Proficiency\nSport, Center ,6pm to 7pm,Monday,2,3,U8\nSport, Center ,6pm to 7pm,Tuesday,4,4,U8\n'
        records,_=read_capacity_csv(text.encode())
        monday=schedule(records,MON)
        self.assertEqual(len(monday),1)
        self.assertEqual(monday[0]['center'],' Center ')
        self.assertEqual(monday[0]['reference_status'],'Over Capacity')
        self.assertEqual(monday[0]['reference_excess'],1)
        self.assertEqual(schedule(records,date(2026,10,20))[0]['reference_status'],'Full')

    def test_main_csv_export(self):
        stream=io.StringIO();writer=csv.writer(stream)
        writer.writerow(['']*4+[v for day in ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday') for v in (day,'','')])
        writer.writerow(['Sport','Centre','Batch Time','Days']+['Total Capacity','Proficiency','Actual Capacity']*7)
        writer.writerow(['Sport','Center','6pm to 7pm','Monday to Friday']+['12','Open','3']*7)
        records,_=read_capacity_csv(stream.getvalue().encode())
        self.assertEqual(schedule(records,MON)[0]['capacity'],12)
        with self.assertRaisesRegex(ValueError,'weekday headers'):
            read_capacity_csv(stream.getvalue().replace('Monday,','Friday,',1).encode())

    def test_upload_replacement_ignores_local_capacity_and_changes_classifier(self):
        text='Sport,Centre,Batch Time,Weekday,Total Capacity,Actual Capacity,Proficiency\nSport,Center,6pm to 7pm,Monday,2,3,Open\n'
        payload={'reference_date':'2026-10-19','capacity_filename':'uploaded.csv','capacity_text':text}
        with patch('slot_thresholds.read_source',return_value=([], 'uploaded-enrollment-hash')):
            # csv_text avoids local enrollment checks; all capacity data is in memory.
            payload['csv_text']='in-memory fixture'
            first=slot_snapshot(payload,Path('never-written.csv'),None,Path('absent.xlsx'))
            second=slot_snapshot({**payload,'capacity_text':text.replace('Monday,2,3','Monday,5,3')},Path('never-written.csv'),None,Path('absent.xlsx'))
        self.assertEqual(first['batches'][0]['reference_status'],'Over Capacity')
        self.assertEqual(second['batches'][0]['reference_status'],'Available')
        self.assertNotEqual(first['workbook_hash'],second['workbook_hash'])
        self.assertTrue(first['capacity_uploaded_snapshot'])

    def test_invalid_capacity_and_missing_reported_count_not_available(self):
        missing=schedule([record(reported_counts=['']*7)],MON)[0]
        self.assertEqual(missing['reference_status'],'Count not supplied')
        invalid=schedule([record(capacities=['1.5']*7)],MON)[0]
        self.assertEqual(invalid['reference_status'],'Needs review')
        self.assertIsNone(invalid['reference_remaining'])

    def calc(self,students,trials,age='U8',capacity=2):
        batch=schedule([record(capacities=[str(capacity)]*7)],MON)[0]
        return evaluate(batch,TARGET,age,list(enumerate(students,2)),
            None if trials is None else list(enumerate(trials,2)),MON)

    def test_weekday_threshold_uses_total_not_actual(self):
        monday=schedule([record()],MON)[0]
        tuesday=schedule([record()],date(2026,10,20))[0]
        self.assertEqual(monday['capacity'],16)
        self.assertEqual(monday['workbook_reported_count'],5)
        self.assertEqual(tuesday['capacity'],12)
        self.assertEqual(schedule([record()],date(2026,10,24)),[])

    def test_missing_capacity_has_no_default_and_zero_is_valid(self):
        b=schedule([record(capacities=['']*7)],MON)[0]
        self.assertIsNone(b['capacity']);self.assertTrue(b['issues'])
        self.assertEqual(schedule([record(capacities=['0']*7)],MON)[0]['capacity'],0)

    def test_duplicate_schedule_rows_are_not_independent_pools(self):
        self.assertTrue(all(b['issues'] for b in schedule([record(),record(row=4)],MON)))

    def test_inclusive_dates_exact_slots_and_unique_students(self):
        rows=[enrolled(),enrolled(),enrolled(identifier='other',Slots='Tuesday 6:00 PM - 7:00 PM'),
            enrolled(identifier='later',**{'Start Date':'2026-10-20'}),
            enrolled(identifier='ended',**{'End Date':'2026-10-18'})]
        r=self.calc(rows,[])
        self.assertEqual(r['enrolled'],1)
        self.assertEqual(r['confirmed_total'],1)

    def test_shared_id_overlap_and_capacity_boundaries(self):
        for capacity,expected in [(3,'Available'),(2,'Full'),(1,'Over Capacity')]:
            r=self.calc([enrolled()], [trial(**{'Player DB ID':'p1'}),
                trial(**{'Player DB ID':'new'}),trial(**{'Player DB ID':'new'})],capacity=capacity)
            self.assertEqual(r['confirmed_total'],2)
            self.assertEqual(r['status'],expected)
            self.assertEqual(r['already_enrolled_excluded'],1)
            self.assertEqual(r['duplicates_excluded'],1)

    def test_provisional_matching_respects_slot_and_date(self):
        r=self.calc([enrolled()],[trial(),trial(),trial(**{'Trial Scheduled Date':'2026-10-20'}),
            trial(**{'Start Time':'7:00 PM','End Time':'8:00 PM'})])
        self.assertEqual(r['booked_rows'],2)
        self.assertEqual(r['duplicates_excluded'],1)
        self.assertEqual(r['preview'],2)
        self.assertIsNone(r['confirmed_total'])

    def test_missing_slots_cannot_become_zero_confirmed(self):
        r=self.calc([enrolled(Slots='')],[])
        self.assertEqual(r['completeness'],'Incomplete')
        self.assertIsNone(r['confirmed_total'])

    def test_open_combines_all_ages_but_keeps_centers_separate(self):
        rows=[enrolled(),enrolled(identifier='u10',**{'Age Category':'U10'}),
            enrolled(identifier='other',**{'Coaching Center Location':'Other'})]
        self.assertEqual(self.calc(rows,[])['enrolled'],2)
        self.assertEqual(self.calc(rows,[],age=None)['enrolled'],2)

    def test_missing_trial_source_and_ambiguous_sport_are_unconfirmed(self):
        self.assertIsNone(self.calc([enrolled()],None)['confirmed_total'])
        r=self.calc([enrolled(),enrolled(Sports='Other sport')],[trial()])
        self.assertEqual(r['completeness'],'Incomplete')
        self.assertEqual(r['booked_rows'],0)


if __name__=='__main__':unittest.main()
