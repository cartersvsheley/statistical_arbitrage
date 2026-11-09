"""Portable launcher; run from any directory. Model runs get unique output paths."""
from pathlib import Path
from datetime import datetime
import argparse, subprocess, sys
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser()
p.add_argument('stage', choices=['test','model','download','prepare','universe'])
a,extra=p.parse_known_args()
if a.stage=='test':cmd=['-m','pytest','-q']
elif a.stage=='model':
    cmd=['src/model/run_model_v2.py','--config',str(ROOT/'config/default.yaml')]
    if '--output' not in extra:
        cmd += ['--output',str(ROOT/'results/local'/datetime.now().strftime('%Y%m%d_%H%M%S_%f'))]
elif a.stage=='download':cmd=['scripts/download_prices.py','--universe',str(ROOT/'data/universe/equity_universe_2023.csv'),'--output',str(ROOT/'data/raw')]
elif a.stage=='prepare':cmd=['scripts/prepare_model_data.py','--prices-root',str(ROOT/'data/raw'),'--output',str(ROOT/'data/processed')]
else:cmd=['scripts/build_equity_universe.py','--source-dir',str(ROOT/'data/sources'),'--output-dir',str(ROOT/'data/universe')]
raise SystemExit(subprocess.call([sys.executable,*cmd,*extra],cwd=ROOT))
