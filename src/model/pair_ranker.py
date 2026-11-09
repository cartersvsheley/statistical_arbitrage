import numpy as np
import pandas as pd

def rank(features,validation,weights):
    out=features.merge(validation,on='pair_id',how='left',validate='one_to_one')
    # Ranks fitted only to this development/validation candidate population.
    def pct(col,positive=True):
        return out[col].rank(pct=True,ascending=positive).fillna(0.)
    out['score_statistical']=pct('q_value',False)
    out['score_stability']=(pct('hedge_ratio_instability',False)+pct('rolling_stationarity_fraction'))/2
    out['score_reversion']=pct('reversion_fraction')
    out['score_economic']=pct('net_return')
    out['score_validation']=pct('sharpe')
    # Missing liquidity is not an observed neutral or high score.
    out['score_execution']=np.nan
    active={k:v for k,v in weights.items() if k!='execution'}
    denom=sum(active.values())
    out['overall_score']=sum(out['score_'+k]*v for k,v in active.items())/denom
    out['label']=np.where(out.q_value.le(.05),'FDR_qualified_in_sample','exploratory')
    rejected=out['invalid'].fillna(True).astype(bool)|out.trades.fillna(0).lt(2)|out.net_return.fillna(-np.inf).le(0)|out.beta.le(0)
    out.loc[rejected,'label']='rejected_data_or_economics'
    return out.sort_values(['overall_score','pair_id'],ascending=[False,True])
