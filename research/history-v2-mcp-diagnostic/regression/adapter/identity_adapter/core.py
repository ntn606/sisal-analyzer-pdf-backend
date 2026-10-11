"""Fail-closed cross-provider identities and diagnostic histories.

Registry and evidence are trusted local configuration, NOT MCP client input.
Simulation evidence never establishes a real cross-provider mapping.
"""
from copy import deepcopy
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, parse_qs, urljoin
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from history_provider_v2 import Dataset, build_history
from history_provider_v2.provider import COMPETITIONS, InputError, instant, positive_id

VERSION = 'history-identity-adapter.1'
KINDS = {'review', 'sisal_event', 'api_football_fixture', 'api_football_history', 'result_observation'}
SISAL_QUOTE_PAGE = 'https://www.sisal.it/scommesse-matchpoint/foglio-quote'
SISAL_LANDING_PDF_PATHS = frozenset({
    '/volantini/Scommesse_Sport/Quote/calcio%20base%20per%20data.pdf',
    '/volantini/Scommesse_Sport/Quote/calcio%20base%20per%20manifestazione.pdf',
    '/volantini/Scommesse_Sport/Quote/calcio%20base%20per%20manifestazione%20TOP.pdf',
})


def _score_pair(value):
    return isinstance(value, dict) and set(value) == {'home', 'away'} and all(type(value[k]) is int and value[k] >= 0 for k in value)


def read_json(path):
    try:
        path = Path(path)
        if path.stat().st_size > 5_000_000:
            raise InputError('local_file_too_large')
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict):
            raise InputError('invalid_local_document')
        return value
    except InputError:
        raise
    except (OSError, ValueError, TypeError):
        raise InputError('local_document_unavailable_or_invalid') from None


def _public_source(value, kind, origin):
    if not isinstance(value, str):
        return False
    if origin == 'synthetic':
        return bool(re.fullmatch(r'urn:synthetic:[a-z0-9:-]{1,100}', value))
    if kind == 'review':
        return bool(re.fullmatch(r'urn:local:review:[a-z0-9:-]{1,100}', value))
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or '\\' in value or '#' in value:
        return False
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or parsed.username is not None or parsed.password is not None
                or parsed.fragment or parsed.port not in (None, 443) or not parsed.hostname
                or parsed.netloc.lower() not in (parsed.hostname, parsed.hostname + ':443')):
            return False
    except ValueError:
        return False
    if kind in ('api_football_fixture', 'api_football_history'):
        return (parsed.hostname == 'v3.football.api-sports.io' and parsed.path == '/fixtures'
                and set(parse_qs(parsed.query)) == {'id'}
                and bool(re.fullmatch(r'id=[1-9][0-9]*', parsed.query)))
    if kind == 'result_observation':
        return (parsed.hostname == 'api.football-data.org' and not parsed.query
                and bool(re.fullmatch(r'/v4/matches/[1-9][0-9]*', parsed.path)))
    if kind != 'sisal_event' or parsed.query or '?' in value:
        return False
    if parsed.hostname == 'landing.sisal.it':
        return parsed.path in SISAL_LANDING_PDF_PATHS
    return parsed.hostname in ('www.sisal.it', 'sisal.it') and parsed.path.lower().endswith('.pdf')


class _DocumentLinks(HTMLParser):
    """Use only actual href links from the archived official quote page."""
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attributes):
        if tag == 'a':
            links = [value for key, value in attributes if key == 'href']
            if len(links) == 1 and links[0]:
                self.links.add(urljoin(SISAL_QUOTE_PAGE, links[0]))


