"""Run isolated development, validation, refit and frozen test stages."""
import argparse,json,hashlib,sys
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from discovery_v1 import parse_args as discovery_args,run as discover
from pair_features import fit_pairs
from pair_ranker import rank
from backtest_engine import simulate,performance

def discovery(prices,universe,start,end,cfg,out):
    hist=prices.loc[start:end].copy()
    ret=hist/hist.shift()-1
    good=hist.notna().mean().ge(cfg['min_coverage']) & ret.notna().sum().ge(cfg['min_returns']) & hist.iloc[0].notna() & hist.iloc[-1].notna()
    ids=good[good].index
    u=universe[universe.universe_security_id.isin(ids)].copy();u['formation_eligible']=True
    out.mkdir(parents=True,exist_ok=False)
    hist[u.universe_security_id].to_parquet(out/'prices.parquet')
    ret[u.universe_security_id].to_parquet(out/'returns.parquet');u.to_csv(out/'eligible.csv',index=False)
    args=discovery_args(['--returns',str(out/'returns.parquet'),'--prices',str(out/'prices.parquet'),
                         '--eligible',str(out/'eligible.csv'),'--output-dir',str(out/'discovery'),
                         '--expected-count',str(len(u)),'--n-clusters',str(cfg['clusters']),
                         '--pairs-per-cluster',str(cfg['pairs_per_cluster']),
                         '--min-cointegration-observations',str(cfg['min_returns']),
                         '--parallel-replicates',str(cfg['parallel_replicates'])])
    discover(args)
    f=fit_pairs(pd.read_csv(out/'discovery/candidate_pairs_and_tests.csv'),hist,cfg['min_returns'])
    return f

def evaluate(features,prices,start,end,strategy,threshold):
    stats=[];trades=[];days={}
    for _,pair in features.iterrows():
        if pair.get('error','') or not np.isfinite(pair.get('beta',np.nan)) or pair.beta<=0:continue
        tr,d,flag=simulate(prices,pair,start,end,strategy,threshold)
        stats.append(dict(pair_id=pair.pair_id,**performance(tr,d,flag)))
        if len(tr):tr['pair_id']=pair.pair_id;trades.append(tr)
        days[pair.pair_id]=d
    return pd.DataFrame(stats),pd.concat(trades,ignore_index=True) if trades else pd.DataFrame(),days

