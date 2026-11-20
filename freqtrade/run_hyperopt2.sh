#!/bin/bash
# usage: run_hyperopt.sh STRATEGY EPOCHS   (in-sample window only: win_is.json)
cd "$(dirname "$0")"
/workspace/ftvenv/bin/freqtrade hyperopt -c config.json --userdir user_data2 -c win_is.json -s "$1" --timerange 20260715-20261022 \
  --timeframe-detail 1m --hyperopt-loss XauNetLoss --hyperopt-path user_data/hyperopts \
  --spaces buy sell protection --enable-protections -e 200 -j 1 --random-state 42 --min-trades 30 \
  --disable-param-export --print-json --no-color > "logs/hyperopt_$1.log" 2>&1
echo "DONE $1 $?" >> logs/progress.txt
