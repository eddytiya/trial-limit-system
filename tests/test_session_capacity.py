import unittest
from datetime import date
from session_capacity import analyze_sessions, parse_slots
from trial_limit import can_book
from test_trial_limit import row

REF=date(2026,10,15)  # Thursday


def record(**changes):
    return {**row(), 'Slots':'Thursday 6:00 PM - 7:00 PM', **changes}


class SessionTests(unittest.TestCase):
    def test_age_groups_independent_same_ground_time(self):
        rows=[record(**{'Age Category':age,'Player DB ID':str(i)})
              for age in ['U8','U10'] for i in range(90)]
        groups,issues,_=analyze_sessions(list(enumerate(rows,2)),REF)
        self.assertEqual(len(groups),2)
        self.assertFalse(issues)
        for group in groups:
            self.assertEqual(len(group.students),90)
            group.trials=5
            self.assertTrue(can_book(group,5,100))
            self.assertFalse(can_book(group,6,100))

    def test_duplicates_sessions_courses_and_dates(self):
        records=[record(),record(),record(Slots='Thursday 6:00 PM - 7:00 PM, Thursday 7:00 PM - 8:00 PM'),
                 record(**{'Course Name':'Advanced'}), record(Slots='Friday 6:00 PM - 7:00 PM'),
                 record(**{'Player DB ID':'expired','End Date':'2026-10-14'})]
        groups,_,_=analyze_sessions(list(enumerate(records,2)),REF)
        self.assertEqual(len(groups),3)
        self.assertEqual([len(g.students) for g in groups],[1,1,1])

    def test_unknown_slots_affect_only_compatible_group(self):
        records=[record(),record(**{'Age Category':'U10'}),record(Slots=''),
                 record(**{'Age Category':'U10','Active':'false','End Date':'2026-10-14','Slots':'bad'})]
        groups,issues,_=analyze_sessions(list(enumerate(records,2)),REF)
        self.assertFalse(groups[0].complete)
        self.assertTrue(groups[1].complete)
        self.assertEqual(len(issues),2)

    def test_missing_identifier_only_affects_listed_session(self):
        records=[record(),record(Slots='Thursday 7:00 PM - 8:00 PM'),record(**{'Player DB ID':''})]
        groups,_,_=analyze_sessions(list(enumerate(records,2)),REF)
        self.assertFalse(groups[0].complete)
        self.assertTrue(groups[1].complete)

    def test_invalid_slots_not_repaired(self):
        for raw in ['', 'Thursday 6:00 PM - 7:00', 'Thursday 8:00 PM - 7:00 PM',
                    'Thursday 13:00 PM - 7:00 PM', 'Thursday 6:00 PM - 7:00 PM)']:
            with self.assertRaises(ValueError):
                parse_slots(raw)

    def test_boundary_and_off_day(self):
        records=[record(**{'Start Date':REF.isoformat(),'End Date':REF.isoformat()}),
                 record(**{'Player DB ID':'other','Slots':'Friday 6:00 PM - 7:00 PM'})]
        groups,_,_=analyze_sessions(list(enumerate(records,2)),REF)
        self.assertEqual(len(groups),1)
        self.assertEqual(len(groups[0].students),1)


if __name__=='__main__':
    unittest.main()
