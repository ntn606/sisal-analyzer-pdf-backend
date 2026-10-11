"""Studio football-data.org Free isolato: niente import o scritture del backend.

Token soltanto da variabile protetta, HTTPS senza redirect, campi minimizzati,
cache di successi, budget 10/min e header quota documentati. Nessun retry di
errori di piano/auth/quota. Massimo 18 GET: nove stagioni attuali e, quando
necessario, una stagione precedente per competizione.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
COMPETITIONS = {'SA': 'Serie A', 'PL': 'Premier League', 'PD': 'LaLiga',
                'BL1': 'Bundesliga', 'FL1': 'Ligue 1', 'DED': 'Eredivisie',
                'PPL': 'Primeira Liga', 'ELC': 'EFL Championship', 'CL': 'UEFA Champions League'}
SCHEMA_VERSION = 2
STATUSES = {'SCHEDULED', 'TIMED', 'IN_PLAY', 'PAUSED', 'FINISHED', 'SUSPENDED',
            'POSTPONED', 'CANCELLED', 'AWARDED'}


def positive_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def goal(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def regulation_score(record):
    """Gol a 90 minuti, espliciti: mai fullTime con shootout né sottrazioni."""
    period = 'fullTime' if record.get('duration')=='REGULAR' else 'regularTime'
    pair = record.get('score',{}).get(period)
    if not isinstance(pair,dict) or any(goal(pair.get(k)) is None for k in ('home','away')):
        return None
    return {'home':pair['home'],'away':pair['away']}


def numeric_headers(headers):
    result = {}
    for name, field in [('X-RequestsAvailable', 'remaining_requests'),
                        ('X-Requests-Available-Minute', 'remaining_requests'),
                        ('X-RequestCounter-Reset', 'counter_reset_seconds'),
                        ('Retry-After', 'retry_after_seconds')]:
        value = headers.get(name) if headers else None
        if isinstance(value, str) and value.isascii() and value.isdigit():
            parsed = int(value)
            result[field] = min(parsed,result[field]) if field=='remaining_requests' and field in result else parsed
    # Non conserva X-Authenticated-Client, nomi utente, cookie o header auth.
    return result


def normalize(row, code, requested_season, cutoff):
    try:
        if row['status'] != 'FINISHED' or row['competition']['code'] != code:
            return None, 'non_final_or_wrong_competition'
        when = datetime.fromisoformat(row['utcDate'].replace('Z', '+00:00'))
        if when.tzinfo is None or when >= cutoff:
            return None, 'future_or_invalid_date'
        home, away, season, score = row['homeTeam'], row['awayTeam'], row['season'], row['score']
        if not all(positive_id(x) for x in (row['id'], row['competition']['id'], home['id'], away['id'], season['id'])):
            return None, 'invalid_identity'
        if home['id'] == away['id'] or any(not isinstance(t['name'], str) or not t['name'].strip() for t in (home, away)):
            return None, 'invalid_identity'
        year = datetime.fromisoformat(season['startDate']).year
        if year != requested_season:
            return None, 'unexpected_season'
        duration = score.get('duration')
        if duration not in ('REGULAR', 'EXTRA_TIME', 'PENALTY_SHOOTOUT'):
            return None, 'unknown_score_duration'
        periods = {}
        for period in ('fullTime', 'regularTime', 'extraTime', 'penalties'):
            value = score.get(period)
            if isinstance(value, dict):
                pair = [goal(value.get('home')), goal(value.get('away'))]
                if None not in pair:
                    periods[period] = {'home': pair[0], 'away': pair[1]}
        if 'fullTime' not in periods:
            return None, 'missing_final_score'
        if duration!='REGULAR' and 'regularTime' not in periods:
            return None, 'missing_regular_time_score'
        # Conserva durata e periodi: non somma rigori ai gol né ricostruisce
        # per differenza periodi assenti. Il significato è quello del provider.
        return {'match_id': row['id'], 'utc_date': when.isoformat(), 'status': 'FINISHED',
                'competition_code': code, 'competition_id': row['competition']['id'],
                'season_id': season['id'], 'season_start': season['startDate'],
                'season_end': season.get('endDate'), 'requested_season': requested_season,
                'stage': row.get('stage'), 'matchday': row.get('matchday'),
                'home': {'id': home['id'], 'name': home['name']},
                'away': {'id': away['id'], 'name': away['name']},
                'score': periods, 'duration': duration,
                'provider_updated_at': row.get('lastUpdated'), 'provider': 'football-data.org'}, None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None, 'invalid_record_schema'


def histories(records, cutoff, team_ids=None):
    unique, conflicts, duplicate_count, excluded_score_basis_count = {}, set(), 0, 0
    for row in records:
        key = row['match_id']
        if key in unique:
            # Provenienze e aggiornamenti diversi non creano un conflitto;
            # squadre/score/data/stagione/competizione discordanti sì.
            fields = ('utc_date', 'home', 'away', 'score', 'duration', 'season_id', 'competition_code')
            if any(unique[key][f] != row[f] for f in fields):
                conflicts.add(key)
            duplicate_count += 1
        else:
            unique[key] = row
    grouped = defaultdict(list)
    for key, row in unique.items():
        if key in conflicts:
            continue
        pair = regulation_score(row)
        if pair is None:
            excluded_score_basis_count += 1
            continue
        for side in ('home', 'away'):
            team = row[side]
            other = row['away' if side == 'home' else 'home']
            grouped[team['id']].append({**row, 'team_id': team['id'], 'team': team['name'],
                                       'opponent_id': other['id'], 'opponent': other['name'],
                                       'venue': side, 'goals_for': pair[side],
                                       'goals_basis': '90_minutes',
                                       'goals_against': pair['away' if side == 'home' else 'home']})
    for rows in grouped.values():
        rows.sort(key=lambda x: x['utc_date'], reverse=True)
    if team_ids is None:
        team_ids = sorted(grouped, key=lambda k: (-len(grouped[k]), grouped[k][0]['team']))[:2]
    teams = []
    for key in team_ids:
        rows = grouped.get(key, [])
        recent = [x for x in rows if cutoff - datetime.fromisoformat(x['utc_date']) <= timedelta(days=180)]
        teams.append({'team_id': key, 'team': rows[0]['team'] if rows else None,
                      'valid_unique_records_available': len(rows),
                      'valid_records_last_180_days': len(recent), 'sample_size': min(5, len(rows)),
                      'sample': rows[:5], 'five_observed': len(rows) >= 5,
                      'previous_season_in_sample': any(x['requested_season'] < cutoff.year for x in rows[:5]),
                      'verified_five_recent': len(recent) >= 5,
                      'newest_available_utc': rows[0]['utc_date'] if rows else None,
                      'oldest_available_utc': rows[-1]['utc_date'] if rows else None,
                      'sample_newest_utc': rows[0]['utc_date'] if rows else None,
                      'sample_oldest_utc': rows[min(5,len(rows))-1]['utc_date'] if rows else None,
                      'sample_home_count': sum(x['venue']=='home' for x in rows[:5]),
                      'sample_away_count': sum(x['venue']=='away' for x in rows[:5]),
                      'observed_team_names': sorted({x['team'] for x in rows}),
                      'all_competitions_complete': False})
    return {'teams': teams, 'duplicate_records': duplicate_count,
            'excluded_score_basis_count':excluded_score_basis_count,
            'conflicting_match_ids': sorted(conflicts)}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise urllib.error.URLError('redirect_rejected')


class Client:
    def __init__(self, token, cutoff, output, now=time.monotonic, sleep=time.sleep):
        self.token, self.cutoff, self.output = token, cutoff, output
        self.now, self.sleep, self.next_call = now, sleep, 0
        self.calls = 0
        self.stopped = None
        self.opener = urllib.request.build_opener(NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def matches(self, code, season):
        if code not in COMPETITIONS:
            return {'state': 'competition_not_allowed'}
        if not self.token:
            return {'state': 'not_run_missing_token', 'network_calls': 0}
        if self.stopped:
            return {'state': 'not_run_after_' + self.stopped}
        path = self.output / f'{code}-{season}.json'
        if path.exists():
            cached = json.loads(path.read_text())
            try:
                age = self.cutoff - datetime.fromisoformat(cached['cutoff_utc'])
                if cached.get('schema_version') == SCHEMA_VERSION and cached.get('state') == 'retrieved' and timedelta(0) <= age <= timedelta(minutes=15):
                    return cached
            except (KeyError, ValueError, TypeError):
                pass
        if self.calls >= 18:
            return {'state': 'local_budget_exhausted'}
        delay = max(0, self.next_call - self.now())
        if delay > 120:
            self.stopped = 'quota_wait_exceeds_budget'
            return {'state': 'not_run_after_' + self.stopped}
        while delay > 0:
            self.sleep(min(delay, 10))
            delay = max(0, self.next_call - self.now())
        # Una richiesta per stagione, senza filtro stato: permette di
        # osservare rinvii e gare passate non finali senza richieste aggiuntive.
        url = f'https://api.football-data.org/v4/competitions/{code}/matches?season={season}'
        result = {'url': url, 'competition': code, 'requested_season': season,
                  'schema_version': SCHEMA_VERSION,
                  'cutoff_utc': self.cutoff.isoformat(),
                  'requested_at_utc': datetime.now(timezone.utc).isoformat()}
        self.calls += 1
        self.next_call = self.now() + 6.2
        try:
            request = urllib.request.Request(url, headers={'X-Auth-Token': self.token})
            with self.opener.open(request, timeout=25) as response:
                result.update(http_status=response.status, quota=numeric_headers(response.headers))
                raw = response.read(5_000_001)
            if len(raw) > 5_000_000:
                raise ValueError('response_too_large')
            body = json.loads(raw)
            if not isinstance(body, dict) or not isinstance(body.get('matches'), list):
                raise ValueError('invalid_match_list')
            records, rejects, status_counts, nonfinal = [], defaultdict(int), defaultdict(int), []
            for index, row in enumerate(body['matches']):
                status = row.get('status') if isinstance(row, dict) else None
                status_counts[status if status in STATUSES else 'UNKNOWN'] += 1
                if status in STATUSES and status != 'FINISHED':
                    try:
                        when = datetime.fromisoformat(row['utcDate'].replace('Z','+00:00'))
                        valid_identity = all(positive_id(x) for x in (row['id'], row['homeTeam']['id'], row['awayTeam']['id']))
                        valid_identity = valid_identity and row['homeTeam']['id'] != row['awayTeam']['id']
                        valid_identity = valid_identity and all(isinstance(row[s]['name'],str) and row[s]['name'].strip() for s in ('homeTeam','awayTeam'))
                        valid_identity = valid_identity and datetime.fromisoformat(row['season']['startDate']).year == season
                        if when.tzinfo and valid_identity and row['competition']['code']==code:
                            nonfinal.append({'match_id': row['id'], 'utc_date': when.isoformat(), 'status': status,
                                             'home': {k:row['homeTeam'][k] for k in ('id','name')},
                                             'away': {k:row['awayTeam'][k] for k in ('id','name')},
                                             'overdue_nonfinal': status in ('SCHEDULED','TIMED','IN_PLAY','PAUSED') and cutoff_delta(self.cutoff,when)>21600})
                    except (KeyError,TypeError,ValueError,AttributeError):
                        pass
                record, reason = normalize(row, code, season, self.cutoff)
                if record is None:
                    rejects[reason] += 1
                else:
                    record.update(source_url=url, response_record_index=index)
                    records.append(record)
            result.update(state='retrieved', raw_match_count=len(body['matches']),
                          rejected=dict(rejects), records=records,
                          status_counts=dict(status_counts), nonfinal_records=nonfinal,
                          api_reported_count=(body.get('resultSet') or {}).get('count') if isinstance((body.get('resultSet') or {}).get('count'),int) and not isinstance((body.get('resultSet') or {}).get('count'),bool) else None,
                          sha256_raw_response=hashlib.sha256(raw).hexdigest())
        except urllib.error.HTTPError as error:
            result.update(http_status=error.code, quota=numeric_headers(error.headers),
                          state={401: 'authentication_failed', 403: 'access_restricted',
                                 429: 'rate_limited'}.get(error.code, 'provider_http_error'))
            if error.code in (401, 429):
                self.stopped = result['state']
            # Non legge il body, non conserva error.reason o header originali.
        except urllib.error.URLError:
            result.update(state='transport_error')
            self.stopped = 'transport_error'
        except (ValueError, TypeError, AttributeError, TimeoutError):
            result.update(state='invalid_response_or_timeout')
        quota = result.get('quota', {})
        if quota.get('retry_after_seconds') is not None:
            self.next_call = max(self.next_call, self.now() + quota['retry_after_seconds'] + 1)
        if quota.get('remaining_requests') == 0:
            reset = max(quota.get('counter_reset_seconds', 60), quota.get('retry_after_seconds', 0))
            self.next_call = max(self.next_call, self.now() + reset + 1)
        serialized = json.dumps(result, ensure_ascii=False, indent=2)
        if self.token in serialized:
            result = {'state': 'sensitive_payload_rejected', 'competition': code}
            serialized = json.dumps(result)
        self.output.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized + '\n')
        return result


def run(token, cutoff, output):
    client = Client(token, cutoff, output)
    result = {'cutoff_utc': cutoff.isoformat(), 'token_available': bool(token),
              'coverage': [], 'source': 'football-data.org'}
    for code, name in COMPETITIONS.items():
        current = client.matches(code, cutoff.year)
        records = list(current.get('records', []))
        evaluated = histories(records, cutoff)
        tested = [x['team_id'] for x in evaluated['teams']]
        if not tested and current['state']=='retrieved':
            # Le squadre vengono dal calendario corrente effettivamente
            # restituito, così la stagione precedente non seleziona ex membri.
            current_teams = {}
            for event in current.get('nonfinal_records',[]):
                for side in ('home','away'):
                    team = event[side]
                    if isinstance(team.get('name'),str) and team['name'].strip():
                        current_teams[team['id']] = team['name']
            tested = sorted(current_teams, key=lambda k:current_teams[k])[:2]
            evaluated = histories(records,cutoff,tested)
            for team in evaluated['teams']:team['team']=current_teams[team['team_id']]
        probes = [{'season': cutoff.year, 'state': current['state']}]
        if current['state'] == 'retrieved' and (len(tested) < 2 or any(x['sample_size'] < 5 for x in evaluated['teams'])):
            previous = client.matches(code, cutoff.year - 1)
            probes.append({'season': cutoff.year - 1, 'state': previous['state']})
            records += previous.get('records', [])
            evaluated = histories(records, cutoff, tested or None)
        result['coverage'].append({'competition': code, 'name': name, 'probes': probes, **evaluated,
                                   'access_verified': current['state'] == 'retrieved',
                                   'current_season_team_membership_verified': bool(tested),
                                   'current_season_state': current['state']})
        print(code, current['state'], [x['sample_size'] for x in evaluated['teams']], flush=True)
    result['network_calls'] = client.calls
    output.mkdir(parents=True, exist_ok=True)
    (output / 'coverage.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def cutoff_delta(cutoff,when):
    return (cutoff-when).total_seconds()


if __name__ == '__main__':
    run(os.environ.get('FOOTBALL_DATA_TOKEN'), datetime.now(timezone.utc), ROOT / 'evidence')