class EvidenceStore:
    def __init__(self, registry, directory, mode, verified):
        self.entries = registry.get('evidence', {})
        if not isinstance(self.entries, dict):
            raise InputError('invalid_evidence_registry')
        self.root, self.mode, self.verified = Path(directory).resolve(), mode, verified
        self.cache = {}

    def _attached_file(self, reference):
        if (not isinstance(reference, dict) or not isinstance(reference.get('file'), str)
                or Path(reference['file']).is_absolute()
                or not isinstance(reference.get('sha256'), str)
                or not re.fullmatch('[0-9a-f]{64}', reference.get('sha256', ''))):
            raise InputError('invalid_document_reference')
        path = (self.root / reference['file']).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise InputError('document_path_outside_root')
        try:
            if path.stat().st_size > 5_000_000:
                raise InputError('document_too_large')
            raw = path.read_bytes()
        except OSError:
            raise InputError('document_unavailable') from None
        if hashlib.sha256(raw).hexdigest() != reference['sha256']:
            raise InputError('document_hash_mismatch')
        return raw

    def _validate_landing_pdf(self, payload):
        document = payload.get('document')
        if not isinstance(document, dict) or document.get('media_type') != 'application/pdf':
            raise InputError('missing_or_invalid_sisal_pdf_document')
        pdf = self._attached_file(document)
        if not re.match(rb'%PDF-[12]\.[0-9]', pdf) or b'%%EOF' not in pdf[-1024:]:
            raise InputError('invalid_pdf_signature')
        page = document.get('landing_page')
        if (not isinstance(page, dict) or page.get('source') != SISAL_QUOTE_PAGE
                or page.get('media_type') != 'text/html'):
            raise InputError('invalid_sisal_pdf_provenance_page')
        if instant(page.get('acquired_at')) > instant(payload.get('acquired_at')):
            raise InputError('sisal_page_acquired_after_pdf_evidence')
        raw_page = self._attached_file(page)
        try:
            parser = _DocumentLinks()
            parser.feed(raw_page.decode('utf-8'))
        except (UnicodeError, ValueError):
            raise InputError('invalid_sisal_provenance_html') from None
        if payload['source'] not in parser.links:
            raise InputError('sisal_pdf_not_linked_from_official_page')

    def get(self, key, kind=None):
        if not isinstance(key, str) or key not in self.entries:
            raise InputError('missing_evidence')
        if key not in self.cache:
            entry = self.entries[key]
            if not isinstance(entry, dict) or not isinstance(entry.get('file'), str) or not re.fullmatch('[0-9a-f]{64}', entry.get('sha256', '')):
                raise InputError('invalid_evidence_reference')
            path = (self.root / entry['file']).resolve()
            if not path.is_relative_to(self.root) or path == self.root:
                raise InputError('evidence_path_outside_root')
            try:
                if path.stat().st_size > 5_000_000:
                    raise InputError('evidence_too_large')
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                    raise InputError('evidence_hash_mismatch')
                payload = json.loads(raw)
            except InputError:
                raise
            except (OSError, ValueError, TypeError):
                raise InputError('unreadable_evidence') from None
            if not isinstance(payload, dict) or payload.get('origin') not in ('real_saved', 'synthetic'):
                raise InputError('invalid_evidence_origin')
            if not isinstance(payload.get('kind'), str) or payload['kind'] not in KINDS or not isinstance(payload.get('record'), dict):
                raise InputError('invalid_evidence_kind_or_record')
            if self.mode == 'real_only' and payload['origin'] != 'real_saved':
                raise InputError('synthetic_evidence_not_accepted')
            if instant(payload.get('acquired_at')) > self.verified:
                raise InputError('evidence_after_verification')
            if not _public_source(payload.get('source'), payload.get('kind'), payload['origin']):
                raise InputError('untrusted_or_sensitive_evidence_source')
            if (payload['origin'] == 'real_saved' and payload['kind'] == 'sisal_event'
                    and urlsplit(payload['source']).hostname == 'landing.sisal.it'):
                self._validate_landing_pdf(payload)
            self.cache[key] = payload
        payload = self.cache[key]
        if kind is not None and payload.get('kind') != kind:
            raise InputError('wrong_evidence_kind')
        return payload

    def verified_entry(self, entry, entry_kind, kickoff):
        verification = entry.get('verification', {})
        if not isinstance(verification, dict) or verification.get('state') != 'verified':
            raise InputError('mapping_not_verified')
        if instant(verification.get('reviewed_at')) > self.verified:
            raise InputError('review_after_verification')
        review = self.get(verification.get('evidence_id'), 'review')
        if (not isinstance(review.get('record'), dict)
                or review['record'].get('reviewed_at') != verification.get('reviewed_at')
                or not isinstance(review['record'].get('reviewer_ref'), str)
                or not re.fullmatch(r'[a-z0-9-]{1,80}', review['record']['reviewer_ref'])):
            raise InputError('missing_explicit_review')
        reviewed = {k: v for k, v in entry.items() if k != 'verification'}
        if {'entry_kind': entry_kind, 'value': reviewed} not in review.get('record', {}).get('entries', []):
            raise InputError('mapping_not_in_review_evidence')
        period = entry.get('validity', {})
        if instant(period.get('from')) > kickoff or kickoff >= instant(period.get('until')):
            raise InputError('mapping_outside_validity')

    def provenance(self):
        return [{'evidence_id': key, 'sha256': self.entries[key]['sha256'], 'kind': value['kind'],
                 'origin': value['origin'], 'source': value['source'],
                 'acquired_at': instant(value['acquired_at']).isoformat()}
                for key, value in sorted(self.cache.items())]


