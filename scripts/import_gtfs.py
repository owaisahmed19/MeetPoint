#!/usr/bin/env python3
"""Import complete GTFS trips touching the Belfort–Montbéliard study region."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.gtfs import import_feed
p=argparse.ArgumentParser(description=__doc__);p.add_argument('zip_path');p.add_argument('--namespace',required=True);p.add_argument('--output',default=str(Path(__file__).resolve().parents[1]/'data/processed'));p.add_argument('--bbox',nargs=4,type=float,default=[6.5,47.3,7.2,47.85]);p.add_argument('--all',action='store_true');a=p.parse_args();print(import_feed(a.zip_path,a.output,a.namespace,None if a.all else a.bbox))
