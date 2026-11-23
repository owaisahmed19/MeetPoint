#!/usr/bin/env python3
"""Download official active SNCF RFN line geometry intersecting the study area."""
import argparse,json,urllib.request,urllib.parse,hashlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bbox',type=float,nargs=4,default=[6.5,47.3,7.2,47.85],metavar=('WEST','SOUTH','EAST','NORTH'))
    p.add_argument('--output',default=str(ROOT/'data/rail_geometry.json'))
    a=p.parse_args();w,s,e,n=a.bbox
    where=f"intersects(geo_shape, geom'POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))') AND mnemo='EXPLOITE'"
    endpoint='https://data.sncf.com/api/explore/v2.1/catalog/datasets/formes-des-lignes-du-rfn/records?'
    records=[];offset=0
    while True:
        u=endpoint+urllib.parse.urlencode({'where':where,'limit':100,'offset':offset})
        req=urllib.request.Request(u,headers={'User-Agent':'PointCommun-course-project/0.1'})
        with urllib.request.urlopen(req,timeout=45) as r:data=json.load(r)
        batch=data.get('results',[]);records+=batch
        if not batch or len(records)>=data.get('total_count',0):break
        offset+=len(batch)
    if not records:raise RuntimeError('Official source returned no active regional rail geometry')
    payload={'source_url':endpoint,'source_page':'https://data.sncf.com/explore/dataset/formes-des-lignes-du-rfn/','licence':'ODbL 1.0','attribution':'SNCF Réseau — Fichier de formes des lignes du Réseau Ferré National','checked_at':datetime.now(timezone.utc).isoformat(),'precision':'decametric, map scale1:50000; corridor, not a certified trip-specific shape','bbox':a.bbox,'records':records}
    target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(len(records),'active corridor records;',target.stat().st_size,'bytes;',hashlib.sha256(target.read_bytes()).hexdigest())
if __name__=='__main__':main()