def sisal_kickoff(event):
    """Resolve a local wall-clock date; reject gaps and unqualified DST folds."""
    try:
        wall = datetime.fromisoformat(event['date'] + 'T' + event['time'])
        if wall.tzinfo is not None:
            raise InputError('sisal_wall_time_must_be_local')
        zone = ZoneInfo(event['timezone'])
        candidates = {}
        for fold in (0, 1):
            local = wall.replace(tzinfo=zone, fold=fold)
            utc = local.astimezone(timezone.utc)
            if utc.astimezone(zone).replace(tzinfo=None) == wall:
                candidates[utc] = local
        if not candidates:
            raise InputError('nonexistent_local_time')
        if event.get('utc_offset') is not None:
            candidates = {utc: local for utc, local in candidates.items()
                          if local.isoformat().endswith(event['utc_offset'])}
        if len(candidates) != 1:
            raise InputError('ambiguous_or_inconsistent_local_time')
        return next(iter(candidates))
    except InputError:
        raise
    except (KeyError, ValueError, TypeError, ZoneInfoNotFoundError):
        raise InputError('invalid_sisal_time') from None


def _fd_event(dataset, match_id, verified):
    variants = []
    for snap in dataset.snapshots:
        if not snap.usable or instant(snap.fetched_at) > verified:
            continue
        for row in snap.records + snap.nonfinal_records:
            if isinstance(row, dict) and positive_id(row.get('match_id')) and row.get('match_id') == match_id:
                try:
                    if (row.get('competition_code', snap.competition) != snap.competition
                            or row.get('requested_season', snap.season) != snap.season
                            or row.get('competition_id', COMPETITIONS[snap.competition]) != COMPETITIONS[snap.competition]):
                        raise InputError('invalid_provider_event')
                    if not all(positive_id(row[s]['id']) for s in ('home', 'away')):
                        raise InputError('invalid_provider_event')
                    variants.append({'match_id': match_id, 'home_team_id': row['home']['id'],
                                     'away_team_id': row['away']['id'], 'kickoff_utc': instant(row['utc_date']).isoformat(),
                                     'competition_id': COMPETITIONS[snap.competition], 'competition_code': snap.competition,
                                     'season_start_year': snap.season, 'snapshot_id': snap.snapshot_id,
                                     'source_sha256': snap.retained_sha256})
                except (KeyError, TypeError, InputError):
                    raise InputError('invalid_provider_event') from None
    if not variants:
        raise InputError('football_data_event_unavailable')
    fields = ('home_team_id', 'away_team_id', 'kickoff_utc', 'competition_id', 'competition_code', 'season_start_year')
    if len({tuple(v[f] for f in fields) for v in variants}) != 1:
        raise InputError('conflicting_provider_event')
    return variants[0]


def _valid_alias(team, provider, label, local_date):
    today = datetime.fromisoformat(local_date).date()
    for alias in team.get('aliases', []):
        if (alias.get('provider') == provider and alias.get('label') == label
                and datetime.fromisoformat(alias['valid_from']).date() <= today <= datetime.fromisoformat(alias['valid_until']).date()):
            return True
    return False


