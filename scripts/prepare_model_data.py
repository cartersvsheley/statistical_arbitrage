#!/usr/bin/env python3
"""Prepare historical-ID price matrices; no downloads, imputation, or model fitting.

Install: python -m pip install pandas numpy pyarrow pandas_market_calendars
Jupyter example (formation window is an explicit research choice):
 %run ./prepare_model_data.py --prices-root "data/raw" --formation-start 2021-01-01 --formation-end 2023-12-29 --test-start 2024-01-01 --test-end 2025-12-31

Default output: data/processed relative to the current working directory.
Uses one acquisition run: latest_run.json or --run-dir. Reads EVERY normalized
price file in that run, never silently combines cache snapshots or old runs.
Uses its frozen universe_input.csv unless --universe is supplied. IDs must match.
All 904 columns remain in adjusted_prices and daily_returns, including empty
histories. Formation matrices contain eligible columns only, with original
missing cells retained. Coverage report contains every universe row.

Daily arithmetic return = AdjClose[t] / AdjClose[previous session] - 1.
No fill, interpolation, winsorization, or raw-Close fallback. Adj Close must be
finite and positive. Duplicate security dates are all masked (never pick one).
NYSE sessions provide the common US-equity calendar. Non-session rows are logged.
Formation returns are recomputed WITHIN formation, making its first row NaN.
Coverage denominator for returns is number of formation sessions minus one.
Full-history returns retain cross-boundary returns for later test slicing.

Default eligibility (all configurable): >=98% formation price AND return
coverage, >=504 returns, <=5 consecutive missing price sessions, both endpoints
present, and finite positive formation return standard deviation. These are
research defaults, not optimized thresholds. Identity policy 'baseline' accepts
baseline_symbol_history_unverified and reviewer_verified_mapping rows only,
with unverified history prominently flagged. 'verified' accepts only the latter.
No ticker lookup, inferred successor, or issuer-level identifier substitution.
Identity policy uses each row's provenance, never whole-run status to filter
formation. Missing, unresolved, and unknown identities are masked.

The end-2023 universe induces earlier selection bias. A 2024-2025 test evaluates
this selected universe conditionally, not a bias-free historical investable
market. Current adjusted prices may contain retrospective provider revisions.
Formation-only selection cannot undo those source limitations. Missing test
prices/delistings require later explicit execution/valuation rules.

Formation matrices may still have NaNs: before PCA define a formation-only
missing-data rule. Do not simply fill zero. Fit scaling/PCA/clustering only on
formation data. This script does not perform those operations.

Outputs: six requested data files plus preparation_manifest.json containing
configuration, hashes, versions, limitations, and file-level quality diagnostics.
Writes a complete staging directory before publishing. Existing output requires
--overwrite, which retains it as a timestamped sibling backup.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

VERSION = '1.0.0'
KEY = 'universe_security_id'
BASELINE = 'baseline_symbol_history_unverified'
VERIFIED = 'reviewer_verified_mapping'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--prices-root', type=Path, default=Path('data/raw'))
    p.add_argument('--run-dir', type=Path, help='Explicit acquisition run, overrides latest pointer')
    p.add_argument('--universe', type=Path, help='Defaults to frozen universe_input.csv in selected run')
    p.add_argument('--output', type=Path, default=Path('data/processed'))
    p.add_argument('--history-start', default='2000-01-01')
    p.add_argument('--formation-start', required=True)
    p.add_argument('--formation-end', required=True)
    p.add_argument('--test-start', required=True)
    p.add_argument('--test-end', required=True)
    p.add_argument('--min-price-coverage', type=float, default=.98)
    p.add_argument('--min-return-coverage', type=float, default=.98)
    p.add_argument('--min-return-observations', type=int, default=504)
    p.add_argument('--max-missing-price-run', type=int, default=5)
    p.add_argument('--allow-missing-endpoints', action='store_true')
    p.add_argument('--identity-policy', choices=['baseline','verified'], default='baseline')
    p.add_argument('--expected-count', type=int, default=904)
    p.add_argument('--allow-incomplete-run', action='store_true', help='Produce explicitly provisional output')
    p.add_argument('--overwrite', action='store_true', help='Preserve previous output in a sibling backup')
    return p.parse_args(argv)


def max_missing_run(series):
    best = current = 0
    for missing in series.isna():
        current = current+1 if missing else 0
        best = max(best, current)
    return best


def arithmetic_returns(prices):
    import numpy as np
    return (prices/prices.shift(1)-1).replace([np.inf,-np.inf], float('nan'))


def load_security(path, sid, calendar, formation_index, args):
    import numpy as np
    import pandas as pd
    empty = pd.Series(np.nan,index=calendar,name=sid,dtype=float)
    fm = {KEY:sid,'formation_duplicate_rows':0,'formation_invalid_adjusted_rows':0,
          'formation_identity_rejected_rows':0,'formation_baseline_rows':0,
          'formation_off_calendar_rows':0}
    audit = {'file':str(path),'state':'missing_file','sha256':None,'rows':0}
    if not path.exists():
        return empty, fm, audit
    try:
        data = path.read_bytes()
        audit['sha256'] = digest(data)
        frame = pd.read_parquet(io.BytesIO(data))
        audit['rows'] = len(frame)
        required = {KEY,'date','Adj Close','identity_status'}
        if not frame.columns.is_unique or not required.issubset(frame.columns):
            raise ValueError('Expected unique columns including ID, date, Adj Close and identity_status')
        if not frame[KEY].eq(sid).all():
            raise ValueError('Embedded security ID does not match filename/universe ID')
        dates = pd.to_datetime(frame['date'], errors='coerce')
        if dates.dt.tz is not None:
            dates = dates.dt.tz_localize(None)
        if dates.isna().any() or not dates.eq(dates.dt.normalize()).all():
            raise ValueError('Invalid/non-midnight normalized date; cannot safely attribute rows to periods')
        formation = dates.between(pd.Timestamp(args.formation_start),pd.Timestamp(args.formation_end))
        on_calendar = dates.isin(calendar)
        duplicates = dates.duplicated(keep=False)
        values = pd.to_numeric(frame['Adj Close'],errors='coerce')
        invalid = ~np.isfinite(values) | values.le(0)
        allowed = [VERIFIED] if args.identity_policy=='verified' else [BASELINE,VERIFIED]
        identity_ok = frame['identity_status'].isin(allowed)
        if 'currency' in frame:
            identity_ok &= frame['currency'].eq('USD')
        valid = on_calendar & ~duplicates & ~invalid & identity_ok
        fm.update(formation_duplicate_rows=int((formation & duplicates).sum()),
                  formation_invalid_adjusted_rows=int((formation & invalid).sum()),
                  formation_identity_rejected_rows=int((formation & ~identity_ok).sum()),
                  formation_baseline_rows=int((formation & valid & frame['identity_status'].eq(BASELINE)).sum()),
                  formation_off_calendar_rows=int((formation & ~on_calendar).sum()))
        result = pd.Series(values[valid].to_numpy(dtype=float),index=pd.DatetimeIndex(dates[valid]),name=sid).reindex(calendar)
        audit.update(state='read',duplicate_rows=int(duplicates.sum()),invalid_adjusted_rows=int(invalid.sum()),
                     identity_rejected_rows=int((~identity_ok).sum()),off_calendar_or_outside_window_rows=int((~on_calendar).sum()))
        return result, fm, audit
    except Exception as exc:
        # Structural file failures are not economic eligibility filters.
        audit.update(state='rejected_file',error=f'{type(exc).__name__}: {exc}')
        return empty, fm, audit


def run(args):
    import numpy as np
    import pandas as pd
    import pandas_market_calendars as mcal
    dates = {}
    for name in ['history_start','formation_start','formation_end','test_start','test_end']:
        value = getattr(args,name)
        parsed = datetime.strptime(value,'%Y-%m-%d')
        if parsed.strftime('%Y-%m-%d') != value:
            raise ValueError('Dates must use YYYY-MM-DD')
        dates[name] = pd.Timestamp(value)
    if not (dates['history_start'] <= dates['formation_start'] < dates['formation_end'] < dates['test_start'] <= dates['test_end']):
        raise ValueError('Require history_start <= formation_start < formation_end < test_start <= test_end')
    if not (0 <= args.min_price_coverage <= 1 and 0 <= args.min_return_coverage <= 1):
        raise ValueError('Coverage thresholds must lie between 0 and 1')
    if args.min_return_observations < 2 or args.max_missing_price_run < 0 or args.expected_count < 1:
        raise ValueError('Require >=2 returns, nonnegative gap limit, and positive expected count')
    output = args.output.expanduser().resolve()
    if output.exists() and not args.overwrite:
        raise ValueError(f'{output} already exists. Use --overwrite to retain it as a backup and replace.')
    root = args.prices_root.expanduser().resolve()
    if args.run_dir:
        run_dir = args.run_dir.expanduser().resolve()
    else:
        pointer = read_json(root/'latest_run.json')
        rid = str(pointer['run_id'])
        if not re.fullmatch(r'[A-Za-z0-9_-]+',rid):
            raise ValueError('Invalid acquisition run ID')
        run_dir = root/'runs'/rid
    if output == run_dir or output in run_dir.parents:
        raise ValueError('Output cannot contain the input acquisition run')
    meta_bytes = (run_dir/'run.json').read_bytes()
    meta = json.loads(meta_bytes)
    completed = meta.get('state') in ['completed_acquisition','completed_with_issues']
    if not completed and not args.allow_incomplete_run:
        raise ValueError(f"Acquisition state is {meta.get('state')!r}. Finish download or use --allow-incomplete-run for provisional output.")
    snapshot = run_dir/'universe_input.csv'
    ub = (args.universe or snapshot).read_bytes()
    universe = pd.read_csv(io.BytesIO(ub),dtype=str,keep_default_na=False)
    if KEY not in universe or universe[KEY].duplicated().any() or universe[KEY].eq('').any():
        raise ValueError('Universe requires unique nonempty historical security IDs')
    if len(universe) != args.expected_count:
        raise ValueError(f'Expected {args.expected_count} securities; got {len(universe)}')
    if not universe[KEY].map(lambda x:bool(re.fullmatch(r'[A-Za-z0-9_.-]+',x)) and x not in ('.','..')).all():
        raise ValueError('Unsafe security ID for filename lookup')
    if snapshot.exists():
        sb = snapshot.read_bytes()
        if meta.get('universe_sha256') and digest(sb)!=meta['universe_sha256']:
            raise ValueError('Acquisition universe checksum mismatch')
        source_u = pd.read_csv(io.BytesIO(sb),dtype=str,keep_default_na=False)
        if set(source_u[KEY]) != set(universe[KEY]):
            raise ValueError('Universe IDs differ from acquisition run')
        for field in ['historical_ticker','as_of_date']:
            if field in source_u and field in universe:
                if not source_u.set_index(KEY)[field].sort_index().equals(universe.set_index(KEY)[field].sort_index()):
                    raise ValueError(f'Universe {field} differs from frozen acquisition input')
    ids = universe[KEY].tolist()
    prices_dir = run_dir/'prices'
    if not prices_dir.is_dir():
        if completed:
            print('WARNING: no prices directory; all universe IDs will remain as missing.')
    unknown_files = [p.name for p in prices_dir.glob('*.parquet') if p.stem not in set(ids)]
    if unknown_files:
        raise ValueError(f'Price files outside universe: {unknown_files[:10]}')
    calendar = pd.DatetimeIndex(mcal.get_calendar('NYSE').schedule(start_date=args.history_start,end_date=args.test_end).index).tz_localize(None)
    calendar.name = 'date'
    fi = calendar[(calendar>=dates['formation_start']) & (calendar<=dates['formation_end'])]
    ti = calendar[(calendar>=dates['test_start']) & (calendar<=dates['test_end'])]
    if len(fi)<3 or not len(ti):
        raise ValueError('Formation needs at least 3 sessions and test at least 1')
    series, diagnostics, audits = [], [], []
    for i,sid in enumerate(ids,1):
        s,d,a = load_security(prices_dir/f'{sid}.parquet',sid,calendar,fi,args)
        series.append(s); diagnostics.append(d); audits.append({KEY:sid,**a})
        if i%100==0:
            print(f'Prepared {i}/{len(ids)} histories',flush=True)
    if (run_dir/'run.json').read_bytes()!=meta_bytes:
        raise ValueError('Acquisition run changed during processing. Wait for completion and rerun.')
    prices = pd.concat(series,axis=1).reindex(columns=ids)
    returns = arithmetic_returns(prices)
    formation_prices_all = prices.loc[fi]
    formation_returns_all = arithmetic_returns(formation_prices_all)
    report = pd.DataFrame(diagnostics).set_index(KEY)
    for sid in ids:
        p = formation_prices_all[sid]
        r = formation_returns_all[sid].iloc[1:]
        n = int(r.notna().sum())
        pc = float(p.notna().mean()); rc = n/len(r)
        gap = max_missing_run(p)
        sd = float(r.std(ddof=1)) if n>=2 else np.nan
        reasons = []
        if pc < args.min_price_coverage: reasons.append('insufficient_price_coverage')
        if rc < args.min_return_coverage: reasons.append('insufficient_return_coverage')
        if n < args.min_return_observations: reasons.append('insufficient_return_observations')
        if gap > args.max_missing_price_run: reasons.append('missing_price_run_too_long')
        if not args.allow_missing_endpoints and (pd.isna(p.iloc[0]) or pd.isna(p.iloc[-1])):
            reasons.append('missing_formation_endpoint')
        if not np.isfinite(sd) or sd<=0: reasons.append('zero_or_undefined_return_variance')
        values = dict(formation_price_observations=int(p.notna().sum()),formation_sessions=len(p),
                      formation_price_coverage=pc,formation_return_observations=n,formation_return_opportunities=len(r),
                      formation_return_coverage=rc,max_missing_price_run=gap,formation_return_std=sd,
                      formation_first_valid_date=str(p.first_valid_index().date()) if p.first_valid_index() is not None else '',
                      formation_last_valid_date=str(p.last_valid_index().date()) if p.last_valid_index() is not None else '',
                      formation_eligible=not reasons,exclusion_reasons=';'.join(reasons),
                      identity_warning='baseline_history_unverified' if report.loc[sid,'formation_baseline_rows'] else '')
        for k,v in values.items(): report.loc[sid,k]=v
    report = report.reset_index()
    for field in ['formation_price_observations','formation_sessions','formation_return_observations',
                  'formation_return_opportunities','max_missing_price_run']:
        report[field] = report[field].astype('int64')
    report['formation_eligible'] = report['formation_eligible'].astype(bool)
    report['input_file_state'] = [a['state'] for a in audits]
    report['input_file_error'] = [a.get('error','') for a in audits]
    report = universe.merge(report,on=KEY,how='left',validate='one_to_one')
    eligible = report.loc[report.formation_eligible.eq(True)].copy()
    selected = eligible[KEY].tolist()
    fp = formation_prices_all[selected]; fr = formation_returns_all[selected]
    manifest = dict(script_version=VERSION,created_at_utc=datetime.now(timezone.utc).isoformat(),
        script_sha256=digest(Path(__file__).read_bytes()),universe_sha256=digest(ub),run_directory=str(run_dir),
        acquisition_metadata=meta,provisional=not completed,
        configuration={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
        packages={k:importlib.metadata.version(k) for k in ['pandas','numpy','pyarrow','pandas_market_calendars']},
        universe_count=len(ids),eligible_count=len(selected),formation_sessions=len(fi),test_sessions=len(ti),
        complete_formation_return_rows=int(fr.iloc[1:].notna().all(axis=1).sum()) if selected else 0,
        formation_missing_return_cells_after_first_row=int(fr.iloc[1:].isna().sum().sum()),
        calendar='NYSE common US equity sessions',return_definition='arithmetic, adjacent exchange sessions, no fills',
        formation_definition='Recompute returns within formation; first formation row is NaN. Eligibility uses formation observations only.',
        matrix_columns='All universe IDs in full matrices; only eligible IDs in formation matrices. NaNs retained.',
        limitations=[
            'End-2023 membership selection biases earlier periods. 2024-2025 is a conditional evaluation of this universe.',
            'Current provider adjusted prices are retrospectively adjusted/revised, not point-in-time vintages.',
            'Baseline identity policy accepts unverified history and does not certify security continuity.',
            'PCA still requires an explicit formation-only missing-data policy. No scaling or imputation fitted here.',
            'No test-period data-quality or survival filter is used for eligibility; missing test observations remain.',
            'Structural file integrity failure may prevent reading formation data; this is logged, not treated as economic evidence.'
        ],file_audit=audits,
        references=['https://pandas-market-calendars.readthedocs.io/en/stable/usage.html',
                    'https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.shift.html'])
    output.parent.mkdir(parents=True,exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.prepare_',dir=output.parent))
    backup = None
    try:
        for name,df in [('adjusted_prices',prices),('daily_returns',returns),('formation_prices',fp),('formation_returns',fr)]:
            df.to_parquet(stage/f'{name}.parquet',engine='pyarrow',index=True)
        eligible.to_csv(stage/'formation_eligible_universe.csv',index=False)
        report.to_csv(stage/'formation_coverage_report.csv',index=False)
        manifest['output_sha256'] = {p.name:digest(p.read_bytes()) for p in sorted(stage.iterdir())}
        (stage/'preparation_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False),encoding='utf-8')
        if output.exists():
            backup = output.with_name(output.name+'.backup_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f'))
            output.rename(backup)
        try:
            stage.rename(output)
        except Exception:
            if backup is not None: backup.rename(output)
            raise
    finally:
        if stage.exists(): shutil.rmtree(stage)
    print(f'Saved {len(ids)} security columns; {len(selected)} formation eligible. Output: {output}')
    print(f'Complete formation return rows across eligible columns: {manifest["complete_formation_return_rows"]}')
    print('NaNs preserved. Eligibility does not certify identity or remove end-2023 universe selection bias.')
    return output


def main(argv=None):
    try:
        run(parse_args(argv))
        return 0
    except ImportError as exc:
        print(f'Missing dependency: {exc}\nInstall: %pip install pandas numpy pyarrow pandas_market_calendars',file=sys.stderr)
    except (OSError,ValueError,KeyError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
    return 1


if __name__=='__main__':
    raise SystemExit(main())
