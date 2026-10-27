import json
import tempfile
import unittest
from pathlib import Path
from capacity_overrides import resolve_centers


class CenterReferenceTests(unittest.TestCase):
    def test_only_confirmed_blank_rows_in_exact_snapshot_are_resolved(self):
        records=[{'row':n,'center':None,'sport':'Tennis','city':'Mumbai'} for n in (79,80,85)]
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            p=Path(folder)/'references.json'
            p.write_text(json.dumps({'version':1,'overrides':[{'source_hash':'correct','rows':[79,80],
                'center':'Acres Racquet Arena','sport':'Tennis','city':'Mumbai'}]}),encoding='utf-8')
            result,applied=resolve_centers(records,'correct',p)
            self.assertEqual(applied,[79,80])
            self.assertEqual(result[0]['center'],'Acres Racquet Arena')
            self.assertIsNone(result[0]['source_center'])
            self.assertIsNone(result[2]['center'])
            self.assertIsNone(records[0]['center'])
            self.assertEqual(resolve_centers(records,'new-snapshot',p)[1],[])

    def test_existing_names_and_different_sports_are_not_replaced(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            p=Path(folder)/'references.json'
            p.write_text(json.dumps({'version':1,'overrides':[{'source_hash':'hash','rows':[79,80],
                'center':'Acres Racquet Arena','sport':'Tennis','city':'Mumbai'}]}),encoding='utf-8')
            records=[{'row':79,'center':'Other Center','sport':'Tennis','city':'Mumbai'},
                {'row':80,'center':None,'sport':'Badminton','city':'Mumbai'}]
            result,applied=resolve_centers(records,'hash',p)
            self.assertEqual(applied,[])
            self.assertEqual(result,records)


if __name__=='__main__':unittest.main()