def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,default=str),encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=Path(__file__).with_name('config.yaml'))
    p.add_argument('--development-start');p.add_argument('--output',type=Path)
    p.add_argument('--events',type=Path,help='Optional explicit restrictions CSV: universe_security_id,known_on,effective_from,effective_to')
    a=p.parse_args();base=a.config.resolve().parent;c=yaml.safe_load(a.config.read_text());period=c['periods']
    if a.development_start:period['development_start']=a.development_start
    ds,de,vs,ve,ts,te=[pd.Timestamp(period[k]) for k in ['development_start','development_end','validation_start','validation_end','test_start','test_end']]
    if not ds<de<vs<=ve<ts<te:raise ValueError('Period boundaries overlap or are unordered')
    out=(a.output or base/c['paths']['output']).resolve()
    if out.exists():raise ValueError('Output exists: choose a new --output for each experiment')
    price_path=(base/c['paths']['adjusted_prices']).resolve();universe_path=(base/c['paths']['universe']).resolve()
    prices=pd.read_parquet(price_path);u=pd.read_csv(universe_path,dtype=str,keep_default_na=False)
    if not prices.index.is_unique or not prices.columns.is_unique or u.universe_security_id.duplicated().any():raise ValueError('Duplicate date or security IDs')
    prices=prices.sort_index().reindex(columns=u.universe_security_id)
    prices=prices.where(np.isfinite(prices)&prices.gt(0))
    import pandas_market_calendars as mcal
    sessions=mcal.get_calendar('NYSE').schedule(start_date=ds,end_date=te).index
    prices=prices.reindex(sessions);prices.index.name='date'
    restrictions=[]
    if a.events:
        ev=pd.read_csv(a.events)
        for _,e in ev.iterrows():
            first=max(pd.Timestamp(e.known_on),pd.Timestamp(e.effective_from));last=pd.Timestamp(e.effective_to)
            prices.loc[first:last,e.universe_security_id]=np.nan;restrictions.append(e.to_dict())
    out.mkdir(parents=True)
    f=discovery(prices,u,ds,de,c['discovery'],out/'development')
    f.to_csv(out/'pair_features.csv',index=False)
    all_perf=[];all_trades=[];rankings={};objective={}
    for threshold in c['strategy']['entry_thresholds']:
        perf,tr,_=evaluate(f,prices,vs,ve,c['strategy'],threshold)
        if perf.empty:continue
        ranked=rank(f,perf,c['ranking_weights']);rankings[threshold]=ranked
        perf['entry_threshold']=threshold;all_perf.append(perf)
        if len(tr):tr['entry_threshold']=threshold;all_trades.append(tr)
        chosen=ranked[ranked.label.ne('rejected_data_or_economics')].head(c['strategy']['top_pairs'])
        objective[threshold]=float(chosen.net_return.mean()) if len(chosen) else -np.inf
    if not objective:raise ValueError('No evaluable validation pairs')
    threshold=max(sorted(objective),key=lambda k:objective[k])
    ranked=rankings[threshold];ranked.to_csv(out/'ranked_pairs.csv',index=False)
    pd.concat(all_perf).to_csv(out/'validation_performance.csv',index=False)
    (pd.concat(all_trades,ignore_index=True) if all_trades else pd.DataFrame()).to_csv(out/'validation_trades.csv',index=False)
    # Refit discovery using development start through 2023. Only previously
    # validated pairs can receive the validation-based ranking.
    final=discovery(prices,u,ds,ve,c['discovery'],out/'refit')
    final.to_csv(out/'refit_pair_features.csv',index=False)
    validated=ranked[ranked.label.ne('rejected_data_or_economics')][['pair_id','overall_score']]
    final=final.merge(validated,on='pair_id',how='inner').sort_values('overall_score',ascending=False)
    selected=[];results=[];trade_list=[];curves=[]
    # Everything above is frozen before the test slice is read by evaluate.
    write_json(out/'selected_strategy.json',dict(entry_threshold=threshold,config=c,selection_objective='validation mean net P&L of selected pairs',test_used_for_selection=False))
    for mode in ['strict','exploratory']:
        pick=final[final.q_value.le(.05)] if mode=='strict' else final
        pick=pick.head(c['strategy']['top_pairs']).copy();pick['strategy']=mode
        selected.append(pick)
        perf,tr,days=evaluate(pick,prices,ts,te,c['strategy'],threshold)
        if len(perf):perf['strategy']=mode;results.append(perf)
        if len(tr):tr['strategy']=mode;trade_list.append(tr)
        idx=prices.loc[ts:te].index
        if len(pick):
            panel=pd.DataFrame({k:d.net_return.reindex(idx) for k,d in days.items()},index=idx)
            # Fixed equal capital sleeves; no reallocation after missing valuation.
            portfolio=panel.sum(axis=1,min_count=len(pick))/len(pick)
            if portfolio.isna().any():portfolio.loc[portfolio.isna().idxmax():]=np.nan
        else:portfolio=pd.Series(0.,index=idx)
        curve=pd.DataFrame(dict(date=idx,strategy=mode,net_return=portfolio.to_numpy()))
        curve['equity_fixed_capital']=1+curve.net_return.cumsum(skipna=False)
        curve['drawdown']=curve.equity_fixed_capital-curve.equity_fixed_capital.cummax()
        curves.append(curve)
    pd.concat(selected).to_csv(out/'selected_pairs.csv',index=False)
    (pd.concat(results) if results else pd.DataFrame()).to_csv(out/'out_of_sample_performance.csv',index=False)
    (pd.concat(trade_list) if trade_list else pd.DataFrame()).to_csv(out/'out_of_sample_trades.csv',index=False)
    curve=pd.concat(curves);curve.to_csv(out/'portfolio_equity_curve.csv',index=False)
    charts=out/'charts';charts.mkdir()
    for mode,g in curve.groupby('strategy'):
        fig,ax=plt.subplots(2,1,figsize=(10,6),sharex=True)
        ax[0].plot(g.date,g.equity_fixed_capital);ax[0].set_title(f'{mode}: 2024–2025 conditional out-of-sample simulation')
        ax[1].plot(g.date,g.drawdown);fig.tight_layout();fig.savefig(charts/f'{mode}_equity_drawdown.png');plt.close(fig)
    fig,ax=plt.subplots();ax.hist(ranked.overall_score,bins=20);ax.set_title('Development/validation ranking scores');fig.savefig(charts/'ranking_scores.png');plt.close(fig)
    from diagnostics import plot_pairs
    plot_pairs(final.head(c['strategy']['top_pairs']),prices,ts,te,c['strategy'],threshold,charts)
    sensitivity=[]
    for slip in [0.,5.,10.,20.]:
        scenario=dict(c['strategy'],slippage_bps=slip)
        perf,_,_=evaluate(final.head(c['strategy']['top_pairs']),prices,ts,te,scenario,threshold)
        sensitivity.append(dict(slippage_bps=slip,mean_net_return=perf.net_return.mean() if len(perf) and not perf.invalid.any() else np.nan))
    pd.DataFrame(sensitivity).to_csv(out/'cost_sensitivity.csv',index=False)
    for xcol in ['half_life_sessions','q_value']:
        fig,ax=plt.subplots();ax.scatter(ranked[xcol],ranked.net_return,s=8);ax.set_xlabel(xcol);ax.set_ylabel('Validation net return');fig.savefig(charts/(xcol+'_validation.png'));plt.close(fig)
    counts={m:sum(len(s) for s in selected if len(s) and s.strategy.iloc[0]==m) for m in ['strict','exploratory']}
    limitations=['End-2023 membership creates earlier selection bias.','Adjusted prices are retrospectively revised total-return proxies; next-close execution uses adjusted close units, not actual share fills.',
                 'Costs and borrow are configurable scenarios, not observed quotes or availability.','No volume or borrow availability supplied; execution feasibility unverified.',
                 'Current V1 had zero FDR-qualified pairs; V2 recomputes FDR separately and does not force that count.',
                 'Incomplete live prices invalidate the portfolio from first missing valuation; no stale/zero valuation.',
                 'Ranking includes only validated pairs rediscovered during refit. Others are logged through the refit features.',
                 'Historical identity is inherited from prepared data; unresolved corporate actions require explicit event restrictions.']
    write_json(out/'model_v2_manifest.json',dict(config=c,selected_counts=counts,restrictions=restrictions,limitations=limitations,
        inputs={str(q):hashlib.sha256(q.read_bytes()).hexdigest() for q in [price_path,universe_path]},v1_preserved=True))
    (out/'model_v2_research_report.md').write_text('# Model V2\n\nDevelopment start: '+str(ds.date())+'\n\nSelected pairs: '+str(counts)+'\n\n'+'\n\n'.join(limitations))
    print('Completed:',out,'selected pairs:',counts)
if __name__=='__main__':main()
