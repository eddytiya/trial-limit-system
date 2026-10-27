"""Read-only enrollment analysis and explicitly manual trial simulation."""
import argparse
import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

GROUP_FIELDS = ('Academy ID', 'Coaching Center Location', 'Sports', 'Age Category', 'Course Name')
REQUIRED = (*GROUP_FIELDS, 'Academy Name', 'Player DB ID', 'Enrollment ID', 'Start Date', 'End Date')
RULE = 'dates_inclusive'


def today():
    return datetime.now(ZoneInfo('Asia/Kolkata')).date()


def nonnegative(value):
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit():
        raise ValueError('Enter a non-negative whole number.')
    return int(value)


def enrollment_date(value):
    """Parse ISO or the source export's explicit day-month-year format in memory."""
    import re
    if not isinstance(value,str):raise ValueError('Missing enrollment date')
    if re.fullmatch(r'\d{2}-\d{2}-\d{4}',value):
        return datetime.strptime(value,'%d-%m-%Y').date()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):return date.fromisoformat(value)
    raise ValueError('Enrollment date must use YYYY-MM-DD or DD-MM-YYYY')


def eligible(row, reference, rule):
    """Dates-only policy confirmed 19 October 2026; Active is ignored."""
    if rule != RULE:
        raise ValueError('Enrollment eligibility has not been confirmed.')
    try:
        start = enrollment_date(row['Start Date'])
        end = enrollment_date(row['End Date'])
        if start > end:
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise ValueError('Missing, invalid, or reversed enrollment dates') from None
    return start <= reference <= end


@dataclass
class Group:
    key: tuple
    academies: set = field(default_factory=set)
    students: set = field(default_factory=set)
    complete: bool = True
    trials: int | None = None


def load(path):
    path = Path(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open('r', encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        missing = set(REQUIRED) - set(reader.fieldnames or [])
        if missing:
            raise ValueError('Missing columns: ' + ', '.join(sorted(missing)))
        rows = []
        while True:
            line = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            rows.append((line, row))
    return rows, before


def analyze(rows, reference, rule=None):
    groups, issues, unresolved = {}, [], []
    for line, row in rows:
        key = tuple(row.get(k) for k in GROUP_FIELDS)
        # Discover existing complete capacity keys, even on ineligible records.
        if all(v is not None and v.strip() for v in key):
            group = groups.setdefault(key, Group(key))
            group.academies.add(row.get('Academy Name', ''))
        reasons = []
        missing = [k for k in (*GROUP_FIELDS, 'Player DB ID') if not row.get(k) or not row[k].strip()]
        if missing:
            reasons.append('Missing required fields: ' + ', '.join(missing))
        if None in row or any(row.get(k) is None for k in REQUIRED):
            reasons.append('Malformed CSV record (column count)')
        possible = True
        if rule is not None:
            try:
                possible = eligible(row, reference, rule)
            except ValueError as exc:
                reasons.append(str(exc))
        if reasons:
            issues.append({'Source row number': line, 'Enrollment ID': row.get('Enrollment ID'),
                           **{k: row.get(k) for k in GROUP_FIELDS},
                           'Player DB ID': row.get('Player DB ID'), 'Reason': '; '.join(reasons),
                           'Could affect counts': possible})
            if possible:
                unresolved.append(key)
        elif rule is not None and possible:
            groups[key].students.add(row['Player DB ID'])
    for group in groups.values():
        group.complete = rule is not None and not any(
            all(v is None or not v.strip() or v == actual for v, actual in zip(key, group.key))
            for key in unresolved)
    return list(groups.values()), issues


def result(group, reference, capacity, rule):
    enrolled = len(group.students) if rule else None
    total = enrolled + group.trials if enrolled is not None and group.trials is not None else None
    status = ('Available' if total < capacity else 'Full' if total == capacity else 'Over Capacity') if total is not None else 'Not confirmed'
    return {**dict(zip(GROUP_FIELDS, group.key)),
            'Academy Name': json.dumps(sorted(group.academies), ensure_ascii=False),
            'Reference date': reference.isoformat(), 'Unique enrolled students': enrolled,
            'Simulated trial students': group.trials if group.trials is not None else 'Not supplied',
            'Total occupancy': total, 'Capacity': capacity,
            'Remaining places': max(0, capacity-total) if total is not None else None,
            'Excess students': max(0, total-capacity) if total is not None else None,
            'Capacity status': status,
            'Data completeness': 'Complete' if group.complete else 'Incomplete',
            'Eligibility rule': rule or 'Awaiting confirmation'}


def can_book(group, proposed, capacity):
    proposed = nonnegative(proposed)
    if not group.complete or group.trials is None:
        return None
    return len(group.students) + group.trials + proposed <= capacity


def export(path, records, fields):
    # Exclusive creation prevents overwriting the source or previous exports.
    with Path(path).open('x', encoding='utf-8-sig', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_path', type=Path)
    parser.add_argument('--reference-date', type=date.fromisoformat, default=today())
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.json'))
    parser.add_argument('--eligibility-rule', choices=[RULE], default=RULE,
                        help='Inclusive enrollment dates only; Active is ignored (default)')
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parent.parent/'outputs')
    parser.add_argument('--no-interactive', action='store_true')
    args = parser.parse_args()
    capacity = nonnegative(json.loads(args.config.read_text())['capacity'])
    if capacity == 0:
        raise ValueError('Capacity must be positive')
    rows, digest = load(args.csv_path)
    groups, issues = analyze(rows, args.reference_date, args.eligibility_rule)
    print('CAPACITY GROUPS — no timed-session limits')
    if not args.eligibility_rule:
        print('Eligibility awaiting confirmation; enrollment and combined occupancy are not calculated.')
    for number, group in enumerate(groups, 1):
        print(number, json.dumps(result(group, args.reference_date, capacity, args.eligibility_rule), ensure_ascii=False))
    if not args.no_interactive and args.eligibility_rule and groups:
        print('MANUAL TRIAL SIMULATION: additional students not already counted as enrolled.')
        while True:
            choice = input('Group number (Enter to export and exit): ')
            if not choice:
                break
            try:
                index = nonnegative(choice)
                if not 1 <= index <= len(groups):
                    raise ValueError('Select an existing group number.')
                group = groups[index-1]
                group.trials = nonnegative(input('Simulated trial students: '))
                print(json.dumps(result(group, args.reference_date, capacity, args.eligibility_rule), ensure_ascii=False))
                proposed = nonnegative(input('Proposed additional trial students: '))
                decision = can_book(group, proposed, capacity)
                print('Cannot confirm booking: incomplete data.' if decision is None else 'Allowed' if decision else 'Rejected: capacity exceeded')
            except ValueError as exc:
                print(exc)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    summaries = [result(g, args.reference_date, capacity, args.eligibility_rule) for g in groups]
    summary_fields = list(result(Group(tuple('' for _ in GROUP_FIELDS)), args.reference_date, capacity, args.eligibility_rule))
    issue_fields = ['Source row number', 'Enrollment ID', *GROUP_FIELDS, 'Player DB ID', 'Reason', 'Could affect counts']
    export(args.output_dir / f'summary_{stamp}.csv', summaries, summary_fields)
    export(args.output_dir / f'data_quality_{stamp}.csv', issues, issue_fields)
    after = hashlib.sha256(args.csv_path.read_bytes()).hexdigest()
    if digest != after:
        raise RuntimeError('Source file hash changed during execution!')
    print(f'Exports: {args.output_dir.resolve()} | Source SHA-256 unchanged: {after}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, csv.Error) as error:
        raise SystemExit(str(error))
