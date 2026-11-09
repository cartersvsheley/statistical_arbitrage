import numpy as np
import pandas as pd
from discovery_v1 import test_pair,bh_qvalues

def fit_pairs(candidates,prices,minimum=252):
    rows=[]
    for _,p in candidates.iterrows():
        y=p.universe_security_id_y;x=p.universe_security_id_x
        try:
            r=test_pair(y,x,prices,{},p.ward_cluster,p.exposure_distance,minimum)
            if r['orientation']=='x_on_y': y,x=x,y
            a=prices[[y,x]].dropna();ly=np.log(a[y]);lx=np.log(a[x])
            alpha,beta=np.linalg.lstsq(np.c_[np.ones(len(a)),lx],ly,rcond=None)[0]
            resid=ly-alpha-beta*lx
            rolling=[];stationary=[]
            from statsmodels.tsa.stattools import coint
            for stop in range(126,len(a)+1,63):
                xx=lx.iloc[stop-126:stop];yy=ly.iloc[stop-126:stop]
                aa,bb=np.linalg.lstsq(np.c_[np.ones(len(xx)),xx],yy,rcond=None)[0]
                rolling.append(bb);stationary.append(coint(yy,xx,trend='c',autolag='aic')[1]<.05)
            r.update(pair_id='__'.join(sorted([y,x])),y=y,x=x,alpha=alpha,beta=beta,
                     residual_volatility=resid.std(),hedge_ratio_instability=float(np.std(rolling)/max(abs(beta),.01)) if rolling else np.nan,
                     rolling_stationarity_fraction=float(np.mean(stationary)) if stationary else np.nan,
                     liquidity_observed=False,borrow_observed=False,benchmark_correlation=np.nan,
                     error=r.get('error',''))
            rows.append(r)
        except (ValueError,np.linalg.LinAlgError) as e:
            rows.append(dict(pair_id='__'.join(sorted([y,x])),y=y,x=x,error=str(e)))
    out=pd.DataFrame(rows)
    if len(out):out['q_value']=bh_qvalues(out.coint_pair_p_bonferroni)
    return out
