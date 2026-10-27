import unittest
from pathlib import Path
from unittest.mock import patch
from slot_thresholds import slot_snapshot

class WeeklyScheduleTests(unittest.TestCase):
    def snapshot(self, rows, **changes):
        payload={'reference_date':'2026-11-01','include_weekly':True,
            'csv_text':'fixture','filename':'enrollment.csv','capacity_filename':'capacity.csv',
            'capacity_text':'Sport,Centre,CITY,Batch Time,Weekday,Total Capacity,Actual Capacity,Proficiency\n'+rows}
        with patch('slot_thresholds.read_source',return_value=([], 'fixture-hash')):
            return slot_snapshot({**payload,**changes},Path('absent.csv'),None,Path('absent.xlsx'))

    def test_week_contains_all_days_and_each_days_own_values(self):
        result=self.snapshot('Tennis,Club,Mumbai,6pm to 7pm,Monday,8,7,Open\nTennis,Club,Mumbai,6pm to 7pm,Sunday,10,0,Open\n')
        week=result['weekly']
        self.assertEqual((week['week_start'],week['week_end']),('2026-10-26','2026-11-01'))
        self.assertEqual([d['weekday'] for d in week['days']],['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'])
        self.assertEqual(week['days'][0]['batches'][0]['reference_remaining'],1)
        self.assertEqual(week['days'][6]['batches'][0]['reference_remaining'],10)
        self.assertEqual(week['days'][1]['batches'],[])
        self.assertEqual(result['batches'][0]['weekday'],'Sunday')

    def test_multiple_sports_cities_and_missing_center(self):
        result=self.snapshot('Tennis,Club,Mumbai,7pm to 8pm,Monday,8,7,Open\nFootball,Club,Mumbai,5pm to 6pm,Monday,20,4,Open\nTennis,Club,Pune,6pm to 7pm,Sunday,10,0,Open\nTennis,,Mumbai,6pm to 7pm,Monday,10,1,Open\n')
        self.assertEqual(result['weekly']['centers'],[{'center':'Club','city':'Mumbai','sports':['Football','Tennis']},{'center':'Club','city':'Pune','sports':['Tennis']}])
        self.assertEqual([b['sport'] for b in result['weekly']['days'][0]['batches']],['Football','Tennis'])
        self.assertFalse(any(not b['center'] for d in result['weekly']['days'] for b in d['batches']))

    def test_on_hold_missing_values_and_no_session_center(self):
        result=self.snapshot('Tennis,Club (on hold),Mumbai,6pm to 7pm,Sunday,8,2,Open\nFootball,Missing,Mumbai,6pm to 7pm,Sunday,,,\nTennis,No sessions,Mumbai,6pm to 7pm,Sunday,NA,NA,NA\n')
        batches=result['weekly']['days'][6]['batches']
        held=next(b for b in batches if 'hold' in b['center'])
        self.assertEqual(held['reference_status'],'Needs review')
        self.assertIsNone(held['reference_remaining'])
        missing=next(b for b in batches if b['center']=='Missing')
        self.assertIsNone(missing['capacity'])
        self.assertIn({'center':'No sessions','city':'Mumbai','sports':['Tennis']},result['weekly']['centers'])

    def test_weekly_is_optional_and_closed_centers_stay_excluded(self):
        from batch_mappings import club_key
        rows='Tennis,Club,Mumbai,6pm to 7pm,Sunday,8,2,Open\n'
        self.assertIsNone(self.snapshot(rows,include_weekly=False)['weekly'])
        key=club_key({'center':'Club','city':'Mumbai','sport':'Tennis'})
        with patch('batch_mappings.read_store',return_value={'excluded_clubs':{key:{}}}):
            result=self.snapshot(rows)
        self.assertEqual(result['weekly']['centers'],[])
        self.assertTrue(all(not d['batches'] for d in result['weekly']['days']))

if __name__=='__main__':unittest.main()
