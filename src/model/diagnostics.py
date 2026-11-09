import numpy as np
import matplotlib.pyplot as plt
from trading_signals import zscores

def plot_pairs(selected,prices,start,end,cfg,threshold,out):
    for _,p in selected.head(3).iterrows():
        h=prices.loc[:end,[p.y,p.x]];s,z=zscores(h,p.y,p.x,p.alpha,p.beta,cfg['window'])
        a=h.loc[start:end];fig,ax=plt.subplots(3,2,figsize=(12,10))
        np.log(a).plot(ax=ax[0,0],legend=False);ax[0,0].set_title('Adjusted log prices')
        ax[0,1].scatter(np.log(a[p.x]),np.log(a[p.y]),s=3);ax[0,1].set_title('Log-price relationship')
        s.loc[start:end].plot(ax=ax[1,0]);ax[1,0].set_title('Frozen-hedge spread')
        z.loc[start:end].plot(ax=ax[1,1]);ax[1,1].axhline(threshold,color='red');ax[1,1].axhline(-threshold,color='red')
        from backtest_engine import simulate
        tr,d,_=simulate(prices,p,start,end,cfg,threshold)
        d.net_return.cumsum(skipna=False).plot(ax=ax[2,0]);ax[2,0].set_title('Net fixed-capital P&L')
        if len(tr):
            ax[2,1].hist(tr.held,bins=10);ax[2,1].axvline(p.half_life_sessions,color='red',label='AR half-life');ax[2,1].legend()
            for dt in tr.entry_date:ax[1,1].axvline(dt,color='green',alpha=.2)
            for dt in tr.exit_date:ax[1,1].axvline(dt,color='orange',alpha=.2)
        ax[2,1].set_title('Realized holding sessions')
        fig.suptitle(f'{p.pair_id}\nOut-of-sample {start.date()}–{end.date()}');fig.tight_layout();fig.savefig(out/(p.pair_id+'.png'));plt.close(fig)
