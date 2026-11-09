#!/usr/bin/env python3
"""Download daily equity histories for a frozen historical security universe.

INSTALL (Anaconda Prompt):
    python -m pip install yfinance pandas pyarrow
JUPYTER INSTALL:  %pip install yfinance pandas pyarrow
JUPYTER RUN:      %run ./download_prices.py --dry-run
                 %run ./download_prices.py
COMMAND LINE:    python download_prices.py --universe equity_universe_2023.csv

Place this script beside equity_universe_2023.csv. No sources/ folder is needed.
Defaults: 2000-01-01 through 2025-12-31 INCLUSIVE, daily, all 904 rows.
An IPO after 2000 naturally has less data. Missing rows are never interpolated.

OUTPUT under price_data/:
  cache/<security_id>/<request_hash>/: immutable provider-frame Parquet snapshots,
      metadata, checksums and a pointer to the most recent cached response.
  runs/<run_id>/prices/<security_id>.parquet: one file per downloaded security.
  runs/<run_id>/status.csv and status.parquet: EVERY input security, even failures.
  runs/<run_id>/segments.jsonl: per-request results and raw-cache locations.
  runs/<run_id>/attempts.jsonl: retries, exceptions and cache validation problems.
  runs/<run_id>/run.json: request parameters, source hashes and package versions.
  runs/<run_id>/universe_input.csv: exact original input bytes.
  latest_run.json: points to the latest run, which may be incomplete/interrupted.

Rerun the same command to reuse good cached responses and retry failed requests.
Use --refresh to fetch new snapshots without deleting earlier raw responses.
Use --offline to rebuild from cache only. A new run gets a fresh output directory
so failed refreshes cannot leave stale files masquerading as successful downloads.

IDENTITY / MAPPINGS
  universe_security_id is the storage key, never the ticker. The ID is a local
  roster key, not proof of historical security continuity. Literal historical
  symbols are baseline requests, marked unverified for full-history identity.
  Only BRK.B -> BRK-B and BF.B -> BF-B are built-in provider-format translations.
  No guessed successor, acquirer substitution, search, or fuzzy match is used.
  Provider symbol redirects, missing identity metadata, non-USD/non-equity
  results, duplicate dates and known merger/ticker-reuse cases are quarantined
  or held. Every held security remains in status. Returned data is not certified
  to represent the same share class for its entire history merely because the
  provider reports the requested symbol.

  Optional --mappings verified_price_mappings.json supplies reviewed segments:
  {
    "schema_version": 1,
    "mappings": [{
      "universe_security_id": "<exact ID from CSV>",
      "historical_ticker": "<exact historical ticker from CSV>",
      "provider_symbol": "<verified Yahoo symbol>",
      "start": "2000-01-01", "end": "2025-12-31",
      "verified": true, "same_security_history_verified": true,
      "verified_by": "<reviewer>", "verified_on": "YYYY-MM-DD",
      "evidence_url": "https://<issuer or SEC evidence>",
      "provider_evidence_url": "https://<provider history evidence>",
      "notes": "<explain share-class continuity and allowed history dates>"
    }]
  }
  These are reviewer attestations, not verification performed by this script.
  Placeholder entries are invalid. Supply only actually reviewed records.
  An explicit mapping REPLACES the baseline request for that security; only its
  approved date intervals are downloaded. Unmapped portions are logged as gaps.
  A new name or CIK alone does not authorize a merger/predecessor price splice.
  Intervals must not overlap within an ID, or across IDs using the same provider
  symbol. Same-symbol ticker reuse requires disjoint, independently checked dates.

RAW DATA MEANING
  Raw Parquet preserves the DataFrame delivered by yfinance, including its index,
  original columns, nulls and action rows. It is not an untouched HTTP payload or
  original exchange tape. Yahoo/yfinance can apply their own split conventions,
  action alignment and revisions. auto_adjust=False, back_adjust=False,
  repair=False, keepna=True, rounding=False; Adj Close is retained separately.
  No fills, calendar reindexing, return calculations or automatic repairs here.
  Acquisition success does not establish complete market-day coverage. Date
  gaps and short histories are reported, not labelled as proven IPO/delist dates.

LIMITATIONS
  Yahoo is a public best-effort source and may omit acquired/delisted securities.
  A 2023-selected roster used before 2023 has selection/look-ahead bias. Current
  provider histories may include later revisions/corporate actions. This script
  performs data acquisition only; the resulting files require identity/coverage
  review before training or backtesting.

References checked 2026-10-21:
  https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html
  https://github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/history.py
  https://finance.yahoo.com/quote/BRK-B/
  https://finance.yahoo.com/quote/BF-B/
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import os
import platform
import random
import re
import sys
import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VERSION = '1.0.1'
OPTIONS = dict(interval='1d', auto_adjust=False, back_adjust=False, repair=False,
               keepna=True, actions=True, rounding=False, prepost=False)
FORMAT_ALIASES = {'BRK.B': 'BRK-B', 'BF.B': 'BF-B'}
RISK_EVENTS = {'merger_and_ticker_reuse', 'old_equity_cancelled_reorganization',
               'merger_completed', 'ticker_change_after_merger'}
RISK_FLAGS = {'TICKER_REUSED_DIFFERENT_ISSUER', 'OLD_EQUITY_CANCELLED_SAME_TICKER'}
# Guard the known project cases even if a CSV export omits optional flag columns.
KNOWN_HOLDS = {
    'U20231229_SP400_DOC': 'Historical Physicians Realty Trust; DOC later reused by Healthpeak.',
    'U20231229_SP500_PEAK': 'Merger and adoption of the pre-existing DOC ticker.',
    'U20231229_SP400_WOLF': 'Old equity cancelled in 2025; ticker continued for new equity.',
    'U20231229_SP400_CHK': 'Merger/reorganization history requires dated continuity review.',
    'U20231229_SP400_SWN': 'Merger into another issuer; never substitute acquirer prices.',
}
STATUSES = ['universe_security_id', 'historical_ticker', 'company_name', 'status',
            'identity_status', 'requested_start', 'requested_end', 'planned_segments',
            'downloaded_segments', 'failed_segments', 'held_segments', 'rows',
            'first_price_date', 'last_price_date', 'missing_close_rows',
            'max_calendar_gap_days', 'mapping_gaps', 'warnings', 'price_file', 'message']


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest_bytes(b):
    return hashlib.sha256(b).hexdigest()


def digest_object(obj):
    return digest_bytes(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode())


def iso_date(s):
    d = date.fromisoformat(str(s))
    if d.isoformat() != s:
        raise ValueError(f'Date must use YYYY-MM-DD: {s!r}')
    return d


def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def save_json(path, obj):
    atomic_bytes(path, json.dumps(obj, indent=2, ensure_ascii=False, default=str,
                                 allow_nan=False).encode('utf-8'))


def save_csv(path, records, fields):
    f = io.StringIO(newline='')
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(records)
    atomic_bytes(path, f.getvalue().encode('utf-8'))


def save_parquet(path, df, index=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        df.to_parquet(tmp, engine='pyarrow', compression='zstd', index=index)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class Journal:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()

    def add(self, **record):
        with self.lock, self.path.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'recorded_at_utc': utc_now(), **record}, default=str) + '\n')
            f.flush()


def read_universe(path, expected_count):
    if not path.is_file():
        raise ValueError(f'Input CSV not found: {path}\nPlace equity_universe_2023.csv '
                         'beside this script or pass --universe with its full path.')
    raw = path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    required = {'universe_security_id', 'historical_ticker', 'company_name'}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError(f'Input must contain columns: {sorted(required)}')
    rows = list(reader)
    if len(rows) != expected_count:
        raise ValueError(f'Expected {expected_count} securities; found {len(rows)}. '
                         'Use --expected-count only for an intentionally different input.')
    seen = set()
    for r in rows:
        sid = r['universe_security_id']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', sid or ''):
            raise ValueError(f'Unsafe/empty security ID: {sid!r}')
        if sid in seen:
            raise ValueError(f'Duplicate security ID: {sid}')
        seen.add(sid)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.^=-]{0,31}', r['historical_ticker'] or ''):
            raise ValueError(f'Invalid historical ticker for {sid}')
        if not r['company_name'].strip():
            raise ValueError(f'Missing company name for {sid}')
    return rows, raw


def read_mappings(path, universe):
    if path is None:
        return {}, None
    raw = path.read_bytes()
    obj = json.loads(raw)
    if obj.get('schema_version') != 1 or not isinstance(obj.get('mappings'), list):
        raise ValueError('Mappings require schema_version=1 and a mappings list.')
    by_id = {r['universe_security_id']: r for r in universe}
    mappings = defaultdict(list)
    for m in obj['mappings']:
        sid = m.get('universe_security_id')
        if sid not in by_id or m.get('historical_ticker') != by_id[sid]['historical_ticker']:
            raise ValueError(f'Mapping ID/ticker does not match universe: {sid}')
        if m.get('verified') is not True or m.get('same_security_history_verified') is not True:
            raise ValueError(f'Mapping lacks explicit history verification: {sid}')
        for key in ['verified_by', 'verified_on', 'evidence_url', 'provider_evidence_url', 'notes']:
            value = m.get(key)
            if not isinstance(value, str) or not value.strip() or '<' in value:
                raise ValueError(f'Mapping requires real {key}: {sid}')
        for key in ['evidence_url', 'provider_evidence_url']:
            if not m[key].startswith(('https://', 'http://')):
                raise ValueError(f'Mapping requires URL in {key}: {sid}')
        iso_date(m['verified_on'])
        if iso_date(m.get('start', '')) > iso_date(m.get('end', '')):
            raise ValueError(f'Reversed mapping dates: {sid}')
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9.^=-]{0,31}', m.get('provider_symbol', '')):
            raise ValueError(f'Invalid provider symbol: {sid}')
        mappings[sid].append(dict(m))
    for sid, segments in mappings.items():
        segments.sort(key=lambda m: m['start'])
        for a, b in zip(segments, segments[1:]):
            if a['end'] >= b['start']:
                raise ValueError(f'Overlapping mapped date intervals for {sid}')
    return dict(mappings), raw


def make_plan(rows, mappings, start, end):
    plan = {}
    for row in rows:
        sid, ticker = row['universe_security_id'], row['historical_ticker']
        flags = set(row.get('quality_flags', '').split(';'))
        events = set(row.get('reviewed_event_types', '').split(';'))
        hold = KNOWN_HOLDS.get(sid, '')
        if flags & RISK_FLAGS or events & RISK_EVENTS:
            hold = hold or 'Known identity discontinuity; verified dated mapping required.'
        if sid in mappings:
            segments = []
            for m in mappings[sid]:
                lo, hi = max(start, m['start']), min(end, m['end'])
                if lo <= hi:
                    segments.append({**m, 'start': lo, 'end': hi,
                                     'identity_status': 'reviewer_verified_mapping'})
            plan[sid] = {'segments': segments, 'hold': '' if segments else 'No approved mapping overlaps requested dates.'}
        elif hold:
            plan[sid] = {'segments': [], 'hold': hold}
        else:
            symbol = FORMAT_ALIASES.get(ticker, ticker)
            plan[sid] = {'hold': '', 'segments': [{
                'universe_security_id': sid, 'historical_ticker': ticker,
                'provider_symbol': symbol, 'start': start, 'end': end,
                'identity_status': 'baseline_symbol_history_unverified',
                'evidence_url': f'https://finance.yahoo.com/quote/{symbol}/' if ticker in FORMAT_ALIASES else '',
                'notes': 'Verified provider spelling only; no full-history continuity assertion.' if ticker in FORMAT_ALIASES else 'Literal historical symbol; no alias inference.'}]}
    # A single provider series must not be silently assigned to two original IDs.
    by_symbol = defaultdict(list)
    for sid, p in plan.items():
        for s in p['segments']:
            by_symbol[s['provider_symbol']].append((sid, s))
    conflicts = set()
    for symbol, items in by_symbol.items():
        for i, (sid, s) in enumerate(items):
            for oid, other in items[i+1:]:
                if sid != oid and max(s['start'], other['start']) <= min(s['end'], other['end']):
                    conflicts.update((sid, oid))
    for sid in conflicts:
        plan[sid] = {'segments': [], 'hold': 'Provider-symbol interval overlaps another security ID; resolve mappings.'}
    return plan


def mapping_gaps(segments, start, end):
    cursor, finish = iso_date(start), iso_date(end)
    gaps = []
    for s in sorted(segments, key=lambda s: s['start']):
        lo, hi = iso_date(s['start']), iso_date(s['end'])
        if cursor < lo:
            gaps.append(f'{cursor.isoformat()}..{(lo-timedelta(days=1)).isoformat()}')
        cursor = max(cursor, hi+timedelta(days=1))
    if cursor <= finish:
        gaps.append(f'{cursor.isoformat()}..{finish.isoformat()}')
    return ';'.join(gaps)


def yahoo_fetch(symbol, start, end_exclusive, timeout):
    import yfinance as yf
    ticker = yf.Ticker(symbol)
    # Individual histories inside scheduled batches avoid multi-ticker alignment
    # that inserts extra null calendar rows across different securities.
    error_options = {}
    if hasattr(yf, 'config') and hasattr(yf.config, 'debug'):
        yf.config.debug.hide_exceptions = False
    else:
        error_options['raise_errors'] = True
    frame = ticker.history(start=start, end=end_exclusive, timeout=timeout,
                           **error_options, **OPTIONS)
    metadata = ticker.get_history_metadata() if frame is not None and not frame.empty else {}
    return frame, dict(metadata)


class Downloader:
    def __init__(self, cache, journal, versions, args, fetcher=yahoo_fetch):
        self.cache, self.journal, self.versions, self.args = cache, journal, versions, args
        self.fetcher = fetcher

    def response(self, row, segment):
        import pandas as pd
        req = {'schema': VERSION, 'provider': 'yahoo_via_yfinance', 'options': OPTIONS,
               'universe_security_id': row['universe_security_id'],
               'historical_ticker': row['historical_ticker'], 'mapping': segment,
               'end_exclusive': (iso_date(segment['end'])+timedelta(days=1)).isoformat(),
               'versions': self.versions}
        key = digest_object(req)
        folder = self.cache / row['universe_security_id'] / key
        pointer = folder / 'current.json'
        if pointer.exists() and not self.args.refresh:
            try:
                meta = json.loads(pointer.read_text(encoding='utf-8'))
                if meta['request'] != req:
                    raise ValueError('Cache request mismatch')
                filename = meta['raw_file']
                if Path(filename).name != filename:
                    raise ValueError('Invalid raw cache filename')
                raw_path = folder / filename
                if digest_bytes(raw_path.read_bytes()) != meta['raw_sha256']:
                    raise ValueError('Raw cache checksum mismatch')
                frame = pd.read_parquet(raw_path, engine='pyarrow')
                if frame.empty or not meta.get('has_usable_close'):
                    raise ValueError('Cached response contains no usable prices; retry required')
                return frame, meta, str(raw_path.resolve()), True
            except (OSError, ValueError, KeyError, TypeError) as e:
                self.journal.add(security_id=row['universe_security_id'], event='invalid_cache', error=str(e))
                if self.args.offline:
                    raise RuntimeError(f'Offline cache invalid: {e}') from e
        if self.args.offline:
            raise RuntimeError('No matching usable cache; offline mode prohibits download.')
        last = ''
        for attempt in range(1, self.args.attempts+1):
            raw_path = None
            try:
                frame, provider_meta = self.fetcher(segment['provider_symbol'], segment['start'],
                                                   req['end_exclusive'], self.args.timeout)
            except Exception as e:
                # Transport/provider exceptions are retryable. Filesystem/storage
                # errors below are fatal, not silently converted to missing tickers.
                last = f'{type(e).__name__}: {e}'
            else:
                if not isinstance(frame, pd.DataFrame):
                    last = 'Provider returned no DataFrame.'
                else:
                    raw_path = folder / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex+'.parquet')
                    save_parquet(raw_path, frame, index=True)
                    close = pd.to_numeric(frame['Close'], errors='coerce') if 'Close' in frame and frame.columns.is_unique and not isinstance(frame.columns, pd.MultiIndex) else pd.Series(dtype=float)
                    usable = bool((close.gt(0) & close.map(lambda x: math.isfinite(x) if pd.notna(x) else False)).any())
                    meta = {'request': req, 'retrieved_at_utc': utc_now(), 'provider_metadata': provider_meta,
                            'raw_file': raw_path.name, 'raw_sha256': digest_bytes(raw_path.read_bytes()),
                            'returned_rows': len(frame), 'has_usable_close': usable}
                    # Default=str preserves unusual metadata scalars for the audit;
                    # serialize NaN metadata safely without touching price values.
                    meta = json.loads(json.dumps(meta, default=str), parse_constant=lambda _: None)
                    save_json(raw_path.with_suffix('.json'), meta)
                    self.journal.add(security_id=row['universe_security_id'], event='response_saved',
                                     attempt=attempt, raw_file=str(raw_path.resolve()), rows=len(frame))
                    if usable:
                        save_json(pointer, meta)
                        return frame, meta, str(raw_path.resolve()), False
                    last = 'Empty response or no positive Close values; raw response retained.'
            self.journal.add(security_id=row['universe_security_id'], symbol=segment['provider_symbol'],
                             event='request_failed', attempt=attempt, error=last,
                             raw_file=str(raw_path.resolve()) if raw_path else '')
            if attempt < self.args.attempts:
                time.sleep(min(30.0, self.args.retry_delay * 2**(attempt-1) + random.uniform(0, .5)))
        raise RuntimeError(f'Failed after {self.args.attempts} attempts: {last}')


def normalize(frame, metadata, row, seg, raw_path):
    """Return an unfilled daily table, or quarantine the retained raw response."""
    import pandas as pd
    pm = metadata.get('provider_metadata', {})
    if not isinstance(pm, dict):
        raise ValueError('Missing or invalid provider identity metadata; raw retained.')
    if str(pm.get('symbol', '')).upper() != seg['provider_symbol'].upper():
        raise ValueError(f'Provider symbol mismatch/missing: {pm.get("symbol")!r}; explicit mapping required.')
    if pm.get('currency') != 'USD' or pm.get('instrumentType') != 'EQUITY':
        raise ValueError(f'Unexpected currency/type: {pm.get("currency")}/{pm.get("instrumentType")}')
    required = {'Open', 'High', 'Low', 'Close', 'Volume'}
    if not required.issubset(frame.columns) or isinstance(frame.columns, pd.MultiIndex):
        raise ValueError('Provider frame missing expected single-security OHLCV schema.')
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.hasnans:
        raise ValueError('Provider returned missing or non-datetime timestamps.')
    if not frame.columns.is_unique:
        raise ValueError('Duplicate provider column names.')
    # Derive trading date in exchange-local time, NOT by converting to UTC first.
    dates = pd.to_datetime(frame.index.date)
    if dates.duplicated().any():
        raise ValueError('Duplicate daily dates; raw retained, no automatic deduplication.')
    if len(dates) and (dates.min().date() < iso_date(seg['start']) or dates.max().date() > iso_date(seg['end'])):
        raise ValueError('Provider returned dates outside approved interval; raw retained.')
    reserved = {'date','universe_security_id','historical_ticker','provider_symbol',
                'provider_timestamp','retrieved_at_utc','raw_cache_file','identity_status','currency'}
    if reserved.intersection(frame.columns):
        raise ValueError('Provider columns conflict with provenance fields.')
    out = frame.copy().reset_index(drop=True)
    out.insert(0, 'date', dates)
    out.insert(0, 'universe_security_id', row['universe_security_id'])
    out['historical_ticker'] = row['historical_ticker']
    out['provider_symbol'] = seg['provider_symbol']
    out['provider_timestamp'] = [x.isoformat() for x in frame.index]
    out['retrieved_at_utc'] = metadata['retrieved_at_utc']
    out['raw_cache_file'] = raw_path
    out['identity_status'] = seg['identity_status']
    out['currency'] = pm['currency']
    return out.sort_values('date', kind='stable').reset_index(drop=True)


def initial_status(row, plan, args):
    return dict(zip(STATUSES, [row['universe_security_id'], row['historical_ticker'], row['company_name'],
                'pending', '', args.start, args.end, len(plan['segments']), 0, 0, 0, 0,
                '', '', 0, 0, mapping_gaps(plan['segments'], args.start, args.end), '', '', '']))


def process_security(row, plan, engine, run_dir, args):
    import pandas as pd
    status = initial_status(row, plan, args)
    if plan['hold']:
        status.update(status='held_identity_review', identity_status='unresolved', message=plan['hold'])
        return status, []
    parts, results = [], []
    for s in plan['segments']:
        result = {'universe_security_id': row['universe_security_id'], 'segment': s,
                  'status': 'failed', 'message': '', 'raw_cache_file': '', 'cache_hit': False}
        try:
            raw, meta, path, cached = engine.response(row, s)
        except RuntimeError as e:
            result['message'] = str(e)
            status['failed_segments'] += 1
        else:
            result.update(raw_cache_file=path, cache_hit=cached)
            try:
                part = normalize(raw, meta, row, s, path)
            except ValueError as e:
                result.update(status='quarantined', message=str(e))
                status['held_segments'] += 1
            else:
                parts.append(part)
                result.update(status='downloaded', rows=len(part), retrieved_at_utc=meta['retrieved_at_utc'])
                status['downloaded_segments'] += 1
        results.append(result)
    status['message'] = '; '.join(r['message'] for r in results if r['message'])
    if not parts:
        status['status'] = 'quarantined' if status['held_segments'] else 'failed'
        return status, results
    combined = pd.concat(parts, ignore_index=True).sort_values('date', kind='stable')
    if combined.duplicated(['universe_security_id', 'date']).any():
        raise ValueError('Internal interval overlap; refusing ambiguous security/date keys.')
    warnings = []
    close = pd.to_numeric(combined['Close'], errors='coerce')
    valid = combined.loc[close.gt(0) & close.map(lambda x: math.isfinite(x) if pd.notna(x) else False), 'date']
    missing = int(close.isna().sum())
    if missing:
        warnings.append('provider_null_close_preserved')
    if ((close <= 0) | close.map(lambda x: not math.isfinite(x) if pd.notna(x) else False)).any():
        warnings.append('nonpositive_or_nonfinite_close_preserved')
    if 'Adj Close' not in combined:
        warnings.append('adjusted_close_unavailable')
    first = valid.min().date().isoformat() if len(valid) else ''
    last = valid.max().date().isoformat() if len(valid) else ''
    if first and iso_date(first) > iso_date(args.start) + timedelta(days=7):
        warnings.append('history_starts_later_than_requested_reason_unverified')
    if last and iso_date(last) < iso_date(args.end) - timedelta(days=7):
        warnings.append('history_ends_earlier_than_requested_reason_unverified')
    max_gap = int(valid.diff().dt.days.max()) if len(valid)>1 else 0
    if max_gap > 7:
        warnings.append('long_calendar_gap_review')
    if status['mapping_gaps']:
        warnings.append('unapproved_date_intervals_not_requested')
    identity = ';'.join(sorted(set(combined['identity_status'])))
    if 'unverified' in identity:
        warnings.append('full_history_security_identity_unverified')
    path = run_dir / 'prices' / (row['universe_security_id'] + '.parquet')
    save_parquet(path, combined)
    partial = status['failed_segments'] or status['held_segments'] or status['mapping_gaps']
    status.update(status='partial' if partial else 'downloaded', identity_status=identity,
                  rows=len(combined), first_price_date=first, last_price_date=last,
                  missing_close_rows=missing, max_calendar_gap_days=max_gap,
                  warnings=';'.join(warnings), price_file=str(path.resolve()))
    return status, results


def package_versions():
    out = {'python': platform.python_version()}
    for package in ['yfinance', 'pandas', 'pyarrow']:
        try:
            out[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            out[package] = 'not_installed'
    return out


def arguments(argv=None):
    base = Path(__file__).resolve().parent if '__file__' in globals() else Path.cwd()
    p = argparse.ArgumentParser(description='Daily public equity prices keyed by universe_security_id.',
                                epilog='See the script docstring for installation, mappings, and storage details.')
    p.add_argument('--universe', type=Path, default=base/'equity_universe_2023.csv')
    p.add_argument('--output', type=Path, default=base/'price_data')
    p.add_argument('--start', default='2000-01-01')
    p.add_argument('--end', default='2025-12-31', help='Inclusive final trading date')
    p.add_argument('--expected-count', type=int, default=904)
    p.add_argument('--mappings', type=Path, help='Explicitly verified mapping JSON; see docstring')
    p.add_argument('--batch-size', type=int, default=25)
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--batch-pause', type=float, default=5)
    p.add_argument('--attempts', type=int, default=3, help='Total attempts per failed segment, including first')
    p.add_argument('--retry-delay', type=float, default=2)
    p.add_argument('--timeout', type=float, default=30)
    g = p.add_mutually_exclusive_group()
    g.add_argument('--refresh', action='store_true')
    g.add_argument('--offline', action='store_true')
    p.add_argument('--dry-run', action='store_true', help='Validate all input rows and write plan; no price requests')
    p.add_argument('--strict', action='store_true', help='Exit 2 if any row fails, is held or has incomplete mapped coverage')
    a = p.parse_args(argv)
    if iso_date(a.start) > iso_date(a.end) or iso_date(a.end) >= date.today():
        p.error('Dates must be ordered and end must precede today.')
    for k in ['expected_count','batch_size','workers','attempts','timeout']:
        if getattr(a,k)<=0:
            p.error(f'--{k.replace("_","-")} must be positive.')
    if a.workers > 8 or a.batch_pause < 0 or a.retry_delay < 0:
        p.error('Use 1..8 workers and nonnegative pauses.')
    return a


def run(args, fetcher=yahoo_fetch):
    rows, universe_bytes = read_universe(args.universe.expanduser().resolve(), args.expected_count)
    mappings, mapping_bytes = read_mappings(args.mappings, rows)
    plan = make_plan(rows, mappings, args.start, args.end)
    versions = package_versions()
    if not args.dry_run:
        needed = ['pandas', 'pyarrow', 'yfinance']
        missing = [p for p in needed if versions[p]=='not_installed']
        if missing:
            raise ValueError('Install dependencies first: python -m pip install yfinance pandas pyarrow\n'
                             'In Jupyter use: %pip install yfinance pandas pyarrow')
    root = args.output.expanduser().resolve()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8]
    run_dir = root/'runs'/run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    atomic_bytes(run_dir/'universe_input.csv', universe_bytes)
    if mapping_bytes is not None:
        atomic_bytes(run_dir/'mappings_input.json', mapping_bytes)
    save_json(run_dir/'request_plan.json', plan)
    run_meta = {'script_version': VERSION, 'run_id': run_id, 'started_at_utc': utc_now(),
                'state': 'running', 'universe_sha256': digest_bytes(universe_bytes),
                'mappings_sha256': digest_bytes(mapping_bytes) if mapping_bytes else None,
                'start_inclusive': args.start, 'end_inclusive': args.end,
                'end_exclusive_sent_to_provider': (iso_date(args.end)+timedelta(days=1)).isoformat(),
                'options': OPTIONS, 'versions': versions, 'universe_count': len(rows),
                'workers': args.workers, 'batch_size': args.batch_size, 'attempts': args.attempts,
                'raw_definition': 'Unmodified yfinance-returned frame; not original HTTP or exchange data.',
                'identity_limit': 'Baseline symbol and metadata match do not verify full-history continuity.'}
    save_json(run_dir/'run.json', run_meta)
    save_json(root/'latest_run.json', {'run_id':run_id, 'run_directory':str(run_dir), 'state':'running'})
    statuses = {r['universe_security_id']: initial_status(r, plan[r['universe_security_id']], args) for r in rows}
    journal = Journal(run_dir/'attempts.jsonl')
    segment_log = Journal(run_dir/'segments.jsonl')

    def checkpoint():
        records = list(statuses.values())
        save_csv(run_dir/'status.csv', records, STATUSES)
        if not args.dry_run:
            import pandas as pd
            save_parquet(run_dir/'status.parquet', pd.DataFrame(records))

    checkpoint()  # All 904 rows exist in inventory BEFORE any network calls.
    interrupted = False
    try:
        if args.dry_run:
            for row in rows:
                sid = row['universe_security_id']
                statuses[sid].update(status='held_identity_review' if plan[sid]['hold'] else 'planned',
                                     message=plan[sid]['hold'])
            run_meta['state'] = 'dry_run'
        else:
            engine = Downloader(root/'cache', journal, versions, args, fetcher)
            for offset in range(0, len(rows), args.batch_size):
                batch = rows[offset:offset+args.batch_size]
                with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futures = {pool.submit(process_security, r, plan[r['universe_security_id']], engine, run_dir, args): r for r in batch}
                    for f in concurrent.futures.as_completed(futures):
                        row = futures[f]
                        status, results = f.result()
                        statuses[row['universe_security_id']] = status
                        for result in results:
                            segment_log.add(**result)
                        checkpoint()  # Durable per-security recovery / inventory.
                        print(f"[{offset+sum(x.done() for x in futures)}/{len(rows)}] "
                              f"{row['universe_security_id']}: {status['status']} ({status['rows']} rows)", flush=True)
                if offset+len(batch)<len(rows) and not args.offline:
                    time.sleep(args.batch_pause)
            run_meta['state'] = 'completed_with_issues' if any(s['status']!='downloaded' for s in statuses.values()) else 'completed_acquisition'
    except KeyboardInterrupt:
        interrupted = True
        run_meta['state'] = 'interrupted'
    except Exception as e:
        run_meta.update(state='aborted', fatal_error=f'{type(e).__name__}: {e}')
        raise
    finally:
        if run_meta['state'] in ('interrupted','aborted'):
            for s in statuses.values():
                if s['status']=='pending':
                    s.update(status='not_completed', message='Run interrupted/aborted; rerun to use existing cache.')
        checkpoint()
        run_meta.update(finished_at_utc=utc_now(), status_counts=dict(Counter(s['status'] for s in statuses.values())),
                        total_price_rows=sum(s['rows'] for s in statuses.values()))
        save_json(run_dir/'run.json', run_meta)
        save_json(root/'latest_run.json', {'run_id':run_id, 'run_directory':str(run_dir), 'state':run_meta['state']})
    print(json.dumps({'state':run_meta['state'],'status_counts':run_meta['status_counts'],
                      'run_directory':str(run_dir)},indent=2))
    if interrupted:
        return 130
    return 2 if args.strict and not args.dry_run and run_meta['state']=='completed_with_issues' else 0


def main(argv=None):
    try:
        return run(arguments(argv))
    except (ValueError, OSError, ImportError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