def _profile(profile):
    return (isinstance(profile, dict) and set(profile) == {'country', 'gender', 'squad_kind', 'age_group'}
            and bool(re.fullmatch('[A-Z]{2}', profile.get('country', '')))
            and profile.get('gender') in ('men', 'women') and profile.get('squad_kind') in ('first', 'reserve', 'youth')
            and profile.get('age_group') in ('senior', 'U23', 'U21', 'U19', 'U18', 'U17'))


def _team_check(registry, binding, side, event, af, fd, store, kickoff):
    result = {'identity_verified': False, 'state': 'identity_unverified', 'canonical_id': None, 'reasons': []}
    desired = binding[side + '_canonical_id']
    if not isinstance(desired, str) or not re.fullmatch(r'local:team:[a-z0-9-]{1,64}', desired):
        result['reasons'].append('invalid_canonical_team_id')
        return result
    candidates = [t for t in registry.get('teams', []) if t.get('canonical_id') == desired]
    if len(candidates) != 1:
        result.update(state='identity_ambiguous' if len(candidates) > 1 else 'identity_unverified', reasons=['canonical_mapping_missing_or_ambiguous'])
        return result
    team = candidates[0]
    try:
        store.verified_entry(team, 'team', kickoff)
        ids = team['provider_ids']
        for provider, field in (('api_football', 'api_football'), ('football_data', 'football_data')):
            if not positive_id(ids.get(field)):
                raise InputError('invalid_provider_team_id')
            if sum(t.get('provider_ids', {}).get(field) == ids[field] for t in registry.get('teams', [])) != 1:
                result['state'] = 'identity_ambiguous'
                raise InputError('provider_id_maps_to_multiple_teams')
        if ids['api_football'] != af[side]['team_id'] or ids['football_data'] != fd[side + '_team_id']:
            raise InputError('team_id_mismatch')
        if not _profile(team.get('profile')) or af[side].get('profile') != team['profile']:
            raise InputError('team_profile_mismatch')
        if not _valid_alias(team, 'sisal', event[side], event['date']) or not _valid_alias(team, 'api_football', af[side]['name'], event['date']):
            raise InputError('unreviewed_team_label')
        result.update(identity_verified=True, state='verified', canonical_id=desired,
                      provider_ids=deepcopy(ids), profile=deepcopy(team['profile']))
    except InputError as error:
        result['reasons'].append(str(error))
    return result


