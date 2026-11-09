import numpy as np
import pandas as pd
from trading_signals import zscores,weights

def simulate(prices,pair,start,end,cfg,entry=2.):
    y,x=pair['y'],pair['x']; beta=float(pair['beta']);alpha=float(pair['alpha'])
    history=prices.loc[:end,[y,x]]
    spread,z=zscores(history,y,x,alpha,beta,cfg['window'])
    dates=history.loc[start:end].index
    ledger=[];trades=[];position=None;pending=None;invalid=False;signals=0
    cost=(cfg['commission_bps']+cfg['slippage_bps'])/10000
    for dt in dates:
        px=history.loc[dt].to_numpy(float); pnl=fees=borrow=0.;reason='';turnover=0.
        valid=np.isfinite(px).all() and (px>0).all()
        if not valid:
            invalid=True
            ledger.append(dict(date=dt,gross_pnl=np.nan,cost=np.nan,borrow=np.nan,net_return=np.nan,invalid=True))
            # Never value a live missing security at zero or carry stale prices.
            break
        if position is not None:
            pnl=float(np.dot(position['units'],px-position['last']))
            elapsed=(dt-position['last_date']).days
            borrow=float(np.sum(np.maximum(-position['units']*position['last'],0)))*cfg['borrow_rate']*elapsed/365
            position['gross']+=pnl;position['borrow']+=borrow;position['held']+=1
            position['last']=px.copy();position['last_date']=dt
            position['mae']=min(position['mae'],position['gross'])
        if pending is not None:
            action,pending_reason=pending;pending=None
            if action=='exit' and position is not None:
                turnover=float(np.abs(position['units']*px).sum());fees=turnover*cost
                trade={k:position[k] for k in ['entry_date','direction','held','gross','borrow','mae']}
                trade.update(exit_date=dt,exit_reason=pending_reason,cost=position['entry_cost']+fees,
                             net_return=position['gross']-position['borrow']-position['entry_cost']-fees)
                trades.append(trade);position=None
            elif action in (-1,1) and position is None:
                w=weights(action,beta);turnover=float(np.abs(w).sum());fees=turnover*cost
                position=dict(units=w/px,last=px.copy(),last_date=dt,entry_date=dt,direction=action,
                              entry_cost=fees,held=0,gross=0.,borrow=0.,mae=0.)
        zz=z.get(dt,np.nan)
        if position is not None and np.isfinite(zz):
            if abs(zz)<=cfg['exit_z']: reason='reversion'
            elif abs(zz)>=cfg['stop_z']:reason='stop'
            elif position['held']>=cfg['max_hold']:reason='timeout'
            if reason:pending=('exit',reason)
        elif position is None and np.isfinite(zz):
            loc=history.index.get_loc(dt)
            previous=z.iloc[loc-1] if loc else np.nan
            if np.isfinite(previous):
                if zz<=-entry and previous>-entry:pending=(1,'entry');signals+=1
                elif zz>=entry and previous<entry:pending=(-1,'entry');signals+=1
        ledger.append(dict(date=dt,gross_pnl=pnl,cost=fees,borrow=borrow,net_return=pnl-fees-borrow,invalid=False))
    # Preannounced end-of-period close liquidation, not a same-close signal fill.
    if position is not None and not invalid and len(ledger):
        fees=float(np.abs(position['units']*position['last']).sum())*cost
        ledger[-1]['cost']+=fees;ledger[-1]['net_return']-=fees
        trades.append(dict(entry_date=position['entry_date'],exit_date=dates[-1],direction=position['direction'],
                           held=position['held'],gross=position['gross'],borrow=position['borrow'],
                           cost=position['entry_cost']+fees,net_return=position['gross']-position['borrow']-position['entry_cost']-fees,
                           mae=position['mae'],exit_reason='scheduled_end'))
    tr=pd.DataFrame(trades);daily=pd.DataFrame(ledger)
    if not daily.empty:daily=daily.set_index('date')
    return tr,daily,dict(invalid=invalid,unresolved_live_position=invalid and position is not None,entry_signals=signals)

def performance(trades,daily,flags):
    r=daily.net_return if len(daily) else pd.Series(dtype=float)
    valid=not flags['invalid']
    curve=r.cumsum();dd=curve-curve.cummax().clip(lower=0)
    wins=trades.net_return if len(trades) else pd.Series(dtype=float)
    loss=-wins[wins<0].sum()
    return dict(net_return=float(r.sum()) if valid else np.nan,
                gross_return=float(daily.gross_pnl.sum()) if len(daily) and valid else np.nan,
                costs=float(daily.cost.sum()) if len(daily) and valid else np.nan,
                sharpe=float(r.mean()/r.std()*np.sqrt(252)) if len(r)>1 and r.std()>0 and valid else np.nan,
                max_drawdown=float(dd.min()) if len(dd) and valid else np.nan,
                trades=len(trades),win_rate=float((wins>0).mean()) if len(wins) else np.nan,
                profit_factor=float(wins[wins>0].sum()/loss) if loss>0 else np.nan,
                average_holding=float(trades.held.mean()) if len(trades) else np.nan,
                median_holding=float(trades.held.median()) if len(trades) else np.nan,
                reversion_fraction=float(trades.exit_reason.eq('reversion').mean()) if len(trades) else np.nan,
                stop_fraction=float(trades.exit_reason.eq('stop').mean()) if len(trades) else np.nan,
                **flags)
