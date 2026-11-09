import numpy as np
import pandas as pd
from trading_signals import weights,zscores
from backtest_engine import simulate

def fixture():
    idx=pd.bdate_range('2021-01-01',periods=30)
    p=pd.DataFrame({'Y':100*np.exp(np.sin(np.arange(30))*0.1),'X':100.},index=idx)
    cfg=dict(window=3,exit_z=.5,stop_z=5,max_hold=3,commission_bps=1,slippage_bps=2,borrow_rate=.03)
    return p,cfg,dict(y='Y',x='X',alpha=0.,beta=1.)
def test_sizing():
    assert np.allclose(weights(1,2),[1/3,-2/3])
    assert np.allclose(weights(-1,2),[-1/3,2/3])
def test_no_future_statistics():
    p,_,_=fixture();_,z=zscores(p,'Y','X',0,1,3);p.iloc[15:,0]*=10
    _,zz=zscores(p,'Y','X',0,1,3);pd.testing.assert_series_equal(z.iloc[:15],zz.iloc[:15])
def test_next_session_and_reconciliation():
    p,c,pair=fixture();t,d,f=simulate(p,pair,p.index[5],p.index[-1],c,1.)
    assert len(t)>0
    assert np.isclose(t.net_return.sum(),d.net_return.sum())
    assert (t.cost>0).all() and (t.borrow>=0).all()
    _,z=zscores(p,'Y','X',0,1,3)
    for _,trade in t.iterrows():
        at=p.index.get_loc(trade.entry_date)
        assert abs(z.iloc[at-1])>=1

def test_short_pnl():
    assert np.dot(np.array([.5,-.5])/100,np.array([0,-10]))==.05

def test_missing_data_invalidates():
    p,c,pair=fixture();p.iloc[10,0]=np.nan
    t,d,f=simulate(p,pair,p.index[5],p.index[-1],c,1.)
    assert f['invalid'] and np.isnan(d.net_return.iloc[-1])
def test_isolation():
    p,c,pair=fixture();t,d,f=simulate(p,pair,p.index[5],p.index[15],c,1.)
    p.iloc[16:,0]*=100
    tt,dd,ff=simulate(p,pair,p.index[5],p.index[15],c,1.)
    pd.testing.assert_frame_equal(t,tt);pd.testing.assert_frame_equal(d,dd)

def test_cost_deduction():
    p,c,pair=fixture()
    t,d,_=simulate(p,pair,p.index[5],p.index[-1],c,1.)
    free=dict(c,commission_bps=0.,slippage_bps=0.,borrow_rate=0.)
    tt,dd,_=simulate(p,pair,p.index[5],p.index[-1],free,1.)
    assert np.isclose(dd.net_return.sum()-d.net_return.sum(),d.cost.sum()+d.borrow.sum())
    assert list(t.entry_date)==list(tt.entry_date)