def _cross_provider_duplicates(request, registry, store, histories, kickoff):
    """AF records only corroborate already selected FD games via reviewed IDs.

    Never pool AF rows or deduplicate by names/date similarity. Full canonical
    match links are mandatory; conflicts block diagnostic statistics.
    """
    ids = request.get('api_football', {}).get('history_evidence_ids', [])
    if not isinstance(ids, list):
        raise InputError('invalid_history_evidence_list')
    duplicates = set()
    for ref in ids:
        proof = store.get(ref, 'api_football_history')
        af = proof['record']
        if (not all(positive_id(af.get(k)) for k in ('fixture_id', 'home_team_id', 'away_team_id', 'competition_id'))
                or type(af.get('season_start_year')) is not int or not _score_pair(af.get('score_90_minutes'))):
            raise InputError('invalid_cross_provider_history_record')
        links = [link for link in registry.get('match_links', []) if link.get('api_football_fixture_id') == af.get('fixture_id')]
        if len(links) != 1:
            raise InputError('history_match_link_missing_or_ambiguous')
        link = links[0]
        if (not positive_id(link.get('football_data_match_id'))
                or not isinstance(link.get('canonical_match_id'), str)
                or not re.fullmatch(r'local:match:[a-z0-9-]{1,64}', link['canonical_match_id'])
                or sum(l.get('football_data_match_id')==link['football_data_match_id'] for l in registry.get('match_links', [])) != 1):
            raise InputError('history_match_link_missing_or_ambiguous')
        store.verified_entry(link, 'match', kickoff)
        matches = [m for h in histories.values() for m in h['matches'] if m['match_id'] == link['football_data_match_id']]
        if not matches:
            raise InputError('linked_history_match_not_in_sample')
        for match in matches:
            sides = {}
            for side in ('home', 'away'):
                teams = [t for t in registry.get('teams', []) if t.get('provider_ids', {}).get('football_data') == match[side]['provider_id']]
                if len(teams) != 1:
                    raise InputError('history_opponent_mapping_unverified')
                store.verified_entry(teams[0], 'team', kickoff)
                sides[side] = teams[0]['provider_ids']['api_football']
            competitions = [c for c in registry.get('competitions', []) if c.get('football_data_code') == match['competition']['code']]
            if len(competitions) != 1:
                raise InputError('history_competition_mapping_unverified')
            store.verified_entry(competitions[0], 'competition', kickoff)
            if (af.get('home_team_id') != sides['home'] or af.get('away_team_id') != sides['away']
                    or instant(af.get('kickoff')) != instant(match['utc_date'])
                    or af.get('competition_id') != competitions[0]['api_football_id']
                    or af.get('season_start_year') != match['season']['start_year'] or af.get('status') != 'FINISHED'
                    or af.get('score_90_minutes') != match['score_90_minutes']):
                raise InputError('cross_provider_history_conflict')
            match['cross_provider_provenance'] = [{'provider': 'api-football', 'fixture_id': af['fixture_id'],
                'canonical_match_id': link['canonical_match_id'], 'evidence_id': ref,
                'origin': proof['origin'], 'acquired_at': instant(proof['acquired_at']).isoformat()}]
        duplicates.add((af['fixture_id'], link['football_data_match_id']))
    return len(duplicates)


def _availability(request, registry, store, histories):
    analysis = instant(request['analysis_at']) if request['purpose'] == 'historical_backtest' else None
    errors, checked, publication_verified, total = [], 0, 0, 0
    lookup = registry.get('availability', {})
    for side, history in histories.items():
        for match in history['matches']:
            total += 1
            match['availability'] = {'first_published_at': None, 'known_available_by': None,
                                     'verified_by_analysis_time': False}
            ref = lookup.get(str(match['match_id']))
            if ref is None:
                if analysis is not None:
                    errors.append({'side': side, 'match_id': match['match_id'], 'code': 'publication_or_observation_time_unknown'})
                continue
            proof = store.get(ref, 'result_observation')
            record = proof['record']
            observed = instant(record['observed_at'])
            if (record.get('football_data_match_id') != match['match_id'] or record.get('status') != 'FINISHED'
                    or not positive_id(record.get('football_data_match_id')) or not _score_pair(record.get('score_90_minutes'))
                    or record.get('score_90_minutes') != match['score_90_minutes']
                    or record.get('home_team_id') != match['home']['provider_id']
                    or record.get('away_team_id') != match['away']['provider_id']
                    or observed < instant(match['utc_date']) or observed > store.verified
                    or observed > instant(proof['acquired_at'])):
                raise InputError('invalid_result_observation')
            published = record.get('published_at')
            available = observed
            if published is not None:
                published = instant(published)
                if (record.get('publication_timestamp_basis') != 'explicit_source_publication'
                        or published < instant(match['utc_date']) or published > observed):
                    raise InputError('invalid_publication_evidence')
                match['availability']['first_published_at'] = published.isoformat()
                available = published
                publication_verified += 1
            match['availability']['known_available_by'] = available.isoformat()
            match['availability']['verified_by_analysis_time'] = analysis is not None and available <= analysis
            if analysis is not None:
                if available > analysis:
                    errors.append({'side': side, 'match_id': match['match_id'], 'code': 'result_published_after_analysis' if published is not None else 'availability_not_proven_by_analysis'})
                else:
                    checked += 1
    return {'state': 'not_certified' if analysis is None else 'verified_as_of_observation' if not errors else 'temporal_unverified',
            'backtest_availability_verified': analysis is not None and not errors and checked > 0,
            'first_publication_time_verified': total > 0 and publication_verified == total, 'reasons': errors}


