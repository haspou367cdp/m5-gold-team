"""Cost-aware hyperopt loss: daily Sharpe of net $ per 1U (gross - $0.425), with a hard minimum trade count."""
import numpy as np
import pandas as pd
from freqtrade.optimize.hyperopt import IHyperOptLoss

COST = 0.425
MIN_TRADES = 30


def net_usd(results):
    sgn = np.where(results['is_short'], -1.0, 1.0)
    return (results['close_rate'] - results['open_rate']) * sgn - COST


class XauNetLoss(IHyperOptLoss):
    @staticmethod
    def hyperopt_loss_function(results: pd.DataFrame, trade_count: int, *args, **kwargs) -> float:
        if trade_count < MIN_TRADES:
            return 100.0 + (MIN_TRADES - trade_count)
        net = net_usd(results)
        day = pd.to_datetime(results['close_date']).dt.date
        daily = pd.Series(net.values).groupby(day.values).sum()
        sd = daily.std()
        if not sd or np.isnan(sd):
            return 50.0
        sharpe = daily.mean() / sd * np.sqrt(len(daily))
        gp = net[net > 0].sum(); gl = -net[net < 0].sum()
        pf = gp / gl if gl > 0 else 5
        return -(sharpe + 0.5 * min(pf, 3))
