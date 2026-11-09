import numpy as np
import pandas as pd

def zscores(prices,y,x,alpha,beta,window):
    spread=np.log(prices[y].where(prices[y]>0))-alpha-beta*np.log(prices[x].where(prices[x]>0))
    # All inputs at t are observable at close t; execution must be t+1.
    mean=spread.rolling(window,min_periods=window).mean()
    sd=spread.rolling(window,min_periods=window).std()
    return spread,(spread-mean)/sd.where(sd>0)

def weights(direction,beta):
    # Log hedge beta is an elasticity. Dollar weights, never beta shares.
    return np.array([direction,-direction*beta],float)/(1+abs(beta))
