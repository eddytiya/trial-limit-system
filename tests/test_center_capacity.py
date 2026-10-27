import unittest
from datetime import date
from automatic_capacity import analyze_center_batches,booking_decision,exceeded_centers
from test_automatic_capacity import enrolled,trial

REF=date(2026,10,19)


def analyze(records,trials=None,capacity=100):
    return analyze_center_batches(list(enumerate(records,2)),
        None if trials is None else list(enumerate(trials,2)),REF,capacity)


class CenterBatchTests(unittest.TestCase):
    def test_missing_invalid_and_offday_slots_are_ignored(self):
        records=[enrolled('blank',Slots=''),enrolled('bad',Slots='not a slot'),
                 enrolled('tuesday',Slots='Tuesday 6:00 PM - 7:00 PM')]
        no_slots=enrolled('absent');no_slots.pop('Slots');records.append(no_slots)
        batches,issues=analyze(records,[])
        self.assertEqual(len(batches),1)
        self.assertEqual(batches[0]['Unique enrolled students'],4)
        self.assertEqual(batches[0]['Data completeness'],'Complete')
        self.assertFalse(issues)

    def test_dates_not_calendar_month_and_active_ignored(self):
        records=[enrolled('boundary',Active='false',**{'Start Date':REF.isoformat(),'End Date':REF.isoformat()}),
                 enrolled('ended',**{'End Date':'2026-10-18'}),
                 enrolled('future',**{'Start Date':'2026-10-20'})]
        self.assertEqual(analyze(records,[])[0][0]['Unique enrolled students'],1)

    def test_same_student_deduped_across_courses_times_and_records(self):
        records=[enrolled(),enrolled(Slots='Monday 7:00 PM - 8:00 PM',**{'Course Name':'Advanced'}),enrolled()]
        b=analyze(records,[])[0][0]
        self.assertEqual(b['Unique enrolled students'],1)

    def test_center_age_sport_academy_remain_independent(self):
        records=[enrolled(),enrolled(**{'Age Category':'U10'}),enrolled(Sports='Tennis'),
                 enrolled(**{'Coaching Center Location':'Center '}),enrolled(**{'Academy ID':'002'})]
        self.assertEqual(len(analyze(records,[])[0]),5)

    def test_missing_group_dates_ids_still_block(self):
        for change in [{'Age Category':''},{'Player DB ID':''},{'End Date':''},{'Coaching Center Location':''}]:
            b,q=analyze([enrolled(),enrolled('bad',**change)],[])
            self.assertEqual(b[0]['Data completeness'],'Incomplete')
            self.assertIsNone(booking_decision(b[0],1))
            self.assertTrue(q)

    def test_trial_times_ignored_and_overlap_deduplicated(self):
        t=trial('new',**{'Start Time':'bad','End Time':''})
        without_time=trial('new');without_time.pop('Start Time');without_time.pop('End Time')
        b,q=analyze([enrolled()],[trial('p1'),t,without_time,trial('cancel',Status='Cancelled'),
                                   trial('other',**{'Trial Date':'2026-10-20'})])
        self.assertEqual(b[0]['Total occupancy'],2)
        self.assertEqual(b[0]['Trial students'],1)
        self.assertFalse(q)

    def test_threshold_and_exceeded_tab_use_aggregate_age_count(self):
        records=[enrolled(str(i),Slots='Monday 6:00 PM - 7:00 PM') for i in range(6)]
        records += [enrolled('later'+str(i),Slots='Tuesday 7:00 PM - 8:00 PM') for i in range(5)]
        batches,_=analyze(records,[],10)
        self.assertEqual(batches[0]['Total occupancy'],11)
        self.assertFalse(booking_decision(batches[0],0))
        centers=exceeded_centers(batches,10)
        self.assertEqual(len(centers[0]['Exceeded batches']),1)
        self.assertEqual(centers[0]['Highest known batch count'],11)
        self.assertEqual(centers[0]['Largest known excess'],1)

    def test_trials_not_supplied_not_assumed_zero(self):
        b=analyze([enrolled(Slots='')])[0][0]
        self.assertEqual(b['Data completeness'],'Complete')
        self.assertIsNone(b['Total occupancy'])
        self.assertIsNone(booking_decision(b,1))


if __name__=='__main__':unittest.main()
