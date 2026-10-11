"""Read minimized football-data.org snapshots and produce auditable histories.

Canonical IDs are namespaced provider identities, NOT cross-provider mappings.
Dates must carry offsets. Scores/statistics use 90 minutes. Freshness is anchored
to min(event kickoff, verification time); all upper bounds are exclusive.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PROVIDER = 'football-data.org'
COMPETITIONS = {'SA': 2019, 'PL': 2021, 'PD': 2014, 'BL1': 2002,
                'FL1': 2015, 'DED': 2003, 'PPL': 2017, 'ELC': 2016, 'CL': 2001}
NONFINAL = {'SCHEDULED', 'TIMED', 'IN_PLAY', 'PAUSED', 'SUSPENDED',
            'POSTPONED', 'CANCELLED', 'AWARDED'}
UTC = timezone.utc


class InputError(ValueError):
    """Only safe, fixed error codes are exposed by the CLI."""


def instant(value: str | datetime) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(UTC)
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise InputError('invalid_or_naive_timestamp') from None


def positive_id(value: Any) -> bool:
    return type(value) is int and value > 0


def safe_name(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= 160 and not any(ord(c) < 32 for c in value)


def team_key(team_id: int) -> str:
    return f'{PROVIDER}:team:{team_id}'


def resolve_team(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r'football-data\.org:team:[1-9][0-9]{0,15}', value):
        raise InputError('invalid_canonical_team_id')
    return int(value.rsplit(':', 1)[1])


@dataclass(frozen=True)
class Snapshot:
    competition: str
    season: int
    fetched_at: datetime
    records: tuple[dict, ...]
    nonfinal_records: tuple[dict, ...] = ()
    snapshot_id: str = 'synthetic.json'
    retained_sha256: str | None = None
    usable: bool = True

    @property
    def url(self) -> str:
        return f'https://api.football-data.org/v4/competitions/{self.competition}/matches?season={self.season}'

    def provenance(self) -> dict:
        return {'provider': PROVIDER, 'source_url': self.url,
                'snapshot_id': self.snapshot_id, 'retained_sha256': self.retained_sha256,
                'acquired_at_utc': instant(self.fetched_at).isoformat(),
                'acquisition_timestamp_basis': 'request_start_from_original_snapshot'}


@dataclass(frozen=True)
class Dataset:
    snapshots: tuple[Snapshot, ...]
    load_issues: tuple[dict, ...] = ()


def load_snapshots(directory: str | Path) -> Dataset:
    """Load only known code-year JSON files. Never preserve raw errors/headers.

    Originals are not rewritten. Invalid/unavailable files remain explicit
    load issues; partial collections are usable with coverage diagnostics.
    """
    root = Path(directory)
    if not root.is_dir():
        raise InputError('snapshot_directory_unavailable')
    snapshots, issues = [], []
    for path in sorted(root.glob('*.json')):
        match = re.fullmatch(r'(SA|PL|PD|BL1|FL1|DED|PPL|ELC|CL)-(20[0-9]{2})\.json', path.name)
        if not match:
            continue
        code, year = match[1], int(match[2])
        try:
            if path.stat().st_size > 5_000_000:
                raise InputError('snapshot_too_large')
            raw = path.read_bytes()
            body = json.loads(raw)
            expected = f'https://api.football-data.org/v4/competitions/{code}/matches?season={year}'
            if not isinstance(body, dict) or type(body.get('schema_version')) is not int or body.get('schema_version') != 2:
                raise InputError('unsupported_snapshot_schema')
            if body.get('competition') != code or type(body.get('requested_season')) is not int or body.get('requested_season') != year or body.get('url') != expected:
                raise InputError('snapshot_identity_mismatch')
            if body.get('state') != 'retrieved' or body.get('http_status') != 200:
                raise InputError('source_unavailable')
            fetched = instant(body.get('requested_at_utc'))
            records, pending = body.get('records'), body.get('nonfinal_records')
            if not isinstance(records, list) or not isinstance(pending, list):
                raise InputError('invalid_snapshot_lists')
            snapshots.append(Snapshot(code, year, fetched, tuple(records), tuple(pending),
                                      path.name, hashlib.sha256(raw).hexdigest()))
        except InputError as error:
            issues.append({'competition': code, 'season': year, 'snapshot_id': path.name, 'code': str(error)})
        except (OSError, ValueError, TypeError):
            issues.append({'competition': code, 'season': year, 'snapshot_id': path.name, 'code': 'unreadable_snapshot'})
    return Dataset(tuple(snapshots), tuple(issues))


def _refs(row: Any) -> set[int]:
    if not isinstance(row, dict):
        return set()
    return {row[side]['id'] for side in ('home', 'away')
            if isinstance(row.get(side), dict) and positive_id(row[side].get('id'))}


def _pair(value: Any) -> dict | None:
    if not isinstance(value, dict) or any(type(value.get(k)) is not int or value[k] < 0 for k in ('home', 'away')):
        return None
    return {k: value[k] for k in ('home', 'away')}


def _normalize(row: Any, snapshot: Snapshot, pending: bool) -> dict:
    if not isinstance(row, dict) or not positive_id(row.get('match_id')):
        raise InputError('invalid_match_identity')
    home, away = row.get('home'), row.get('away')
    if not all(isinstance(t, dict) and positive_id(t.get('id')) and safe_name(t.get('name')) for t in (home, away)):
        raise InputError('invalid_team_identity')
    if home['id'] == away['id']:
        raise InputError('identical_opponents')
    when = instant(row.get('utc_date'))
    state = row.get('status')
    if not isinstance(state, str) or (state != 'FINISHED' and state not in NONFINAL):
        raise InputError('unknown_match_status')
    # Minimized non-final rows legitimately omit season/competition IDs.
    # They are retained only to diagnose exclusions, never as finished games.
    code = row.get('competition_code', snapshot.competition if pending else None)
    if code != snapshot.competition or row.get('provider', PROVIDER) != PROVIDER:
        raise InputError('competition_or_provider_mismatch')
    if row.get('source_url', snapshot.url) != snapshot.url:
        raise InputError('record_provenance_mismatch')
    record = {'match_id': row['match_id'], 'canonical_match_id': f'{PROVIDER}:match:{row["match_id"]}',
              'utc_date': when.isoformat(), 'status': state,
              'competition': {'provider': PROVIDER, 'code': code, 'id': COMPETITIONS[code]},
              'home': {'canonical_id': team_key(home['id']), 'provider_id': home['id'], 'name': home['name'].strip()},
              'away': {'canonical_id': team_key(away['id']), 'provider_id': away['id'], 'name': away['name'].strip()},
              'season': {'start_year': snapshot.season}, 'duration': None, 'score_periods': {},
              'stage': None, 'provider_updated_at': None}
    if pending and state == 'FINISHED':
        raise InputError('finished_record_in_nonfinal_collection')
    if state == 'FINISHED':
        if row.get('competition_id') != COMPETITIONS[code] or not positive_id(row.get('competition_id')):
            raise InputError('invalid_competition_identity')
        try:
            start, end = date.fromisoformat(row['season_start']), date.fromisoformat(row['season_end'])
        except (ValueError, TypeError, KeyError):
            raise InputError('incomplete_season') from None
        if not positive_id(row.get('season_id')) or type(row.get('requested_season')) is not int or row.get('requested_season') != snapshot.season or start.year != snapshot.season or end < start:
            raise InputError('invalid_season_identity')
        record['season'].update(id=row['season_id'], start_date=start.isoformat(), end_date=end.isoformat())
        duration, score = row.get('duration'), row.get('score')
        if duration not in ('REGULAR', 'EXTRA_TIME', 'PENALTY_SHOOTOUT') or not isinstance(score, dict):
            raise InputError('incomplete_score')
        periods = {}
        for key in ('fullTime', 'regularTime', 'extraTime', 'penalties'):
            if key in score:
                pair = _pair(score[key])
                if pair is None:
                    raise InputError('incomplete_score_period')
                periods[key] = pair
        if 'fullTime' not in periods or (duration != 'REGULAR' and 'regularTime' not in periods):
            raise InputError('missing_90_minute_or_final_score')
        if duration == 'REGULAR' and 'regularTime' in periods and periods['regularTime'] != periods['fullTime']:
            raise InputError('contradictory_90_minute_score')
        record.update(duration=duration, score_periods=periods,
                      score_90_minutes=periods['fullTime' if duration == 'REGULAR' else 'regularTime'])
        stage = row.get('stage')
        if stage is not None and (not isinstance(stage, str) or not re.fullmatch('[A-Z0-9_]{1,60}', stage)):
            raise InputError('invalid_stage')
        record['stage'] = stage
        updated = row.get('provider_updated_at')
        if updated is not None:
            record['provider_updated_at'] = instant(updated).isoformat()
    record['provenance'] = [{**snapshot.provenance(),
                             'response_record_index': row.get('response_record_index')
                             if type(row.get('response_record_index')) is int and row['response_record_index'] >= 0 else None}]
    return record


def _fingerprint(record: dict) -> str:
    value = {k: record[k] for k in ('utc_date', 'status', 'competition', 'season', 'duration', 'score_periods', 'stage')}
    value.update(home_id=record['home']['provider_id'], away_id=record['away']['provider_id'])
    return json.dumps(value, sort_keys=True)


def _statistics(rows: list[dict]) -> dict:
    counts = Counter(row['result_90_minutes'] for row in rows)
    played = len(rows)
    gf, ga = sum(r['goals_for_90_minutes'] for r in rows), sum(r['goals_against_90_minutes'] for r in rows)
    points = 3 * counts['W'] + counts['D']
    return {'played': played, 'wins': counts['W'], 'draws': counts['D'], 'losses': counts['L'],
            'goals_for': gf, 'goals_against': ga,
            'average_goals_for': round(gf / played, 4) if played else None,
            'average_goals_against': round(ga / played, 4) if played else None,
            'points_90_minutes_3_1_0': points,
            'points_per_game': round(points / played, 4) if played else None}


def build_history(dataset: Dataset, *, team_id: str, competitions: list[str],
                  event_kickoff: str | datetime, verified_at: str | datetime,
                  display_timezone: str = 'UTC', max_source_age_hours: float = 24) -> dict:
    """Return five fresh terminal games, statistics and separate quality issues.

    No name matching. Identical IDs with conflicting fields fail closed, even
    when one variant is incomplete. Statistics describe the selected sample
    at 90 minutes, including draws in games subsequently decided on penalties.
    """
    identity = resolve_team(team_id)
    if not isinstance(competitions, (list, tuple)) or not competitions or any(not isinstance(code, str) or code not in COMPETITIONS for code in competitions):
        raise InputError('invalid_competition_scope')
    scope = sorted(set(competitions))
    event, verified = instant(event_kickoff), instant(verified_at)
    anchor = min(event, verified)
    try:
        zone = ZoneInfo(display_timezone)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise InputError('invalid_display_timezone') from None
    if isinstance(max_source_age_hours, bool) or not isinstance(max_source_age_hours, (float, int)) or not math.isfinite(max_source_age_hours) or max_source_age_hours <= 0:
        raise InputError('invalid_source_age_threshold')
    snapshots = [s for s in dataset.snapshots if s.competition in scope]
    relevant_keys = {row['match_id'] for snap in snapshots
                     for row in snap.records + snap.nonfinal_records
                     if identity in _refs(row) and positive_id(row.get('match_id'))}
    names, candidates, tainted = set(), defaultdict(list), set()
    issues = {'identity': [], 'incomplete': [], 'conflicts': [], 'sources': [],
              'duplicate_records': 0, 'name_aliases': [], 'nonfinal_status_counts': {},
              'exclusions': {}, 'load': [i for i in dataset.load_issues if i.get('competition') in scope]}
    excluded, statuses, occurrences = Counter(), Counter(), Counter()
    sources = []
    for snap in snapshots:
        fetched = instant(snap.fetched_at)
        age = (verified - fetched).total_seconds() / 3600
        problems = []
        if not snap.usable:
            problems.append('source_unavailable')
        if fetched > verified:
            problems.append('source_after_verification')
        if age > max_source_age_hours:
            problems.append('stale_source')
        if fetched > event:
            problems.append('post_event_acquisition')
        sources.append({**snap.provenance(), 'competition': snap.competition,
                        'season': snap.season, 'age_hours_at_verification': round(age, 6),
                        'issues': problems})
        for problem in problems:
            issues['sources'].append({'snapshot_id': snap.snapshot_id, 'code': problem})
        for pending, rows in ((False, snap.records), (True, snap.nonfinal_records)):
            for index, row in enumerate(rows):
                if identity not in _refs(row) and (not isinstance(row, dict) or not positive_id(row.get('match_id')) or row['match_id'] not in relevant_keys):
                    continue
                # Team ID is exact; names are descriptive labels only.
                for side in ('home', 'away'):
                    team = row.get(side)
                    if isinstance(team, dict) and team.get('id') == identity and safe_name(team.get('name')):
                        names.add(team['name'].strip())
                if not snap.usable or fetched > verified:
                    excluded['source_unavailable_or_future'] += 1
                    continue
                key = row.get('match_id')
                if positive_id(key):
                    occurrences[key] += 1
                try:
                    normalized = _normalize(row, snap, pending)
                    candidates[normalized['match_id']].append(normalized)
                except InputError as error:
                    reason = str(error)
                    category = 'identity' if reason in {'invalid_match_identity', 'invalid_team_identity', 'identical_opponents', 'invalid_competition_identity', 'invalid_season_identity', 'competition_or_provider_mismatch'} else 'incomplete'
                    issues[category].append({'code': reason, 'match_id': key if positive_id(key) else None,
                                             'snapshot_id': snap.snapshot_id, 'retained_record_index': index})
                    excluded[category + '_record'] += 1
                    if positive_id(key):
                        tainted.add(key)
    for code in scope:
        if not any(s.competition == code for s in snapshots):
            issues['sources'].append({'competition': code, 'code': 'missing_competition_snapshot'})
    issues['duplicate_records'] = sum(count - 1 for count in occurrences.values())
    eligible, before_freshness = [], 0
    for key, variants in candidates.items():
        fingerprints = {_fingerprint(row) for row in variants}
        if len(fingerprints) > 1 or key in tainted:
            issues['conflicts'].append({'match_id': key, 'code': 'conflicting_record_variants'})
            excluded['conflicting_match'] += 1
            continue
        record = dict(variants[0])
        # Keep distinct acquisitions/indices when collapsing identical games.
        provenance = {json.dumps(p, sort_keys=True): p for v in variants for p in v['provenance']}
        record['provenance'] = [provenance[k] for k in sorted(provenance)]
        updates = [v['provider_updated_at'] for v in variants if v['provider_updated_at']]
        record['provider_updated_at'] = max(updates) if updates else None
        if record['status'] != 'FINISHED':
            statuses[record['status']] += 1
            if record['status'] in {'SCHEDULED', 'TIMED', 'IN_PLAY', 'PAUSED'} and (verified - instant(record['utc_date'])) > timedelta(hours=6):
                issues['sources'].append({'match_id': key, 'code': 'overdue_nonfinal_heuristic'})
            continue
        when = instant(record['utc_date'])
        future = False
        if when >= event:
            excluded['at_or_after_event_kickoff'] += 1
            future = True
        if when >= verified:
            excluded['at_or_after_verification'] += 1
            future = True
        if future:
            continue
        if record['provider_updated_at'] and instant(record['provider_updated_at']) > verified:
            excluded['provider_update_after_verification'] += 1
            continue
        before_freshness += 1
        if anchor - when > timedelta(days=180):
            excluded['older_than_180_days'] += 1
            continue
        side = 'home' if record['home']['provider_id'] == identity else 'away'
        other = 'away' if side == 'home' else 'home'
        score = record['score_90_minutes']
        gf, ga = score[side], score[other]
        record.update(team_id=team_id, venue=side, opponent=record[other],
                      date_local=when.astimezone(zone).isoformat(),
                      goals_for_90_minutes=gf, goals_against_90_minutes=ga,
                      result_90_minutes='W' if gf > ga else 'L' if gf < ga else 'D')
        eligible.append(record)
    eligible.sort(key=lambda r: (instant(r['utc_date']), r['match_id']), reverse=True)
    selected = eligible[:5]
    issues['exclusions'] = dict(sorted(excluded.items()))
    issues['nonfinal_status_counts'] = dict(sorted(statuses.items()))
    issues['name_aliases'] = sorted(names) if len(names) > 1 else []
    observed = bool(names)
    history_status = 'sufficient_history' if len(selected) == 5 else 'insufficient_history'
    source_codes = {i['code'] for i in issues['sources']}
    if not observed:
        status = 'identity_unresolved'
    elif len(selected) < 5:
        status = 'insufficient_history'
    elif issues['conflicts'] or issues['identity'] or issues['incomplete'] or issues['load'] or source_codes - {'stale_source'}:
        status = 'review_required'
    elif 'stale_source' in source_codes:
        status = 'stale_source'
    else:
        status = 'verified_sample'
    return {'schema_version': 'history-provider-v2.prototype.1', 'mode': 'offline_snapshots',
            'status': status, 'history_status': history_status,
            'team': {'canonical_id': team_id, 'provider': PROVIDER, 'provider_id': identity,
                     'observed_names': sorted(names), 'identity_status': 'exact_provider_id' if observed else 'unresolved',
                     'cross_provider_mapping_verified': False},
            'scope': {'requested_competitions': scope,
                      'observed_competitions': sorted({r['competition']['code'] for r in eligible}),
                      'all_competitions_complete': False,
                      'dataset_completeness_independently_verified': False},
            'temporal_policy': {'event_kickoff_utc': event.isoformat(), 'verified_at_utc': verified.isoformat(),
                                'effective_cutoff_utc': anchor.isoformat(), 'upper_bound': 'exclusive',
                                'freshness_days': 180, 'freshness_lower_bound': 'inclusive',
                                'display_timezone': display_timezone,
                                'match_time_basis': 'kickoff; FINISHED observed in saved snapshot',
                                'exact_finished_at_available': False,
                                'historical_publication_time_certified': False,
                                'max_source_age_hours': max_source_age_hours},
            'counts': {'requested_results': 5, 'valid_results_before_freshness': before_freshness,
                       'valid_results_within_180_days': len(eligible), 'selected_results': len(selected)},
            'statistics': {'criterion': '90_minutes; selected sample only; shootouts excluded; 3/1/0 descriptive points',
                           'sample_complete': len(selected) == 5,
                           'overall': _statistics(selected),
                           'home': _statistics([r for r in selected if r['venue'] == 'home']),
                           'away': _statistics([r for r in selected if r['venue'] == 'away'])},
            'matches': selected, 'sources': sources, 'diagnostics': issues}
