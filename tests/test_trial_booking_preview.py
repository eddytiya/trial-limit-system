import unittest
from trial_booking_preview import booking_preview, overflow_probability, attach_booking_previews, sport_booking_rules, booking_scenarios


class BookingPreviewTests(unittest.TestCase):
    def test_same_sport_uses_same_rule_across_centres(self):
        batches=[{'center':name,'capacity':20,'workbook_reported_count':7,
                  'sport':sport,'issues':[]} for name,sport in
                 [('Centre A','Table Tennis'),('Centre B','TableTennis')]]
        attach_booking_previews(batches,'2026-10-26')
        previews=[b['trial_booking_preview'] for b in batches]
        self.assertEqual(previews[0],previews[1])
        self.assertEqual(previews[0]['rule_scope'],'Sport across all centres')

    def test_sport_rule_catalog_has_one_entry_per_sport(self):
        rules=sport_booking_rules()
        self.assertEqual(len(rules),len({r['sport'] for r in rules}))
        badminton=next(r for r in rules if r['sport']=='Badminton')
        self.assertAlmostEqual(badminton['turnup_rate'],259/1308)
        self.assertNotIn('booking_ceiling_percent',badminton)
        chess=next(r for r in rules if r['sport']=='Chess')
        self.assertFalse(chess['extra_bookings_supported'])

    def test_one_space_never_rounds_up(self):
        r=booking_preview(8,7,0.20,1)
        self.assertEqual(r['suggested_total_trial_bookings'],1)
        self.assertEqual(r['additional_bookings_allowed'],0)

    def test_ceiling_and_existing_bookings(self):
        r=booking_preview(20,7,259/1308,3)
        self.assertEqual(r['suggested_total_trial_bookings'],15)
        self.assertEqual(r['additional_bookings_allowed'],12)
        self.assertLessEqual(r['estimated_overflow_probability'],0.05)

    def test_high_attendance_risk_prevents_extra(self):
        self.assertEqual(booking_preview(10,0,1)['suggested_total_trial_bookings'],10)
        self.assertAlmostEqual(overflow_probability(3,1,0.2),0.104)

    def test_full_missing_and_zero_evidence(self):
        for rate in [None,0]:
            self.assertEqual(booking_preview(20,7,rate)['suggested_total_trial_bookings'],13)
        self.assertEqual(booking_preview(8,9,.2,2)['additional_bookings_allowed'],0)
        self.assertIsNone(booking_preview(8,7,.2)['additional_bookings_allowed'])

    def test_missing_scope_and_historical_dates_withheld(self):
        batch={'capacity':20,'workbook_reported_count':7,'sport':'Badminton','issues':[]}
        attach_booking_previews([batch],'2026-10-23')
        self.assertIsNone(batch['trial_booking_preview'])
        attach_booking_previews([batch],'2026-10-26')
        self.assertEqual([r['total_trial_bookings'] for r in batch['trial_booking_preview']['scenarios']],[13,14,15])
        batch['issues']=['Needs review']
        attach_booking_previews([batch],'2026-10-26')
        self.assertIsNone(batch['trial_booking_preview'])

    def test_requested_one_space_scenarios(self):
        result=booking_scenarios(8,7,.2)
        self.assertEqual([r['total_trial_bookings'] for r in result['scenarios']],[1,2,3])
        for scenario,expected,risk in zip(result['scenarios'],[.2,.4,.6],[0,.04,.104]):
            self.assertAlmostEqual(scenario['expected_trial_attendees'],expected)
            self.assertAlmostEqual(scenario['estimated_overflow_probability'],risk)
        self.assertNotIn('suggested_total_trial_bookings',result)

    def test_no_automatic_extra_with_missing_evidence_or_full_batch(self):
        for rate in [None,0]:
            result=booking_scenarios(8,7,rate)
            self.assertEqual(len(result['scenarios']),1)
            self.assertIsNone(result['scenarios'][0]['expected_trial_attendees'])
        self.assertEqual(booking_scenarios(8,8,.2)['scenarios'][0]['total_trial_bookings'],0)

    def test_single_selection_uses_actual_spaces(self):
        from trial_booking_preview import select_booking_suggestion
        one=select_booking_suggestion(8,7,.2)
        self.assertEqual(one['selected_scenario']['total_trial_bookings'],2)
        self.assertAlmostEqual(one['selected_scenario']['estimated_overflow_probability'],.04)
        two=select_booking_suggestion(8,6,.2)
        self.assertEqual(two['selected_scenario']['total_trial_bookings'],4)
        self.assertAlmostEqual(two['selected_scenario']['estimated_overflow_probability'],.0272)
        self.assertIsNone(select_booking_suggestion(8,7,None)['selected_scenario'])

    def test_sport_summary_keeps_partial_and_missing_counts_explicit(self):
        from trial_booking_preview import sport_inventory_summary
        batches=[{'sport':'Tennis','capacity':8,'workbook_reported_count':7,'issues':[]},
                 {'sport':'Tennis','capacity':12,'workbook_reported_count':2,'issues':[]},
                 {'sport':'Tennis','capacity':None,'workbook_reported_count':None,'issues':['Missing']},
                 {'sport':'Unknown','capacity':None,'workbook_reported_count':None,'issues':['Missing']}]
        attach_booking_previews(batches,'2026-10-26')
        rows=sport_inventory_summary(batches)
        tennis=next(r for r in rows if r['sport']=='Tennis')
        self.assertEqual(tennis['capacity'],20)
        self.assertEqual(tennis['currently_active'],9)
        self.assertEqual(tennis['places_left'],11)
        self.assertEqual(tennis['sessions_requiring_review'],1)
        self.assertEqual(tennis['suggested_trial_bookings'],14)
        unknown=next(r for r in rows if r['sport']=='Unknown')
        self.assertIsNone(unknown['capacity'])
        self.assertIsNone(unknown['currently_active'])
