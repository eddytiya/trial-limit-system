"""Read-only booking suggestions; never changes capacity or reservation state."""
import json
import math
from pathlib import Path


def sport_booking_rules():
    """One attendance profile per sport, shared by every centre and session."""
    profile=json.loads(Path(__file__).with_name('trial_turnup_profile.json').read_text(encoding='utf-8'))
    return [{'sport':e['sport'], 'booked':e['booked'], 'attended':e['attended'],
             'turnup_rate':e['attended']/e['booked'] if e['booked'] else None,
             'history_from':profile['from'], 'history_through':profile['through'],
             'mode':'Scenario comparison; no automatic limit',
             'scope':'Sport across all centres',
             'extra_bookings_supported':e['booked']>0 and e['attended']>0}
            for e in profile['sports'].values()]


def overflow_probability(bookings, spaces, rate):
    """Binomial estimate assuming independent attendance with constant probability."""
    if bookings <= spaces:
        return 0.0
    return min(1.0, max(0.0, math.fsum(
        math.comb(bookings, k) * rate**k * (1-rate)**(bookings-k)
        for k in range(spaces+1, bookings+1))))


def booking_preview(capacity, enrolled, rate, existing_trials=None, risk_limit=0.05):
    """120% ceiling and provisional overflow-risk threshold, rounded down."""
    for value in (capacity, enrolled):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError('Capacity and enrolled counts must be nonnegative integers')
    if not 0 <= risk_limit < 1:
        raise ValueError('Risk threshold must be between zero and one')
    if rate is not None and (not isinstance(rate, (int, float)) or not math.isfinite(rate) or not 0 <= rate <= 1):
        raise ValueError('Invalid attendance rate')
    if existing_trials is not None and (isinstance(existing_trials, bool) or not isinstance(existing_trials, int) or existing_trials < 0):
        raise ValueError('Existing trial bookings must be a nonnegative integer')
    spaces=max(0, capacity-enrolled)
    ceiling=spaces*120//100
    supported=rate is not None and rate > 0
    limit=spaces
    if supported:
        for candidate in range(spaces+1, ceiling+1):
            if overflow_probability(candidate, spaces, rate) > risk_limit:
                break
            limit=candidate
    return {'available_trial_spaces':spaces, 'ceiling_120_percent':ceiling,
            'suggested_total_trial_bookings':limit,
            'additional_bookings_allowed':None if existing_trials is None else max(0,limit-existing_trials),
            'expected_trial_attendees':limit*rate if supported else None,
            'estimated_overflow_probability':overflow_probability(limit,spaces,rate) if supported else None,
            'turnup_rate':rate, 'provisional_risk_limit':risk_limit,
            'existing_trials':existing_trials, 'mode':'Preview only',
            'note':'Provisional 5% risk threshold; incomplete attendance outcomes. No automatic cancellations.' if supported else 'No usable attendance evidence; no extra bookings suggested.'}


def booking_scenarios(capacity, enrolled, rate):
    """Compare total trial bookings at available spaces, +1 and +2."""
    for value in (capacity, enrolled):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError('Capacity and enrolled counts must be nonnegative integers')
    if rate is not None and (not isinstance(rate, (int, float)) or not math.isfinite(rate) or not 0 <= rate <= 1):
        raise ValueError('Invalid attendance rate')
    spaces=max(0,capacity-enrolled)
    supported=rate is not None and rate > 0
    # No extra-booking scenarios when already full or attendance evidence is absent.
    candidates=range(spaces,spaces+3) if spaces and supported else [spaces]
    return {'available_trial_spaces':spaces,'turnup_rate':rate,
            'mode':'Scenario comparison; no automatic limit',
            'note':'Estimates assume independent attendance; unknown outcomes may understate turnout.',
            'scenarios':[{'total_trial_bookings':n,'extra_vs_spaces':n-spaces,
                          'expected_trial_attendees':n*rate if supported else None,
                          'estimated_overflow_probability':overflow_probability(n,spaces,rate) if supported else None}
                         for n in candidates],
            'status':'No trial spaces' if not spaces else 'Compare scenarios' if supported else 'Insufficient attendance evidence'}


def select_booking_suggestion(capacity, enrolled, rate, risk_limit=0.05):
    """Select one of spaces, spaces+1, spaces+2; threshold is provisional."""
    if not 0 <= risk_limit < 1:
        raise ValueError('Invalid risk threshold')
    result=booking_scenarios(capacity,enrolled,rate)
    eligible=[s for s in result['scenarios'] if s['estimated_overflow_probability'] is not None
              and s['estimated_overflow_probability'] <= risk_limit]
    result['selected_scenario']=eligible[-1] if eligible else None
    result['provisional_risk_limit']=risk_limit
    result['mode']='Single suggestion; provisional threshold; no booking enforcement'
    return result


def sport_inventory_summary(batches):
    """Daily sport totals over complete batch snapshots, not unique students."""
    groups={}
    for batch in batches:
        sport=batch.get('sport') or 'Sport not supplied'
        key=''.join(c for c in sport.lower() if c.isalnum())
        if key=='tabletennis':sport='Table Tennis'
        group=groups.setdefault(key,{'sport':sport,'batch_sessions':0,'complete_sessions':0,
            'sessions_requiring_review':0,'capacity':0,'currently_active':0,'places_left':0,
            'suggested_trial_bookings':0,'sessions_with_suggestion':0})
        group['batch_sessions']+=1
        if batch.get('issues') or batch.get('capacity') is None or batch.get('workbook_reported_count') is None:
            group['sessions_requiring_review']+=1
            continue
        group['complete_sessions']+=1
        group['capacity']+=batch['capacity']
        group['currently_active']+=batch['workbook_reported_count']
        group['places_left']+=max(0,batch['capacity']-batch['workbook_reported_count'])
        selected=(batch.get('trial_booking_preview') or {}).get('selected_scenario')
        if selected is not None:
            group['suggested_trial_bookings']+=selected['total_trial_bookings']
            group['sessions_with_suggestion']+=1
    for group in groups.values():
        if not group['complete_sessions']:
            for field in ['capacity','currently_active','places_left']:
                group[field]=None
        if group['sessions_with_suggestion']!=group['complete_sessions'] or not group['complete_sessions']:
            group['suggested_trial_bookings']=None
    return sorted(groups.values(),key=lambda g:g['sport'])


def attach_booking_previews(batches, reference_date):
    profile=json.loads(Path(__file__).with_name('trial_turnup_profile.json').read_text(encoding='utf-8'))
    for batch in batches:
        batch['trial_booking_preview']=None
        if batch.get('issues') or batch.get('capacity') is None or batch.get('workbook_reported_count') is None:
            continue
        # Do not use future attendance evidence for a historical analysis date.
        if reference_date <= profile['through']:
            continue
        sport=''.join(c for c in (batch.get('sport') or '').lower() if c.isalnum())
        evidence=profile['sports'].get(sport)
        rate=evidence['attended']/evidence['booked'] if evidence and evidence['booked'] else None
        result=select_booking_suggestion(batch['capacity'],batch['workbook_reported_count'],rate)
        result.update({'rule_scope':'Sport across all centres',
                       'sport':evidence['sport'] if evidence else batch.get('sport'),
                       'evidence':evidence,'history_from':profile['from'],'history_through':profile['through'],
                       'occupancy_basis':'Reported schedule count; not confirmed live enrollment. Existing trials not reconciled.'})
        batch['trial_booking_preview']=result