def probe(request, registry, dataset: Dataset, evidence_directory):
    """Return safe diagnostics; never expose statistics before both identities pass."""
    output = {'schema_version': VERSION, 'ready_for_quant': False, 'status': 'identity_unverified',
              'diagnostic_statistics_allowed': False, 'statistics_usable_in_production': False,
              'verification_scope': 'unverified', 'checks': {'event': {'verified': False, 'reasons': []},
              'teams': {side: {'identity_verified': False, 'state': 'identity_unverified', 'reasons': []} for side in ('home', 'away')}},
              'histories': {}, 'temporal': {'backtest_availability_verified': False, 'first_publication_time_verified': False},
              'blockers': [], 'cross_provider_duplicate_matches': 0, 'evidence': []}
    store = None
    try:
        if not isinstance(request, dict) or request.get('schema_version') != VERSION or registry.get('schema_version') != VERSION:
            raise InputError('unsupported_adapter_contract')
        if request.get('evidence_mode') not in ('real_only', 'simulation') or request.get('purpose') not in ('diagnostic', 'historical_backtest'):
            raise InputError('invalid_adapter_mode_or_purpose')
        verified = instant(request['verified_at'])
        store = EvidenceStore(registry, evidence_directory, request['evidence_mode'], verified)
        event, af = request['sisal_event'], request['api_football']
        if af.get('state') != 'available' or request['football_data'].get('state') != 'available':
            output['status'] = 'provider_unavailable'
            raise InputError('provider_not_available')
        if not all(isinstance(event.get(k), str) and re.fullmatch('[0-9]{1,20}', event[k]) for k in ('palinsesto', 'avvenimento')):
            raise InputError('invalid_sisal_event_ids')
        kickoff = sisal_kickoff(event)
        if (not all(positive_id(af.get(k)) for k in ('fixture_id', 'competition_id'))
                or not all(positive_id(af[s].get('team_id')) for s in ('home','away'))
                or af['home']['team_id']==af['away']['team_id']
                or type(event.get('season_start_year')) is not int or type(af.get('season_start_year')) is not int):
            raise InputError('invalid_api_football_fixture_identity')
        fd_id = request['football_data']['match_id']
        if not positive_id(fd_id) or not positive_id(af.get('fixture_id')):
            raise InputError('invalid_provider_match_id')
        fd = _fd_event(dataset, fd_id, verified)
        output['event_ids'] = {'palinsesto': event['palinsesto'], 'avvenimento': event['avvenimento'],
                               'api_football_fixture_id': af['fixture_id'], 'football_data_match_id': fd_id}
        bindings = [b for b in registry.get('bindings', []) if b.get('palinsesto') == event['palinsesto'] and b.get('avvenimento') == event['avvenimento']]
        if len(bindings) != 1:
            for side in ('home', 'away'):
                output['checks']['teams'][side].update(state='identity_ambiguous' if len(bindings)>1 else 'identity_unverified', reasons=['event_binding_missing_or_ambiguous'])
            raise InputError('event_binding_missing_or_ambiguous')
        binding = bindings[0]
        store.verified_entry(binding, 'binding', kickoff)
        for side in ('home', 'away'):
            output['checks']['teams'][side] = _team_check(registry, binding, side, event, af, fd, store, kickoff)
        context = []
        try:
            sisal_proof = store.get(event['evidence_id'], 'sisal_event')
            af_proof = store.get(af['evidence_id'], 'api_football_fixture')
            if sisal_proof.get('record') != {k:v for k,v in event.items() if k != 'evidence_id'}:
                raise InputError('sisal_record_does_not_match_evidence')
            if af_proof.get('record') != {k:v for k,v in af.items() if k not in ('evidence_id','state','history_evidence_ids')}:
                raise InputError('fixture_record_does_not_match_evidence')
            comps = [c for c in registry.get('competitions', []) if c.get('canonical_id') == binding.get('competition_canonical_id')]
            if len(comps) != 1:
                raise InputError('competition_mapping_missing_or_ambiguous')
            comp = comps[0]
            store.verified_entry(comp, 'competition', kickoff)
            if not all(positive_id(comp.get(k)) for k in ('api_football_id','football_data_id')):
                raise InputError('invalid_competition_mapping')
            if (binding.get('api_football_fixture_id') != af['fixture_id'] or binding.get('football_data_match_id') != fd_id
                    or binding.get('home_canonical_id') == binding.get('away_canonical_id')
                    or comp['canonical_id'] != event['competition_canonical_id']
                    or comp['api_football_id'] != af['competition_id']
                    or comp['football_data_id'] != fd['competition_id'] or comp['football_data_code'] != fd['competition_code']
                    or event['season_start_year'] != af['season_start_year'] or af['season_start_year'] != fd['season_start_year']
                    or instant(af['kickoff']) != kickoff or instant(fd['kickoff_utc']) != kickoff):
                raise InputError('fixture_competition_season_or_kickoff_mismatch')
        except InputError as error:
            context.append(str(error))
        output['checks']['event'] = {'verified': not context, 'reasons': context,
                                    'kickoff_utc': kickoff.isoformat(), 'football_data_source': fd}
        if context or not all(c['identity_verified'] for c in output['checks']['teams'].values()):
            output['blockers'].append('identity_unverified')
            return output
        output['verification_scope'] = 'synthetic_only' if request['evidence_mode']=='simulation' else 'reviewed_real_evidence'
        analysis = instant(request['analysis_at']) if request['purpose']=='historical_backtest' else verified
        if analysis > verified:
            raise InputError('analysis_after_verification')
        history_cutoff = min(kickoff, analysis) if request['purpose']=='historical_backtest' else kickoff
        histories = {}
        for side, identity in output['checks']['teams'].items():
            histories[side] = build_history(dataset, team_id=f"football-data.org:team:{identity['provider_ids']['football_data']}",
                                           competitions=request['history_scope'][side], event_kickoff=history_cutoff,
                                           verified_at=verified, display_timezone=event['timezone'])
            histories[side]['adapter_canonical_team_id'] = identity['canonical_id']
            team = next(t for t in registry['teams'] if t['canonical_id']==identity['canonical_id'])
            for match in histories[side]['matches']:
                store.verified_entry(team, 'team', instant(match['utc_date']))
        output['cross_provider_duplicate_matches'] = _cross_provider_duplicates(request, registry, store, histories, kickoff)
        output['temporal'] = _availability(request, registry, store, histories)
        output['temporal'].update(event_kickoff_utc=kickoff.isoformat(), analysis_at_utc=analysis.isoformat(), purpose=request['purpose'])
        statuses = {h['status'] for h in histories.values()}
        unavailable_scope = any(any(i['code'] in ('missing_competition_snapshot', 'source_unavailable') for i in h['diagnostics']['sources']) or h['diagnostics']['load'] for h in histories.values())
        if output['temporal']['state'] == 'temporal_unverified':
            output['status'] = 'temporal_unverified'
        elif unavailable_scope:
            output['status'] = 'provider_unavailable'
        elif any(h['history_status']=='insufficient_history' for h in histories.values()):
            output['status'] = 'insufficient_history'
        elif statuses & {'review_required', 'identity_unresolved'}:
            output['status'] = 'data_unverified'
        elif 'stale_source' in statuses:
            output['status'] = 'source_stale'
        else:
            output['status'] = 'diagnostic_available'
            output['diagnostic_statistics_allowed'] = True
        output['histories'] = histories
        if not output['diagnostic_statistics_allowed']:
            # Keep match identity/provenance and real counts, withhold all stats.
            for history in output['histories'].values():
                history['statistics'] = None
        return output
    except InputError as error:
        code = str(error)
        if code in ('football_data_event_unavailable',):
            output['status'] = 'provider_unavailable'
        elif code in ('conflicting_provider_event','cross_provider_history_conflict','invalid_result_observation'):
            output['status'] = 'data_conflict'
        output['blockers'].append(code)
        return output
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        output['blockers'].append('malformed_adapter_input')
        return output
    finally:
        if store is not None:
            output['evidence'] = store.provenance()
