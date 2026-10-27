import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from automatic_capacity import (analyze_automatic,automatic_snapshot,booking_decision,
                                ENROLLMENT_FIELDS,TRIAL_FIELDS,exceeded_centers)
from test_trial_limit import row

REF=date(2026,10,19)


def enrolled(identifier='p1',**changes):
    return {**row(),'Player DB ID':identifier,'Slots':'Monday 6:00 PM - 7:00 PM',**changes}


def trial(identifier='t1',**changes):
    r=enrolled(identifier)
    return {'Trial Booking ID':'B'+identifier,**{k:r[k] for k in
        ('Academy ID','Academy Name','Coaching Center Location','Sports','Age Category','Player DB ID')},
        'Trial Date':REF.isoformat(),'Start Time':'6:00 PM','End Time':'7:00 PM','Status':'Scheduled',**changes}


def analyze(enrollments,trials=None):
    return analyze_automatic(list(enumerate(enrollments,2)),
        None if trials is None else list(enumerate(trials,2)),REF)


class AutomaticTests(unittest.TestCase):
    def test_exceeded_centers_strict_boundary_and_no_session_sum(self):
        records=[enrolled(str(i)) for i in range(12)]
        records += [enrolled('later'+str(i),Slots='Monday 7:00 PM - 8:00 PM') for i in range(11)]
        records += [enrolled('other'+str(i),**{'Coaching Center Location':'Other'}) for i in range(10)]
        records += [enrolled('age'+str(i),**{'Age Category':'U10'}) for i in range(4)]
        batches,_=analyze(records)
        centers=exceeded_centers(batches,10)
        self.assertEqual(len(centers),1)
        self.assertEqual(len(centers[0]['Exceeded batches']),2)
        self.assertEqual(centers[0]['Highest known batch count'],12)
        self.assertEqual(centers[0]['Largest known excess'],2)
        self.assertEqual(exceeded_centers(batches,100),[])

    def test_thresholds_and_booking_gate(self):
        records=[enrolled(str(i)) for i in range(80)]
        for count,expected in [(15,'Available'),(20,'Full'),(25,'Over Capacity')]:
            batches,_=analyze(records,[trial('t'+str(i)) for i in range(count)])
            b=batches[0]
            self.assertEqual(b['Capacity status'],expected)
            self.assertEqual(b['Total occupancy'],80+count)
            self.assertEqual(b['Known excess students'],max(0,count-20))
        b=analyze(records,[trial('t'+str(i)) for i in range(15)])[0][0]
        self.assertTrue(booking_decision(b,5));self.assertFalse(booking_decision(b,6))

    def test_deduplicates_courses_trials_and_overlap(self):
        batches,_=analyze([enrolled(),enrolled(**{'Course Name':'Advanced'})],
                          [trial('p1'),trial(),trial()])
        self.assertEqual(len(batches),1)
        self.assertEqual(batches[0]['Unique enrolled students'],1)
        self.assertEqual(batches[0]['Trial students'],1)
        self.assertEqual(batches[0]['Trial students already enrolled'],1)
        self.assertEqual(batches[0]['Total occupancy'],2)

    def test_age_sport_center_time_independent(self):
        records=[enrolled(),enrolled(**{'Age Category':'U10'}),enrolled(Sports='Tennis'),
                 enrolled(**{'Coaching Center Location':'Center '}),
                 enrolled(Slots='Monday 7:00 PM - 8:00 PM')]
        batches,_=analyze(records,[])
        self.assertEqual(len(batches),5)
        self.assertTrue(all(b['Total occupancy']==1 for b in batches))

    def test_dates_boundaries_and_active_ignored(self):
        records=[enrolled(Active='false',**{'Start Date':REF.isoformat(),'End Date':REF.isoformat()}),
                 enrolled('expired',**{'End Date':'2026-10-18'}),
                 enrolled('future',**{'Start Date':'2026-10-20'}),enrolled('offday',Slots='Tuesday 6:00 PM - 7:00 PM')]
        self.assertEqual(analyze(records,[])[0][0]['Total occupancy'],1)

    def test_missing_trials_is_unknown_not_zero(self):
        b=analyze([enrolled()])[0][0]
        self.assertIsNone(b['Trial students']);self.assertIsNone(b['Total occupancy'])
        self.assertIsNone(b['Remaining places']);self.assertEqual(b['Capacity status'],'Not confirmed')
        self.assertIsNone(booking_decision(b,0))
        self.assertEqual(analyze([enrolled()],[])[0][0]['Trial students'],0)

    def test_enrollment_over_limit_flagged_without_trials(self):
        b=analyze([enrolled(str(i)) for i in range(101)])[0][0]
        self.assertEqual(b['Known excess students'],1)
        self.assertIn('Over Capacity',b['Capacity status'])
        self.assertIsNone(b['Total occupancy'])

    def test_missing_dates_slots_ids_withhold(self):
        for bad in [{'Start Date':''},{'Slots':''},{'Player DB ID':''},{'Age Category':''}]:
            batches,issues=analyze([enrolled(),enrolled('bad',**bad)],[])
            self.assertEqual(batches[0]['Data completeness'],'Incomplete')
            self.assertIsNone(booking_decision(batches[0],1));self.assertTrue(issues)

    def test_trial_cancellation_date_and_trial_only_batches(self):
        b=analyze([], [trial(),trial('cancel',Status='Cancelled'),
                       trial('otherday',**{'Trial Date':'2026-10-20'})])[0][0]
        self.assertEqual(b['Unique enrolled students'],0)
        self.assertEqual(b['Trial students'],1)

    def test_invalid_trials_and_conflicting_states(self):
        for changes in [{'Status':'Unknown'},{'Trial Date':''},{'Start Time':'bad'},{'Player DB ID':''}]:
            b=analyze([enrolled()],[trial(**changes)])[0][0]
            self.assertEqual(b['Data completeness'],'Incomplete')
        b=analyze([enrolled()],[trial(),trial(Status='Cancelled')])[0][0]
        self.assertEqual(b['Data completeness'],'Incomplete')

    def test_invalid_proposals_and_capacity(self):
        b=analyze([enrolled()],[])[0][0]
        for invalid in [-1,1.5,'bad',True]:
            with self.assertRaises(ValueError):booking_decision(b,invalid)
        with self.assertRaises(ValueError):analyze_automatic([],[],REF,0)

    def test_file_refresh_and_source_preservation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root=Path(folder);p=root/'enrollment.csv';t=root/'trials.csv'
            def write(path,fields,records):
                with path.open('w',encoding='utf-8',newline='') as f:
                    writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(records)
            write(p,ENROLLMENT_FIELDS,[enrolled()]);before=p.read_bytes()
            first=automatic_snapshot({'reference_date':REF.isoformat()},p,t)
            self.assertIsNone(first['batches'][0]['Total occupancy'])
            self.assertEqual(p.read_bytes(),before)
            write(t,TRIAL_FIELDS,[trial()]);trial_before=t.read_bytes()
            second=automatic_snapshot({'reference_date':REF.isoformat()},p,t)
            self.assertEqual(second['batches'][0]['Total occupancy'],2)
            self.assertEqual(t.read_bytes(),trial_before)
            write(p,ENROLLMENT_FIELDS,[enrolled(),enrolled('p2')])
            third=automatic_snapshot({'reference_date':REF.isoformat()},p,t)
            self.assertEqual(third['batches'][0]['Total occupancy'],3)
            self.assertNotEqual(first['enrollment_hash'],third['enrollment_hash'])


if __name__=='__main__':unittest.main()
