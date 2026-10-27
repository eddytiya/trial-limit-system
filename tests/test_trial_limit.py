import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from trial_limit import GROUP_FIELDS, REQUIRED, RULE, Group, analyze, can_book, eligible, load, nonnegative, result

REF = date(2026, 10, 15)


def row(**changes):
    value = dict.fromkeys(REQUIRED, '')
    value.update({'Academy ID': '001', 'Academy Name': ' Academy ', 'Coaching Center Location': 'Center',
                  'Sports': 'Sport', 'Age Category': 'U8', 'Course Name': 'Regular',
                  'Player DB ID': '0001', 'Enrollment ID': 'E1', 'Active': 'true',
                  'Start Date': '2026-10-01', 'End Date': '2026-10-31'})
    value.update(changes)
    return value


class Tests(unittest.TestCase):
    def test_duplicates_and_separate_groups(self):
        records = [row(), row(), row(**{'Course Name': 'Advanced'}), row(**{'Age Category': 'U9'}),
                   row(**{'Course Name': 'Regular '})]
        groups, issues = analyze(list(enumerate(records, 2)), REF, RULE)
        self.assertEqual(len(groups), 4)
        self.assertEqual([len(g.students) for g in groups], [1]*4)
        self.assertFalse(issues)

    def test_boundaries_and_active_ignored(self):
        for start, end, expected in [('2026-10-15','2026-10-15',True), ('2026-10-16','2026-10-31',False),
                                     ('2026-10-01','2026-10-14',False)]:
            self.assertEqual(eligible(row(**{'Start Date': start, 'End Date': end}), REF, RULE), expected)
        for active in ['false','true','','unknown',None]:
            self.assertTrue(eligible(row(Active=active), REF, RULE))
        without_active=row();without_active.pop('Active')
        self.assertTrue(eligible(without_active, REF, RULE))

    def test_missing_and_invalid(self):
        records = [row(), row(**{'Age Category': ''}), row(**{'Player DB ID': ''}),
                   row(**{'Start Date': 'bad'}), row(**{'End Date': ''})]
        groups, issues = analyze(list(enumerate(records, 2)), REF, RULE)
        self.assertEqual(len(issues), 4)
        self.assertEqual(issues[0]['Source row number'], 3)
        self.assertFalse(groups[0].complete)
        self.assertEqual(len(groups[0].students), 1)
        groups[0].trials = 0
        self.assertIsNone(can_book(groups[0], 1, 100))

    def test_affected_groups_only(self):
        groups, _ = analyze([(2,row()), (3,row(**{'Course Name':'Advanced'})),
                              (4,row(**{'Course Name':'Advanced', 'End Date':'bad'}))], REF, RULE)
        self.assertTrue(groups[0].complete)
        self.assertFalse(groups[1].complete)

    def test_capacity(self):
        group = Group(('a','b','c','d','e'), students={str(i) for i in range(80)})
        for trials, status, remaining, excess in [(15,'Available',5,0),(20,'Full',0,0),(25,'Over Capacity',0,5)]:
            group.trials = trials
            output = result(group, REF, 100, RULE)
            self.assertEqual((output['Capacity status'],output['Remaining places'],output['Excess students']),
                             (status,remaining,excess))
        group.trials = 15
        self.assertTrue(can_book(group,5,100))
        self.assertFalse(can_book(group,6,100))
        group.trials = None
        self.assertIsNone(result(group, REF,100,RULE)['Total occupancy'])
        self.assertIsNone(can_book(group,0,100))

    def test_invalid_inputs(self):
        for value in [-1, 1.5, '1.0', '', 'hello', True, ' 2', '²']:
            with self.assertRaises(ValueError):
                nonnegative(value)
        self.assertEqual(nonnegative('0'), 0)

    def test_pending_rule(self):
        groups, _ = analyze([(2,row())], REF)
        self.assertFalse(groups[0].complete)
        self.assertIsNone(result(groups[0],REF,100,None)['Unique enrolled students'])
        with self.assertRaises(ValueError):
            eligible(row(),REF,None)

    def test_source_unchanged_and_strings(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory)/'source.csv'
            with path.open('w',newline='',encoding='utf-8') as output:
                writer = csv.DictWriter(output,fieldnames=[*REQUIRED,'Active'])
                writer.writeheader()
                writer.writerow(row())
            before = path.read_bytes()
            records, _ = load(path)
            groups, _ = analyze(records,REF,RULE)
            self.assertIn('0001',groups[0].students)
            self.assertEqual(groups[0].academies, {' Academy '})
            self.assertEqual(before,path.read_bytes())


if __name__ == '__main__':
    unittest.main()
