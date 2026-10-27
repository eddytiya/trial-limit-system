import tempfile
import unittest
from pathlib import Path
from batch_mappings import attach_mappings,save_mapping,read_store


def batch(**changes):
    return {'center':'Club A','city':'City A','sport':'Tennis','weekday':'Monday','time':'6pm to 7pm',
        'division':'Beginner','capacity':16,'days':'Monday to Friday','source_row':3,**changes}


def target(**changes):
    return {'id':'0','academy_id':'academy','academy':'Academy','center':'Club A, Location A','sport':'Tennis',
        'ages':['Child','Adult'],'proficiency_memberships':[{'age':'Child','course':'Beginner'},
            {'age':'Adult','course':'Beginner'}],**changes}


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.path=Path(self.folder.name)/'links.json'

    def tearDown(self):self.folder.cleanup()

    def approve(self,b=None,t=None):
        save_mapping(self.path,b or batch(),t or target(),'Child',[['Child','Beginner']],'capacity.xlsx','hash1')

    def attach(self,b=None,t=None,source_hash='hash1'):
        rows=[b or batch()];options=[t or target()]
        stats=attach_mappings(rows,options,self.path,'capacity.xlsx',source_hash)
        return rows[0],stats

    def test_suggestions_do_not_save_or_approve(self):
        b,s=self.attach()
        self.assertFalse(self.path.exists())
        self.assertEqual(s['approved_batches'],0)
        self.assertIsNone(b['approved_mapping'])
        self.assertEqual(b['club_label'],'Club A · City A')

    def test_save_reload_and_exact_full_club_location(self):
        self.approve();b,s=self.attach()
        self.assertEqual(s['approved_batches'],1)
        self.assertEqual(b['approved_mapping']['target']['center'],'Club A, Location A')
        self.assertEqual(b['approved_mapping']['proficiency_pairs'],[['Child','Beginner']])
        self.assertEqual(len(read_store(self.path)['clubs']),1)

    def test_same_named_clubs_in_different_cities_are_not_merged(self):
        self.approve();b,s=self.attach(batch(city='City B'))
        self.assertEqual(s['approved_batches'],0)
        self.assertIsNone(b['club_target_id'])

    def test_capacity_change_requires_review(self):
        self.approve();b,_=self.attach(batch(capacity=20))
        self.assertIsNone(b['approved_mapping'])
        self.assertIn('definition changed',b['mapping_status'])

    def test_named_club_mapping_reuses_unchanged_definition_after_new_export(self):
        self.approve();b,s=self.attach(source_hash='new-export-hash')
        self.assertEqual(s['approved_batches'],1)

    def test_blank_center_link_is_snapshot_specific(self):
        self.approve(batch(center=None));b,s=self.attach(batch(center=None))
        self.assertEqual(s['approved_batches'],1)
        b,_=self.attach(batch(center=None),source_hash='changed-hash')
        self.assertIsNone(b['approved_mapping'])

    def test_other_slots_reuse_club_only_not_proficiency_approval(self):
        self.approve();b,s=self.attach(batch(time='7pm to 8pm',division='Adult Beginner'))
        self.assertIsNone(b['approved_mapping'])
        self.assertEqual(b['club_target_id'],'0')
        self.assertEqual(s['approved_batches'],0)

    def test_location_or_membership_change_invalidates_link(self):
        self.approve()
        for t in [target(center='Club A, Location B'),target(proficiency_memberships=[])]:
            b,_=self.attach(t=t);self.assertIsNone(b['approved_mapping'])

    def test_target_menu_reordering_does_not_change_saved_identity(self):
        self.approve();b,_=self.attach(t=target(id='27'))
        self.assertEqual(b['approved_mapping']['target_id'],'27')

    def test_changing_club_link_invalidates_other_previous_batch_links(self):
        self.approve()
        self.approve(batch(time='7pm to 8pm'),target(center='Different Club'))
        b,_=self.attach();self.assertIsNone(b['approved_mapping'])
        self.assertIn('club link changed',b['mapping_status'])


if __name__=='__main__':unittest.main()
