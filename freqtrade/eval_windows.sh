#!/bin/bash
# usage: eval_windows.sh "S1 S2 ..."  -> backtests each window with 1m detail; results in user_data/bt_<win>/
cd "$(dirname "$0")"
for w in is oos full m1 m2 m3; do
  mkdir -p user_data/bt_$w
  /workspace/ftvenv/bin/freqtrade backtesting -c config.json -c win_$w.json --strategy-list $1 --timerange 20260715-20261121 \
    --timeframe-detail 1m --enable-protections --export trades --backtest-directory user_data/bt_$w --no-color > logs/bt_$w.log 2>&1
  echo "bt $w $?"
done
