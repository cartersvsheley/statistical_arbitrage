#!/usr/bin/env python3
"""PCA factor-exposure clustering and exploratory pair screening.

Example from the project working directory (inputs in data/processed):
 python pca_ward_pairs.py

For data stored elsewhere, pass --returns, --prices and --eligible explicitly.

Dependencies: pandas numpy pyarrow scikit-learn scipy statsmodels.
Input columns are historical universe_security_id values. Formation eligibility
is read from the supplied CSV. Fundamentals are intentionally not included.

Method:
1. Keep eligible IDs in roster order. Never join prices on ticker.
2. Drop dates that do not have finite returns for every eligible stock. No fill.
3. Z-score each stock's daily formation returns (sample SD).
4. PCA across stocks on those standardized returns. The default factor count is
   selected by parallel analysis; an 80% variance cutoff is a sensitivity option.
5. Select common factors by 95th-percentile parallel analysis using independent
   circular shifts of each stock series (preserves each series autocorrelation
   approximately while breaking cross-stock timing); 100 null replications. The
   80% variance rule is available as a sensitivity option, not the default.
6. Exposure of stock i to PC k is corr(z_i, standardized PC_k) = v_ik*sqrt(lambda_k).
7. Ward/euclidean cluster those exposure vectors. Candidate pairs are the
   closest N names in each Ward cluster. Defaults are 40 clusters, 10 pairs per
   cluster. These are transparent discovery settings, not optimized values.
8. For each candidate, test log adjusted-price levels with Engle-Granger in
   both orientations; pair p = min(1, 2*min(p_xy,p_yx)) to account for direction
   selection. Apply Benjamini-Hochberg across candidate pairs. Estimate the
   residual AR(1) coefficient and half-life. This is an in-formation screen,
   not out-of-sample evidence. Candidate-selection and model search also make
   nominal p-values optimistic; validate frozen pairs on 2024-2025 separately.

No transaction costs, hedge rebalancing, shorting constraints, borrow fees,
execution, or trading strategy are tested. End-2023 constituent selection
creates survivorship/selection bias in earlier years; the 2024-2025 test is
conditional on this end-2023 universe. Yahoo adjusted prices may be revised.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys
import tempfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bh_qvalues(pvalues):
    import numpy as np
    p = np.asarray(pvalues,dtype=float)
    q = np.full(len(p),np.nan)
    valid = np.flatnonzero(np.isfinite(p))
    if len(valid)==0: return q
    order = valid[np.argsort(p[valid])]
    ranked = p[order]*len(order)/np.arange(1,len(order)+1)
    q_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    q[order] = np.minimum(q_sorted,1.0)
    return q


def mean_reversion(spread):
    import numpy as np
    x=np.asarray(spread,dtype=float)
    lag=x[:-1]; now=x[1:]
    design=np.column_stack([np.ones(len(lag)),lag])
    intercept,phi=np.linalg.lstsq(design,now,rcond=None)[0]
    half_life=(-np.log(2)/np.log(phi)) if 0<phi<1 else np.nan
    return float(phi),float(intercept),float(half_life) if np.isfinite(half_life) else np.nan


def adf_pvalue(series):
    """Support both legacy tuple results and newer statsmodels result objects."""
    import inspect
    from statsmodels.tsa.stattools import adfuller
    kwargs = dict(regression='c', autolag='AIC')
    if 'result_object' in inspect.signature(adfuller).parameters:
        kwargs['result_object'] = True
    result = adfuller(series, **kwargs)
    return float(result.pvalue if hasattr(result, 'pvalue') else result[1])


def test_pair(id_y,id_x,prices,meta,cluster,distance,min_obs):
    import numpy as np
    import pandas as pd
    from statsmodels.tsa.stattools import coint
    a=pd.to_numeric(prices[id_y],errors='coerce')
    b=pd.to_numeric(prices[id_x],errors='coerce')
    valid=np.isfinite(a)&np.isfinite(b)&a.gt(0)&b.gt(0)
    a=a.loc[valid];b=b.loc[valid]
    base={
        'universe_security_id_y':id_y,'historical_ticker_y':meta.get(id_y,{}).get('historical_ticker',''),
        'company_name_y':meta.get(id_y,{}).get('company_name',''),
        'universe_security_id_x':id_x,'historical_ticker_x':meta.get(id_x,{}).get('historical_ticker',''),
        'company_name_x':meta.get(id_x,{}).get('company_name',''),
        'ward_cluster':int(cluster),'exposure_distance':float(distance),'observations':len(a),
        'first_date':a.index.min() if len(a) else pd.NaT,'last_date':a.index.max() if len(a) else pd.NaT}
    if len(a)<min_obs:
        return {**base,'orientation':'','hedge_ratio':np.nan,'coint_p_y_on_x':np.nan,
                'coint_p_x_on_y':np.nan,'coint_pair_p_bonferroni':np.nan,
                'adf_residual_p':np.nan,'ar1_phi':np.nan,'ar1_intercept':np.nan,
                'half_life_sessions':np.nan,'error':'insufficient_overlapping_prices'}
    ly=np.log(a.to_numpy());lx=np.log(b.to_numpy())
    py=float(coint(ly,lx,trend='c',autolag='aic')[1])
    px=float(coint(lx,ly,trend='c',autolag='aic')[1])
    orient='y_on_x' if py<=px else 'x_on_y'
    response,predictor=(ly,lx) if orient=='y_on_x' else (lx,ly)
    alpha,beta=np.linalg.lstsq(np.column_stack([np.ones(len(predictor)),predictor]),response,rcond=None)[0]
    resid=response-(alpha+beta*predictor)
    adf_p=adf_pvalue(resid)
    phi,intercept,half=mean_reversion(resid)
    return {**base,'orientation':orient,'hedge_ratio':float(beta),'hedge_intercept':float(alpha),
            'coint_p_y_on_x':py,'coint_p_x_on_y':px,
            'coint_pair_p_bonferroni':min(1.0,2*min(py,px)),
            'adf_residual_p':adf_p,'ar1_phi':phi,'ar1_intercept':intercept,
            'half_life_sessions':half,'error':''}


def default_input(filename):
    """Find standard prepared inputs in cwd or beside this script."""
    cwd=Path.cwd()
    script_dir=Path(__file__).resolve().parent if '__file__' in globals() else cwd
    candidates=[cwd/'data'/'processed'/filename, cwd/filename,
                script_dir/'data'/'processed'/filename, script_dir/filename,
                script_dir.parent/'data'/'processed'/filename]
    return next((p for p in candidates if p.is_file()), candidates[0])


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--returns',type=Path,default=default_input('formation_returns.parquet'))
    p.add_argument('--prices',type=Path,default=default_input('formation_prices.parquet'))
    p.add_argument('--eligible',type=Path,default=default_input('formation_eligible_universe.csv'))
    p.add_argument('--output-dir',type=Path,default=Path('data/model/pca_ward'))
    p.add_argument('--factor-selection',choices=['parallel','variance'],default='parallel')
    p.add_argument('--variance-threshold',type=float,default=.80)
    p.add_argument('--parallel-replicates',type=int,default=100)
    p.add_argument('--parallel-percentile',type=float,default=.95)
    p.add_argument('--random-seed',type=int,default=20231021)
    p.add_argument('--n-clusters',type=int,default=40)
    p.add_argument('--pairs-per-cluster',type=int,default=10)
    p.add_argument('--min-cointegration-observations',type=int,default=500)
    p.add_argument('--expected-count',type=int,default=821)
    p.add_argument('--overwrite',action='store_true')
    a=p.parse_args(argv)
    if not 0<a.variance_threshold<1 or not 0<a.parallel_percentile<1: p.error('thresholds must be between 0 and 1')
    if a.parallel_replicates<20: p.error('use at least 20 parallel-analysis replications')
    if a.n_clusters<2 or a.pairs_per_cluster<1 or a.expected_count<2 or a.min_cointegration_observations<30:
        p.error('cluster count, pair count, universe size and observation minimum must be positive (min observations >=30)')
    return a


def run(a):
    import numpy as np
    import pandas as pd
    from sklearn.decomposition import PCA
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import pdist, squareform
    outputs=[a.returns,a.prices,a.eligible]
    for arg_name,f in zip(['--returns','--prices','--eligible'],outputs):
        if not f.is_file():
            raise FileNotFoundError(f"Cannot find {f}. Place the prepared files in data/processed, or pass {arg_name} with its full path.")
    out=a.output_dir.expanduser().resolve()
    if out.exists() and not a.overwrite: raise ValueError(f'{out} exists; use --overwrite to back it up')
    elig=pd.read_csv(a.eligible,dtype=str,keep_default_na=False)
    key='universe_security_id'
    needed={key,'historical_ticker','company_name'}
    if not needed.issubset(elig): raise ValueError(f'Eligibility CSV needs {sorted(needed)}')
    if elig[key].duplicated().any() or len(elig)!=a.expected_count: raise ValueError(f'Expected {a.expected_count} unique eligible rows; found {len(elig)}')
    if 'formation_eligible' in elig and not elig.formation_eligible.astype(str).str.lower().eq('true').all():
        raise ValueError('Eligibility file contains non-eligible rows')
    ids=elig[key].tolist()
    returns=pd.read_parquet(a.returns)
    prices=pd.read_parquet(a.prices)
    for label,df in [('returns',returns),('prices',prices)]:
        if not isinstance(df.index,pd.DatetimeIndex) or not df.index.is_unique or not df.columns.is_unique:
            raise ValueError(f'{label} must have unique datetime index and unique security-ID columns')
        missing=set(ids)-set(df.columns)
        if missing: raise ValueError(f'{label} missing {len(missing)} eligible security IDs; first: {sorted(missing)[:5]}')
    if not returns.index.equals(prices.index):
        raise ValueError('Formation return and price dates differ; align upstream with evidence, not implicit reindexing')
    R=returns.loc[:,ids].apply(pd.to_numeric,errors='coerce')
    finite=np.isfinite(R.to_numpy())
    complete=finite.all(axis=1)
    dropped_dates=R.index[~complete]
    R=R.loc[complete]
    if len(R)<a.min_cointegration_observations: raise ValueError(f'Only {len(R)} complete return dates available')
    if not np.isfinite(R.to_numpy()).all(): raise ValueError('Non-finite return remains after complete-date filter')
    means=R.mean(axis=0)
    stds=R.std(axis=0,ddof=1)
    constant=stds.le(0)|~np.isfinite(stds)
    if constant.any(): raise ValueError(f'{int(constant.sum())} zero-variance stocks cannot be standardized; resolve explicitly')
    Z=(R-means)/stds
    pca=PCA(svd_solver='full')
    scores_all=pca.fit_transform(Z.to_numpy())
    cumulative=np.cumsum(pca.explained_variance_ratio_)
    if a.factor_selection=='variance':
        k=int(np.searchsorted(cumulative,a.variance_threshold)+1)
    else:
        # Circular shifts retain each series' ordered values/autocorrelation but break
        # synchronized cross-sectional moves. Use a fixed seed for repeatability.
        rng=np.random.default_rng(a.random_seed)
        x=Z.to_numpy(); nobs,nstocks=x.shape
        null_eigenvalues=np.empty((a.parallel_replicates,min(nobs,nstocks)))
        for b in range(a.parallel_replicates):
            shifted=np.column_stack([np.roll(x[:,j],int(rng.integers(1,nobs))) for j in range(nstocks)])
            eig=np.linalg.eigvalsh((shifted@shifted.T)/(nobs-1))[::-1]
            null_eigenvalues[b,:]=eig[:null_eigenvalues.shape[1]]
        null_cut=np.quantile(null_eigenvalues,a.parallel_percentile,axis=0)
        observed=pca.explained_variance_
        above=observed>null_cut
        k=0
        for passes in above:
            if not passes: break
            k+=1
        if k==0: raise ValueError('Parallel analysis retained no common factors; inspect returns/data and choose a prespecified sensitivity setting')
    k=min(max(k,1),scores_all.shape[1])
    scores=scores_all[:,:k]
    # Correlations of standardized stocks with unit-variance PC factor scores.
    exposures=pca.components_[:k,:].T*np.sqrt(pca.explained_variance_[:k])
    pc_names=[f'PC{i:03d}' for i in range(1,k+1)]
    exposure_df=pd.DataFrame(exposures,index=ids,columns=pc_names)
    exposure_df.index.name=key
    factor_df=pd.DataFrame(scores/np.sqrt(pca.explained_variance_[:k]),index=R.index,columns=pc_names)
    factor_df.index.name='date'
    zout=Z.copy();zout.index.name='date'
    model=linkage(pdist(exposures,metric='euclidean'),method='ward',optimal_ordering=False)
    cluster_ids=fcluster(model,t=min(a.n_clusters,len(ids)-1),criterion='maxclust')
    cluster_df=elig[[key,'historical_ticker','company_name']].copy()
    cluster_df['ward_cluster']=cluster_ids
    cluster_df['cluster_size']=cluster_df.groupby('ward_cluster')[key].transform('count')
    cluster_df['pca_components']=k
    cluster_df['cumulative_variance_explained']=float(cumulative[k-1])
    distances=squareform(pdist(exposures,metric='euclidean'))
    id_index={sid:i for i,sid in enumerate(ids)}
    pair_rows=[]
    for cluster in sorted(set(cluster_ids)):
        members=np.flatnonzero(cluster_ids==cluster)
        candidates=[]
        for ii,pos_i in enumerate(members):
            for pos_j in members[ii+1:]:
                candidates.append((float(distances[pos_i,pos_j]),ids[pos_i],ids[pos_j]))
        candidates.sort()
        pair_rows.extend((cluster,d,x,y) for d,x,y in candidates[:a.pairs_per_cluster])
    meta={r[key]:r for r in elig.to_dict('records')}
    from concurrent.futures import ThreadPoolExecutor
    pair_results=[]
    for cluster,d,x,y in pair_rows:
        pair_results.append(test_pair(y,x,prices,meta,cluster,d,a.min_cointegration_observations))
    pairs=pd.DataFrame(pair_results)
    if len(pairs):
        pairs['coint_q_value_bh']=bh_qvalues(pairs.coint_pair_p_bonferroni)
        pairs['cointegration_fdr_5pct']=pairs.coint_q_value_bh.le(.05)
        pairs['mean_reversion_ar1_stable']=pairs.ar1_phi.gt(0)&pairs.ar1_phi.lt(1)
        pairs['residual_adf_p_descriptive_only']=pairs.adf_residual_p
        pairs['exploratory_candidate_pass']=pairs.cointegration_fdr_5pct & pairs.mean_reversion_ar1_stable
        pairs=pairs.sort_values(['exploratory_candidate_pass','coint_q_value_bh','exposure_distance'],ascending=[False,True,True],na_position='last')
    variance=pd.DataFrame({'component':pc_names,'explained_variance_ratio':pca.explained_variance_ratio_[:k],
                           'cumulative_variance_ratio':cumulative[:k],'eigenvalue':pca.explained_variance_[:k]})
    out.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.pca_ward_',dir=out.parent)); backup=None
    try:
        Z.to_parquet(stage/'standardized_formation_returns.parquet')
        factor_df.to_parquet(stage/'pca_factor_returns.parquet')
        exposure_df.to_csv(stage/'pca_factor_exposures.csv')
        variance.to_csv(stage/'pca_explained_variance.csv',index=False)
        cluster_df.to_csv(stage/'ward_cluster_assignments.csv',index=False)
        pairs.to_csv(stage/'candidate_pairs_and_tests.csv',index=False)
        pd.DataFrame({'date':dropped_dates}).to_csv(stage/'excluded_incomplete_dates.csv',index=False)
        manifest={
            'created_at_utc':datetime.now(timezone.utc).isoformat(),'script_version':'1.0.1','script_sha256':sha(Path(__file__)),
            'input_sha256':{f.name:sha(f) for f in outputs},
            'parameters':{'expected_security_count':a.expected_count,'complete_return_dates':len(R),
                          'excluded_incomplete_dates':[str(d.date()) for d in dropped_dates],
                          'return_standardization':'Each security standardized over its formation dates using sample standard deviation',
                          'pca_components':k,'factor_selection':a.factor_selection,'variance_threshold':a.variance_threshold,
                          'parallel_replicates':a.parallel_replicates if a.factor_selection=='parallel' else None,
                          'parallel_percentile':a.parallel_percentile if a.factor_selection=='parallel' else None,
                          'random_seed':a.random_seed if a.factor_selection=='parallel' else None,
                          'actual_cumulative_explained_variance':float(cumulative[k-1]),
                          'exposure_definition':'PCA eigenvector loading multiplied by sqrt(eigenvalue); correlation with unit-variance PC score',
                          'ward_distance':'Euclidean on unscaled PCA return-factor correlations','ward_clusters':a.n_clusters,
                          'pairs_per_cluster':a.pairs_per_cluster,'candidate_pair_count':len(pair_rows),
                          'cointegration':'Engle-Granger log adjusted prices, constant trend, AIC lag; both directions tested',
                          'pair_p_value':'Bonferroni-adjusted min of two directional p-values; BH q-values over screened pairs',
                          'mean_reversion':'AR(1) on Engle-Granger residual; half-life in exchange sessions. Ordinary ADF residual p-value is descriptive only because estimated residuals need Engle-Granger critical values.',
                          'fundamentals':'not included; add only in a separate modeling version with training-only scaling'},
            'data_dimensions':{'eligible_stocks':len(ids),'complete_return_observations':len(R),
                               'pca_factors':k,'ward_cluster_count':int(cluster_df.ward_cluster.nunique()),
                               'candidate_pairs':len(pairs),'exploratory_pair_passes':int(pairs.get('exploratory_candidate_pass',pd.Series(dtype=bool)).sum())},
            'limitations':['End-2023 universe selection biases the 2021-2023 formation sample.',
                           'All PCA, clustering and pair screens use the formation period; selected-pair p-values are exploratory after data-driven selection.',
                           'Ordinary ADF p-values on estimated regression residuals are descriptive only; Engle-Granger test p-values are used for cointegration inference.',
                           '2024-2025 results must be evaluated on a frozen candidate list and cannot undo earlier universe selection bias.',
                           'Clustering parameters and 80% PCA threshold are initial choices; run sensitivity checks before drawing conclusions.',
                           'No execution, transaction costs, borrow availability, hedge rebalancing or profitability is evaluated.'],
            'packages':{p:importlib.metadata.version(p) for p in ['numpy','pandas','scikit-learn','scipy','statsmodels','pyarrow']}}
        (stage/'model_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        if out.exists():
            backup=out.with_name(out.name+'.backup_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f'))
            out.rename(backup)
        try: stage.rename(out)
        except Exception:
            if backup: backup.rename(out)
            raise
    finally:
        if stage.exists(): shutil.rmtree(stage)
    print(f'Eligible securities: {len(ids)}')
    print(f'Complete formation observations: {len(R)}; excluded incomplete dates: {len(dropped_dates)}')
    print(f'PCA factors retained: {k}; variance explained: {cumulative[k-1]:.1%}')
    print(f'Ward clusters: {cluster_df.ward_cluster.nunique()}; screened pairs: {len(pairs)}')
    if len(pairs): print(f'Pairs passing exploratory FDR + AR(1) screen: {int(pairs.exploratory_candidate_pass.sum())}')
    print(f'Results: {out}')
    return out


def main():
    try: run(parse_args())
    except ImportError as e:
        print(f'Missing dependency: {e}. Install: %pip install numpy pandas pyarrow scikit-learn scipy statsmodels',file=sys.stderr);return 1
    except (ValueError,OSError,KeyError) as e:
        print(f'ERROR: {e}',file=sys.stderr);return 1
    return 0

if __name__=='__main__': raise SystemExit(main())
