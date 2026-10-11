"""Small official HTTPS collector. Never persist credentials or provider errors.

API-Football requests share the account with Railway. No production imports,
automatic retries, redirects or private endpoints. API-Football hard cap: five
GETs including /status, daily reserve 20 and minute reserve 2.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
ROOT.joinpath('evidence').mkdir(exist_ok=True)
ROOT.joinpath('reports').mkdir(exist_ok=True)


def now():
    return datetime.now(timezone.utc).isoformat()


def save(name, value):
    (ROOT / 'evidence' / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def get(url, name, auth=None, select=None, binary=False):
    """Persist only whitelisted public data and numeric quota observations."""
    headers = {'Accept': 'application/pdf,text/html' if binary else 'application/json',
               'User-Agent': 'HistoryProviderV2-Research/1.0'}
    if auth:
        header, variable = auth
        credential = os.environ.get(variable, '').strip()
        if not credential:
            raise RuntimeError('credential_missing')
        headers[header] = credential
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    meta = {'source': url, 'request_started_at': now(), 'http_status': None,
            'tls_verification_enabled': True, 'state': 'unavailable', 'quota': {}}
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=25) as response:
            meta['http_status'] = response.status
            meta['content_type'] = response.headers.get_content_type()
            for key in ('x-ratelimit-requests-limit', 'x-ratelimit-requests-remaining',
                        'x-ratelimit-limit', 'x-ratelimit-remaining', 'retry-after',
                        'x-requests-available-minute', 'x-requestcounter-reset'):
                value = response.headers.get(key)
                if value and value.isdigit():
                    meta['quota'][key] = int(value)
            raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise RuntimeError('response_too_large')
            if binary:
                (ROOT / 'evidence' / name).write_bytes(raw)
                meta.update(state='retrieved', retained_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
            else:
                body = json.loads(raw)
                errors = body.get('errors') if isinstance(body, dict) else None
                if errors:
                    words = json.dumps(errors).lower()
                    category = ('provider_plan_restricted' if any(x in words for x in ('free', 'subscription', 'plan')) else
                                'provider_rate_limited' if any(x in words for x in ('limit', 'quota', 'requests')) else
                                'provider_reported_error')
                    meta.update(state='provider_error', error_category=category)
                    # Fixed categories and validated public date constraints,
                    # never the original provider message or arbitrary values.
                    meta['safe_provider_diagnostic'] = {
                        'restriction_scope': 'date' if 'date' in words else 'season' if 'season' in words else 'unspecified',
                        'free_plan_mentioned': 'free' in words,
                    }
                    interval = re.search(r'(?:from|between)\s+(\d{4}-\d{2}-\d{2})\s+(?:to|and)\s+(\d{4}-\d{2}-\d{2})', words)
                    if interval:
                        try:
                            start, end = (datetime.fromisoformat(value).date() for value in interval.groups())
                            if start <= end:
                                meta['safe_provider_diagnostic']['permitted_date_interval_reported'] = {'from': str(start), 'until': str(end)}
                        except ValueError:
                            pass
                else:
                    clean = select(body) if select else None
                    if clean is None:
                        raise RuntimeError('unexpected_response_shape')
                    save(name, clean)
                    meta.update(state='retrieved', retained_sha256=hashlib.sha256((ROOT / 'evidence' / name).read_bytes()).hexdigest())
    except urllib.error.HTTPError as error:
        meta.update(http_status=error.code, state='http_error',
                    error_category='provider_authentication_failed' if error.code in (401, 403) else
                    'provider_rate_limited' if error.code == 429 else 'provider_http_failure')
    except urllib.error.URLError as error:
        meta.update(state='proxy_connect_forbidden' if 'tunnel connection failed: 403' in str(error.reason).lower() else 'transport_error',
                    technical_error_class=type(error.reason).__name__)
    except Exception as error:
        meta.update(state='technical_error', technical_error_class=type(error).__name__)
    meta['response_completed_at'] = now()
    save(name + '.meta.json', meta)
    print(json.dumps(meta, ensure_ascii=False))
    return meta


def af_budget_check():
    observations = sorted(ROOT.joinpath('evidence').glob('af-*.meta.json'), key=lambda path: path.stat().st_mtime)
    if len(observations) >= 5:
        raise RuntimeError('local_af_request_cap')
    if not observations:
        raise RuntimeError('missing_shared_account_quota')
    last = json.loads(observations[-1].read_text())
    if last['state'] != 'retrieved':
        raise RuntimeError('previous_af_request_unavailable')
    remaining = last['quota'].get('x-ratelimit-requests-remaining')
    status_file = ROOT / 'evidence/af-status.json'
    if remaining is None and status_file.exists():
        account = json.loads(status_file.read_text())['requests']
        remaining = account['limit_day'] - account['current'] - (len(observations) - 1)
    if remaining is None or remaining <= 20:
        raise RuntimeError('shared_daily_reserve_or_unknown_quota')
    minute = last['quota'].get('x-ratelimit-remaining')
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last['response_completed_at'])).total_seconds()
    delay = max(0, (60 if minute is not None and minute <= 2 else 8) - elapsed)
    if delay:
        time.sleep(min(delay, 60))


def status_select(body):
    response = body.get('response')
    if not isinstance(response, dict):
        return None
    requests = response.get('requests', {})
    if not all(type(requests.get(key)) is int for key in ('current', 'limit_day')):
        return None
    subscription = response.get('subscription', {})
    return {'requests': {key: requests[key] for key in ('current', 'limit_day')},
            'subscription': {key: subscription.get(key) for key in ('plan', 'active')}}


def fixtures_select(body):
    rows = body.get('response')
    if not isinstance(rows, list):
        return None
    clean = []
    for row in rows:
        fixture, league = row.get('fixture', {}), row.get('league', {})
        clean.append({
            'fixture': {key: fixture.get(key) for key in ('id', 'timezone', 'date', 'timestamp', 'status', 'venue')},
            'league': {key: league.get(key) for key in ('id', 'name', 'country', 'season', 'round')},
            'teams': {side: {key: row.get('teams', {}).get(side, {}).get(key) for key in ('id', 'name')} for side in ('home', 'away')},
            'goals': row.get('goals'), 'score': row.get('score'),
        })
    return {'results': body.get('results'), 'paging': body.get('paging'), 'response': clean}


if __name__ == '__main__':
    presence = {'checked_at': now(), 'credentials': {key: bool(os.environ.get(key, '').strip())
                for key in ('API_FOOTBALL_KEY', 'FOOTBALL_DATA_TOKEN')}}
    save('credential-presence.json', presence)
    if not all(presence['credentials'].values()):
        raise SystemExit('credential_missing')
    if (ROOT / 'evidence/af-status.json.meta.json').exists():
        raise SystemExit('status_attempt_already_recorded_no_automatic_repeat')
    get('https://v3.football.api-sports.io/status', 'af-status.json',
        auth=('x-apisports-key', 'API_FOOTBALL_KEY'), select=status_select)
