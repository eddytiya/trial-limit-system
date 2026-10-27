import unittest
from datetime import date
from unittest.mock import patch
from pathlib import Path
from workbook_capacity import catalog, check_batch, enrollment_targets, minutes, time_range, weekdays, divisions
from frontend import workbook_calculate
from test_trial_limit import row

SAT=date(2026,10,17)


def schedule(**changes):
    return {'row':133,'sport':'Football','center':'Reference Center','center_cell':'E133',
            'time':'6 pm to 7 pm','days':'Sat (U6, U8)','proficiency':[None]*7,**changes}


def student(**changes):
    return {**row(), 'Sports':'Football','Coaching Center Location':' CSV Center ',
            'Slots':'Saturday 6:00 PM - 7:00 PM', **changes}


class WorkbookTests(unittest.TestCase):
    def setUp(self):
        self.batches,_=catalog([schedule()],SAT)

    def evaluate(self,records,age='U8',trials='0',proposed='0',confirmed=True,batch=None,course=None):
        rows=list(enumerate(records,2))
        target=enrollment_targets(rows)[0]
        return check_batch(batch or self.batches[1],rows,SAT,100,target,age,course,confirmed,trials,proposed)

    def test_explicit_split(self):
        self.assertEqual([b['age'] for b in self.batches],['U6','U8'])
        self.assertFalse(self.batches[1]['issues'])
        self.assertEqual(weekdays('Monday to Friday'),[0,1,2,3,4])
        self.assertEqual(weekdays('Tues, Thurs & Fri (U8)'),[1,3,4])
        self.assertEqual(time_range('6 pm to 7 pm'),(1080,1140))
        self.assertEqual(time_range('5.30pm to 7.00pm'),(1050,1140))

    def test_ages_independent_and_unique_across_courses(self):
        records=[student(**{'Age Category':'U8','Player DB ID':str(i)}) for i in range(95)]
        records += [student(**{'Age Category':'U10','Player DB ID':'other'+str(i)}) for i in range(90)]
        records += [student(**{'Age Category':'U8','Player DB ID':'0','Course Name':'Advanced'})]
        result=self.evaluate(records,trials='5',proposed='0')
        self.assertEqual(result['Unique enrolled students'],95)
        self.assertEqual(result['Capacity status'],'Full')
        self.assertTrue(result['Booking allowed'])
        ten=catalog([schedule(days='Sat (U10)')],SAT)[0][0]
        result=self.evaluate(records,age='U10',batch=ten,trials='5',proposed='5')
        self.assertEqual(result['Unique enrolled students'],90)
        self.assertTrue(result['Booking allowed'])

    def test_thresholds(self):
        available=[student(**{'Age Category':'U8','Player DB ID':str(i)}) for i in range(70)]
        output=self.evaluate(available,trials='10',proposed='20')
        self.assertEqual(output['Remaining places'],20)
        self.assertTrue(output['Booking allowed'])
        records=[student(**{'Age Category':'U8','Player DB ID':str(i)}) for i in range(98)]
        output=self.evaluate(records,trials='5')
        self.assertEqual(output['Total occupancy'],103)
        self.assertEqual(output['Excess students'],3)
        self.assertFalse(output['Booking allowed'])
        self.assertTrue(self.evaluate(records,proposed='2')['Booking allowed'])
        self.assertFalse(self.evaluate(records,proposed='3')['Booking allowed'])

    def test_names_preserved_link_required(self):
        output=self.evaluate([student()],confirmed=False)
        self.assertEqual(output['Coaching Center Location'],' CSV Center ')
        self.assertEqual(output['Reference Centre'],'Reference Center')
        self.assertIsNone(output['Booking allowed'])

    def test_unknown_dates_ids_and_slots_withhold(self):
        for changes in [{'Player DB ID':''},{'Start Date':'bad'},{'Slots':''},{'Age Category':''}]:
            output=self.evaluate([student(),student(**changes)])
            self.assertEqual(output['Data completeness'],'Incomplete')
            self.assertIsNone(output['Booking allowed'])
            self.assertTrue(output['issues'])

    def test_expired_other_day_and_boundaries(self):
        records=[student(**{'Start Date':SAT.isoformat(),'End Date':SAT.isoformat()}),
                 student(**{'Player DB ID':'expired','Active':'false','End Date':'2026-10-14','Slots':''}),
                 student(**{'Player DB ID':'friday','Slots':'Friday 6:00 PM - 7:00 PM'})]
        result=self.evaluate(records)
        self.assertEqual(result['Unique enrolled students'],1)
        self.assertEqual(result['Data completeness'],'Complete')

    def test_active_false_counts_and_missing_dates_still_block(self):
        records=[student(**{'Active':'false','Player DB ID':'false-student'}),
                 student(**{'Active':'unknown','Player DB ID':'unknown-student'})]
        result=self.evaluate(records)
        self.assertEqual(result['Unique enrolled students'],2)
        self.assertTrue(result['Booking allowed'])
        result=self.evaluate([*records,student(**{'Active':'false','End Date':''})])
        self.assertIsNone(result['Booking allowed'])

    def test_ambiguous_divisions_and_times(self):
        for raw in ['U6 to U18','U5,7,9','U8 Elite/development']:
            self.assertIsNone(divisions(raw,None)[0][1])
        with self.assertRaises(ValueError):
            time_range('7pm to 8om')
        bad=catalog([schedule(time=None)],SAT)[0][1]
        self.assertIsNone(self.evaluate([student()],batch=bad)['Booking allowed'])
        missing=catalog([schedule(days='Saturday',proficiency=[None]*7)],SAT)[0][0]
        self.assertIsNone(self.evaluate([student()],batch=missing)['Booking allowed'])

    def test_duplicate_schedule_and_course_subset_blocked(self):
        repeated=catalog([schedule(),schedule(row=134)],SAT)[0][1]
        self.assertIsNone(self.evaluate([student()],batch=repeated)['Booking allowed'])
        self.assertIsNone(self.evaluate([student()],course='Regular')['Booking allowed'])

    def test_unsupplied_trials_and_invalid_inputs(self):
        self.assertIsNone(self.evaluate([student()],trials=None,proposed=None)['Total occupancy'])
        for value in ['-1','2.5','hello']:
            with self.assertRaises(ValueError):
                self.evaluate([student()],trials=value)


if __name__=='__main__':
    unittest.main()
