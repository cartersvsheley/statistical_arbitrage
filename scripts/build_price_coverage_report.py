#!/usr/bin/env python3
"""Audit download_prices.py output without downloading or modifying prices.

Jupyter:
 %pip install pandas pyarrow openpyxl pandas_market_calendars
 %run ./build_price_coverage_report.py --prices-root "data/raw"

Uses latest_run.json by default. --run-dir selects a specific run.
Uses that run's universe_input.csv (the frozen equity_universe_2023.csv).
--universe can supply an alternative only if its ID set matches the snapshot.
Outputs timestamped Excel and CSV reports under prices-root/coverage/.
Wait for acquisition to finish for a final report; running/interrupted runs are
reported as provisional. No cache files or earlier runs are silently combined.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(path, sid, sessions, start, end):
    import numpy as np
    import pandas as pd
    r = dict(file_state='missing_file', file_sha256='', rows=0,
             valid_close_sessions=0, coverage_full_window=0.0,
             first_valid_date=None, last_valid_date=None,
             internal_missing_sessions=None, coverage_observed_span=None,
             leading_missing_sessions=None, trailing_missing_sessions=None,
             duplicate_date_rows=0, invalid_dates=0, outside_window_rows=0,
             off_calendar_rows=0, missing_close_rows=0, invalid_close_rows=0,
             missing_adj_close_rows=None, zero_volume_rows=None,
             identity_in_file='', error='')
    valid = pd.DatetimeIndex([])
    gaps = []
    if not path.is_file():
        return r, valid, gaps
    try:
        r['file_sha256'] = sha(path)
        f = pd.read_parquet(path)
        r['rows'] = len(f)
        if not {'universe_security_id','date','Close'}.issubset(f.columns):
            raise ValueError('Missing security ID, date or Close column')
        if not f['universe_security_id'].eq(sid).all():
            raise ValueError('Security IDs inside file do not match roster key')
        dates = pd.to_datetime(f['date'], errors='coerce')
        if dates.dt.tz is not None:
            dates = dates.dt.tz_localize(None)
        dates = dates.dt.normalize()
        close = pd.to_numeric(f['Close'], errors='coerce')
        dup = dates.notna() & dates.duplicated(keep=False)
        in_window = dates.between(start, end)
        on_calendar = dates.isin(sessions)
        ok = close.gt(0) & np.isfinite(close)
        r.update(file_state='readable', invalid_dates=int(dates.isna().sum()),
                 duplicate_date_rows=int(dup.sum()),
                 outside_window_rows=int((dates.notna() & ~in_window).sum()),
                 off_calendar_rows=int((in_window & ~on_calendar).sum()),
                 missing_close_rows=int(close.isna().sum()),
                 invalid_close_rows=int((close.notna() & ~ok).sum()))
        if 'Adj Close' in f:
            adj = pd.to_numeric(f['Adj Close'], errors='coerce')
            r['missing_adj_close_rows'] = int((adj.isna() | ~np.isfinite(adj) | adj.le(0)).sum())
        if 'Volume' in f:
            r['zero_volume_rows'] = int(pd.to_numeric(f['Volume'], errors='coerce').eq(0).sum())
        if 'identity_status' in f:
            r['identity_in_file'] = ';'.join(sorted(set(f['identity_status'].dropna().astype(str))))
        # Duplicate dates excluded entirely: never pick a winning record silently.
        valid = pd.DatetimeIndex(dates[ok & in_window & on_calendar & ~dup]).sort_values().unique()
        r['valid_close_sessions'] = len(valid)
        r['coverage_full_window'] = len(valid)/len(sessions)
        if len(valid):
            span = sessions[(sessions >= valid.min()) & (sessions <= valid.max())]
            missing = span.difference(valid)
            r.update(first_valid_date=valid.min(), last_valid_date=valid.max(),
                     internal_missing_sessions=len(missing),
                     coverage_observed_span=len(valid)/len(span),
                     leading_missing_sessions=int((sessions < valid.min()).sum()),
                     trailing_missing_sessions=int((sessions > valid.max()).sum()))
            # Compact consecutive missing-session intervals, not calendar-day runs.
            positions = sessions.get_indexer(missing)
            groups = []
            for p in positions:
                if groups and p == groups[-1][-1]+1:
                    groups[-1].append(p)
                else:
                    groups.append([p])
            for group in groups:
                gaps.append(dict(universe_security_id=sid, gap_start=sessions[group[0]],
                                 gap_end=sessions[group[-1]], missing_sessions=len(group)))
    except Exception as exc:
        r.update(file_state='unreadable_or_wrong_identity', error=f'{type(exc).__name__}: {exc}')
        valid = pd.DatetimeIndex([])
    return r, valid, gaps


def run(args):
    import pandas as pd
    import pandas_market_calendars as mcal
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.formatting.rule import ColorScaleRule
    root = args.prices_root.expanduser().resolve()
    if args.run_dir:
        run_dir = args.run_dir.expanduser().resolve()
    else:
        pointer = load_json(root/'latest_run.json')
        run_id = str(pointer['run_id'])
        if Path(run_id).name != run_id:
            raise ValueError('Invalid run_id in latest_run.json')
        run_dir = root/'runs'/run_id
    meta = load_json(run_dir/'run.json')
    universe_path = args.universe or run_dir/'universe_input.csv'
    u = pd.read_csv(universe_path, dtype=str, keep_default_na=False)
    key = 'universe_security_id'
    if key not in u or u[key].eq('').any() or u[key].duplicated().any():
        raise ValueError('Universe must have unique nonempty universe_security_id values')
    if len(u) != args.expected_count:
        raise ValueError(f'Expected {args.expected_count} securities, found {len(u)}')
    if not u[key].map(lambda x: bool(re.fullmatch(r'[A-Za-z0-9_.-]+', x)) and x not in ('.','..')).all():
        raise ValueError('Unsafe security ID for file lookup')
    snap = run_dir/'universe_input.csv'
    if snap.exists():
        original = pd.read_csv(snap, dtype=str, keep_default_na=False)
        if set(original[key]) != set(u[key]):
            raise ValueError('Universe ID set differs from selected acquisition run')
        if meta.get('universe_sha256') and sha(snap) != meta['universe_sha256']:
            raise ValueError('Frozen run universe checksum mismatch')
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    if start > end:
        raise ValueError('Start must precede end')
    sessions = mcal.get_calendar('NYSE').schedule(start_date=start, end_date=end).index
    sessions = pd.DatetimeIndex(sessions).tz_localize(None).normalize()
    if not len(sessions):
        raise ValueError('No reference trading sessions in requested window')
    sp = run_dir/'status.csv'
    statuses = pd.read_csv(sp, dtype=str, keep_default_na=False) if sp.exists() else pd.DataFrame(columns=[key])
    if key not in statuses or statuses[key].duplicated().any():
        raise ValueError('Invalid or duplicate security IDs in status.csv')
    unknown = set(statuses[key])-set(u[key])
    if unknown:
        raise ValueError(f'Status has IDs outside universe: {sorted(unknown)[:5]}')
    status_map = statuses.set_index(key).to_dict('index')
    rows, gaps, years = [], [], []
    for i, rec in enumerate(u.to_dict('records'), 1):
        sid = rec[key]
        status = status_map.get(sid, {})
        r, valid, g = analyze(run_dir/'prices'/f'{sid}.parquet', sid, sessions, start, end)
        r = {**rec, **r}
        r['download_status'] = status.get('status', 'missing_status')
        r['download_identity_status'] = status.get('identity_status', '')
        r['download_message'] = status.get('message', '')
        r['download_warnings'] = status.get('warnings', '')
        r['mapping_gaps'] = status.get('mapping_gaps', '')
        r['expected_sessions'] = len(sessions)
        r['status_rows_disagree'] = bool(status.get('rows','').isdigit() and int(status['rows']) != r['rows'])
        rows.append(r)
        gaps.extend(g)
        for year in sorted(set(sessions.year)):
            expected = int((sessions.year == year).sum())
            observed = int((valid.year == year).sum())
            years.append({key:sid, 'year':int(year), 'valid_close_sessions':observed,
                          'expected_sessions':expected, 'coverage':observed/expected})
        if i % 100 == 0:
            print(f'Inspected {i}/{len(u)} securities', flush=True)
    coverage = pd.DataFrame(rows)
    yearly = pd.DataFrame(years)
    gap_frame = pd.DataFrame(gaps, columns=[key,'gap_start','gap_end','missing_sessions'])
    annual = yearly.groupby('year').agg(valid_security_sessions=('valid_close_sessions','sum'),
                                        possible_security_sessions=('expected_sessions','sum'),
                                        securities_with_prices=('valid_close_sessions',lambda x:int(x.gt(0).sum()))).reset_index()
    annual['coverage'] = annual.valid_security_sessions/annual.possible_security_sessions
    summary = pd.DataFrame([
        ('Universe securities',len(u)), ('Files readable',int(coverage.file_state.eq('readable').sum())),
        ('Securities with valid Close',int(coverage.valid_close_sessions.gt(0).sum())),
        ('Securities with no valid Close',int(coverage.valid_close_sessions.eq(0).sum())),
        ('Full-window coverage',int(coverage.valid_close_sessions.eq(len(sessions)).sum())),
        ('Securities with internal gaps',int(coverage.internal_missing_sessions.gt(0).sum())),
        ('Valid security sessions',int(coverage.valid_close_sessions.sum())),
        ('Possible security sessions',len(u)*len(sessions)),
    ], columns=['metric','value'])
    notes = [
        ('Run directory',str(run_dir)), ('Acquisition state',meta.get('state','unknown')),
        ('Report status','Final snapshot' if str(meta.get('state','')).startswith('completed') else 'Provisional: acquisition not completed'),
        ('Window',f'{args.start} through {args.end}, inclusive'),
        ('Acquisition requested window',f"{meta.get('start_inclusive')} through {meta.get('end_inclusive')}"),
        ('Reference calendar','NYSE sessions used as a common US equity benchmark; not issuer-specific listing eligibility.'),
        ('Calendar source','https://pandas-market-calendars.readthedocs.io/en/stable/usage.html'),
        ('Full-window coverage','Unique sessions with finite positive Close, excluding all duplicate-date rows, divided by all reference sessions.'),
        ('Observed-span coverage','Same numerator divided by sessions from first to last valid Close. Empty histories have no span ratio.'),
        ('Gaps','Internal missing sessions only. Leading/trailing missing history is separately counted. No inference of IPO, delisting, or halt.'),
        ('Identity','Coverage does not verify historical security continuity. Holds, warnings, and mapping gaps remain visible.'),
        ('Prices','Read-only analysis. No interpolation, repairs, cache mixing, or automatic exclusion of universe members.'),
        ('Selection','The December 2023 roster is a future-selected universe for earlier years; coverage does not remove selection bias.'),
        ('Missing adjusted close','Count includes missing, nonpositive or nonfinite adjusted prices; blank means column unavailable.'),
        ('Universe SHA256',sha(universe_path)),
    ]
    out = args.output or root/'coverage'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    out.mkdir(parents=True, exist_ok=False)
    coverage.to_csv(out/'price_coverage.csv', index=False)
    yearly.to_csv(out/'coverage_by_security_year.csv', index=False)
    gap_frame.to_csv(out/'internal_gaps.csv', index=False)
    tables = {'Summary':summary,'Annual coverage':annual,'Security coverage':coverage,
              'Download statuses':coverage.groupby('download_status').size().reset_index(name='securities'),
              'Internal gaps':gap_frame,'Definitions':pd.DataFrame(notes,columns=['item','description'])}
    with pd.ExcelWriter(out/'price_coverage_report.xlsx', engine='openpyxl') as writer:
        for name, frame in tables.items():
            frame.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            ws.freeze_panes = 'B2'
            ws.auto_filter.ref = ws.dimensions
            for c in ws[1]:
                c.font = Font(color='FFFFFF', bold=True)
                c.fill = PatternFill('solid',fgColor='16324F')
                c.alignment = Alignment(wrap_text=True, vertical='center')
            ws.row_dimensions[1].height = 44
            for col in ws.columns:
                label = str(col[0].value)
                width = min(48,max(16,len(label)+2))
                if name == 'Definitions' and col[0].column == 2:
                    width = 105
                ws.column_dimensions[col[0].column_letter].width = width
                for c in col[1:]:
                    # Keep any source text literal rather than spreadsheet formulas.
                    if isinstance(c.value,str):
                        c.data_type = 's'
                    c.alignment = Alignment(vertical='top',wrap_text=True)
                    if 'coverage' in label and name != 'Summary':
                        c.number_format = '0.0%'
                    if 'date' in label or label in ('gap_start','gap_end'):
                        c.number_format = 'yyyy-mm-dd'
                if label.startswith('coverage') and len(frame):
                    ws.conditional_formatting.add(f'{col[0].column_letter}2:{col[0].column_letter}{len(frame)+1}',ColorScaleRule(start_type='num',start_value=0,start_color='FADBD8',end_type='num',end_value=1,end_color='D5F5E3'))
            if name == 'Definitions':
                for row in range(2, ws.max_row+1):
                    ws.row_dimensions[row].height = 45
    manifest = dict(created_at_utc=datetime.now(timezone.utc).isoformat(),run_directory=str(run_dir),
                    run_metadata=meta,universe_sha256=sha(universe_path),
                    status_sha256=sha(sp) if sp.exists() else None,
                    script_sha256=sha(Path(__file__)),start=args.start,end=args.end,
                    calendar='NYSE',expected_count=args.expected_count,
                    packages={p:importlib.metadata.version(p) for p in ['pandas','pyarrow','openpyxl','pandas_market_calendars']})
    (out/'report_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(summary.to_string(index=False))
    print(f'\nReport saved to: {out.resolve()}')
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--prices-root',type=Path,default=Path('data/raw'))
    p.add_argument('--run-dir',type=Path)
    p.add_argument('--universe',type=Path)
    p.add_argument('--output',type=Path,help='New output directory; must not already exist')
    p.add_argument('--start',default='2000-01-01')
    p.add_argument('--end',default='2025-12-31')
    p.add_argument('--expected-count',type=int,default=904)
    try:
        run(p.parse_args())
    except ImportError as e:
        print(f'Missing dependency: {e}. In Jupyter run: %pip install pandas pyarrow openpyxl pandas_market_calendars',file=sys.stderr)
        return 1
    except (ValueError,OSError,KeyError) as e:
        print(f'ERROR: {e}',file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
