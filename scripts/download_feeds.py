#!/usr/bin/env python3
"""Download real GTFS resources discovered through the official French catalogue."""
import argparse,datetime,hashlib,json,pathlib,urllib.request,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
SLUGS={'evolity':'evolity-horaires-theoriques-de-transport-public','optymo':'arrets-circuits-et-horaires-du-reseau-optymo-de-belfort','sncf':'horaires-sncf'}
def request(url):return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'PointCommun-university-project/0.1'}),timeout=90)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--only',nargs='+',choices=list(SLUGS),default=list(SLUGS));p.add_argument('--refresh',action='store_true');a=p.parse_args()
 base=ROOT/'data';(base/'raw').mkdir(parents=True,exist_ok=True);manifest=base/'feed_sources.json'
 feeds=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() and not a.refresh else []
 if not feeds:
  with request('https://transport.data.gouv.fr/api/datasets') as r:catalogue=json.load(r)
  for ns,slug in SLUGS.items():
   ds=next(x for x in catalogue if x.get('slug')==slug);resource=next(x for x in ds['resources'] if x.get('format','').upper()=='GTFS')
   feeds.append({'namespace':ns,'dataset_url':ds.get('page_url','https://transport.data.gouv.fr/datasets/'+slug+'/'),'resource_url':resource['original_url'],'stable_resource_url':resource.get('url'),'licence':ds.get('licence'),'resource_updated':resource.get('updated'),'catalogue_metadata':resource.get('metadata',{}),'local_file':'data/raw/'+ns+'.zip'})
  manifest.write_text(json.dumps(feeds,ensure_ascii=False,indent=2),encoding='utf-8')
 failed=False
 for f in feeds:
  if f['namespace'] not in a.only:continue
  path=ROOT/f['local_file'];tmp=path.with_suffix('.download')
  try:
   print('Downloading '+f['namespace'],flush=True)
   with request(f['resource_url']) as r,tmp.open('wb') as out:
    while chunk:=r.read(1024*1024):out.write(chunk)
   with zipfile.ZipFile(tmp) as z:
    names={pathlib.PurePosixPath(n).name:n for n in z.namelist()}
    for name in ['agency.txt','stops.txt','routes.txt','trips.txt','stop_times.txt']:
     if name not in names:raise ValueError('Missing '+name)
    if not {'calendar.txt','calendar_dates.txt'}&names.keys():raise ValueError('Missing calendar')
    rows={}
    for name in names:
     if name.endswith('.txt'):
      with z.open(names[name]) as stream:rows[name]=max(0,sum(1 for _ in stream)-1)
   tmp.replace(path)
   with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
   f.update(status='downloaded',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),bytes=path.stat().st_size,sha256=digest,inspection={'row_counts':rows})
   print(f['namespace']+': '+str(f['bytes'])+' bytes',flush=True)
  except Exception as e:
   f.update(status='failed',error=str(e));failed=True;print(str(e),flush=True)
   tmp.unlink(missing_ok=True)
  manifest.write_text(json.dumps(feeds,ensure_ascii=False,indent=2),encoding='utf-8')
 return int(failed)
if __name__=='__main__':raise SystemExit(main())
