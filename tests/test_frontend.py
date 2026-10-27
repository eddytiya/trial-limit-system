import csv
import io
import unittest
from pathlib import Path
from frontend import calculate
from test_trial_limit import row
from trial_limit import REQUIRED


class FrontendTests(unittest.TestCase):
    def payload(self, records):
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=[*REQUIRED,'Active','Slots'])
        writer.writeheader()
        writer.writerows({'Slots':'Thursday 6:00 PM - 7:00 PM', **record} for record in records)
        return {'csv_text':stream.getvalue(), 'filename':'fictional.csv', 'reference_date':'2026-10-15'}

    def test_decisions_and_threshold(self):
        payload = self.payload([row(),row()])
        capacity=calculate(payload,Path('unused'))['groups'][0]['Capacity']
        for proposed, expected in [(str(capacity-1),True),(str(capacity),False)]:
            output = calculate({**payload,'group_index':0,'trials':'0','proposed':proposed},Path('unused'))
            self.assertEqual(output['groups'][0]['Unique enrolled students'],1)
            self.assertEqual(output['decision'], expected)

    def test_incomplete_and_unsupplied(self):
        payload = self.payload([row(),row(**{'Player DB ID':''})])
        output = calculate(payload,Path('unused'))
        self.assertIsNone(output['groups'][0]['Total occupancy'])
        output = calculate({**payload,'group_index':0,'trials':'0','proposed':'0'},Path('unused'))
        self.assertIsNone(output['decision'])

    def test_invalid_input(self):
        payload = self.payload([row()])
        for value in ['-1','2.5','bad']:
            with self.assertRaises(ValueError):
                calculate({**payload,'group_index':0,'trials':value},Path('unused'))


if __name__ == '__main__':
    unittest.main()
