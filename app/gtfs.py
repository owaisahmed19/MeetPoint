"""Validated GTFS import and Europe/Paris dated timetable connections."""
from __future__ import annotations
import csv,io,json,zipfile
from functools import lru_cache
from pathlib import Path
from datetime import date,timedelta


def seconds(value):
    parts=str(value).split(':')
    if len(parts) not in (2,3):raise ValueError('Expected HH:MM or HH:MM:SS')
    h,m=int(parts[0]),int(parts[1]);s=int(parts[2]) if len(parts)==3 else 0
    if h<0 or not 0<=m<60 or not 0<=s<60:raise ValueError('Invalid timetable time')
    return h*3600+m*60+s


def import_feed(zip_path,output_dir,namespace,bbox=None):
    if not namespace or any(x not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for x in namespace):raise ValueError('Invalid namespace')
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        names={Path(n).name:n for n in z.namelist()}
        def rows(name):
            if name not in names:return
            with z.open(names[name]) as raw:
                yield from csv.DictReader(io.TextIOWrapper(raw,encoding='utf-8-sig',newline=''))
        for name in ['stops.txt','routes.txt','trips.txt','stop_times.txt']:
            if name not in names:raise ValueError('Missing '+name)
        if 'frequencies.txt' in names and any(True for _ in rows('frequencies.txt')):raise ValueError('Frequency-based trips require an additional routing implementation')
        stops={}
        for r in rows('stops.txt'):
            try:lat,lon=float(r['stop_lat']),float(r['stop_lon'])
            except (KeyError,ValueError):continue
            stops[r['stop_id']]={'id':r['stop_id'],'name':r.get('stop_name',r['stop_id']),'lat':lat,'lon':lon}
        if bbox:
            w,s,e,n=bbox;area={sid for sid,v in stops.items() if w<=v['lon']<=e and s<=v['lat']<=n}
            selected={r['trip_id'] for r in rows('stop_times.txt') if r.get('stop_id') in area}
        else:selected=None
        times={};bad=0
        for r in rows('stop_times.txt'):
            if selected is not None and r['trip_id'] not in selected:continue
            try:
                if r['stop_id'] not in stops:raise ValueError('Unknown stop')
                a,d=seconds(r['arrival_time']),seconds(r['departure_time'])
                times.setdefault(r['trip_id'],[]).append({'stop_id':r['stop_id'],'arrival':a,'departure':d,'sequence':int(r['stop_sequence']),'pickup':r.get('pickup_type','0')!='1','dropoff':r.get('drop_off_type','0')!='1'})
            except (ValueError,KeyError):bad+=1
        if bad:raise ValueError(f'{bad} selected stop times require interpolation/repair; refusing to join across missing rows')
        trips={r['trip_id']:{'route_id':r['route_id'],'service_id':r['service_id'],'headsign':r.get('trip_headsign',''),'shape_id':r.get('shape_id','')} for r in rows('trips.txt') if r['trip_id'] in times}
        used_stops={r['stop_id'] for tid in trips for r in times[tid]};used_routes={v['route_id'] for v in trips.values()};services={v['service_id'] for v in trips.values()}
        routes={r['route_id']:{'name':r.get('route_short_name') or r.get('route_long_name') or r['route_id'],'type':r.get('route_type','3')} for r in rows('routes.txt') if r['route_id'] in used_routes}
        calendars={r['service_id']:r for r in rows('calendar.txt') if r['service_id'] in services}
        exceptions=[r for r in rows('calendar_dates.txt') if r['service_id'] in services]
        if not calendars and not exceptions:raise ValueError('No usable service calendar')
        if any(r.get('agency_timezone','Europe/Paris')!='Europe/Paris' for r in rows('agency.txt')):raise ValueError('Only Europe/Paris feeds supported')
        shape_ids={r['shape_id'] for r in trips.values() if r['shape_id']};shapes={}
        for r in rows('shapes.txt'):
            if r['shape_id'] not in shape_ids:continue
            try:shapes.setdefault(r['shape_id'],[]).append((int(r['shape_pt_sequence']),float(r['shape_pt_lat']),float(r['shape_pt_lon'])))
            except ValueError:continue
        shapes={sid:[[lat,lon] for _,lat,lon in sorted(v)] for sid,v in shapes.items()}
        for v in times.values():
            v.sort(key=lambda r:r['sequence'])
            if any(r['arrival']>r['departure'] for r in v) or any(a['departure']>b['arrival'] or a['sequence']>=b['sequence'] for a,b in zip(v,v[1:])):raise ValueError('Non-monotonic trip times or stop order')
        transfers=[]
        for r in rows('transfers.txt'):
            if r.get('from_stop_id') not in used_stops or r.get('to_stop_id') not in used_stops:continue
            if any(r.get(k) for k in ['from_route_id','to_route_id','from_trip_id','to_trip_id']) or r.get('transfer_type') in {'4','5'}:raise ValueError('Scoped or in-seat transfer rules unsupported')
            transfers.append(r)
        result={'namespace':namespace,'source_file':Path(zip_path).name,'stops':{k:stops[k] for k in used_stops},'routes':routes,'trips':trips,'stop_times':{k:times[k] for k in trips},'calendar':calendars,'calendar_dates':exceptions,'shapes':shapes,'transfers':transfers,'bbox':bbox}
        (output_dir/(namespace+'.json')).write_text(json.dumps(result,separators=(',',':')),encoding='utf-8')
        manifest_path=output_dir/'manifest.json';manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'feeds':[]}
        entry={'namespace':namespace,'file':namespace+'.json','stops':len(used_stops),'trips':len(trips),'source_file':Path(zip_path).name}
        manifest['feeds']=[x for x in manifest['feeds'] if x['namespace']!=namespace]+[entry]
        manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8');return entry


def service_active(feed,sid,day):
    stamp=day.strftime('%Y%m%d')
    for r in feed.get('calendar_dates',[]):
        if r['service_id']==sid and r['date']==stamp:return r['exception_type']=='1'
    r=feed.get('calendar',{}).get(sid)
    return bool(r and r['start_date']<=stamp<=r['end_date'] and r.get(['monday','tuesday','wednesday','thursday','friday','saturday','sunday'][day.weekday()])=='1')


def _load_network(data_dir,day):
    root=Path(data_dir)/'processed';manifest=root/'manifest.json';stops={};connections=[];transfers=[];status=[];warnings=[]
    entries=json.loads(manifest.read_text(encoding='utf-8')).get('feeds',[]) if manifest.exists() else []
    for e in entries:
        feed=json.loads((root/e['file']).read_text(encoding='utf-8'));ns=feed['namespace'];prefix=ns+':'
        for sid,s in feed['stops'].items():stops[prefix+sid]=s
        active_count=0
        for offset in [-1,0]:
            service_day=day+timedelta(days=offset)
            active={sid:service_active(feed,sid,service_day) for sid in {t['service_id'] for t in feed['trips'].values()}}
            for tid,tr in feed['trips'].items():
                if not active[tr['service_id']]:continue
                ts=feed['stop_times'][tid];route=feed['routes'].get(tr['route_id'],{'name':tr['route_id'],'type':'3'})
                if offset==0:active_count+=1
                shape=feed.get('shapes',{}).get(tr.get('shape_id',''),[])
                for a,b in zip(ts,ts[1:]):
                    dep=a['departure']+offset*86400;arr=b['arrival']+offset*86400
                    if arr<0 or dep>172800:continue
                    rt=int(route.get('type') or 3)
                    if rt in {0,1,2} or 100<=rt<200 or 400<=rt<500 or 900<=rt<1000:mode='train'
                    elif rt==3 or 200<=rt<300 or 700<=rt<800:mode='bus'
                    else:
                        warning=f'{ns}: unsupported GTFS route type {rt}; journey excluded.'
                        if warning not in warnings:warnings.append(warning)
                        continue
                    connections.append({'from':prefix+a['stop_id'],'to':prefix+b['stop_id'],'dep':dep,'arr':arr,'trip_id':prefix+tid+':'+service_day.isoformat(),'route_name':route['name'],'mode':mode,'headsign':tr.get('headsign',''),'pickup':a.get('pickup',True),'dropoff':b.get('dropoff',True),'shape':shape})
        for r in feed.get('transfers',[]):transfers.append({**r,'from_stop_id':prefix+r['from_stop_id'],'to_stop_id':prefix+r['to_stop_id']})
        status.append({'namespace':ns,'stops':len(feed['stops']),'active_trips':active_count})
        if not active_count:warnings.append(ns+': no service on this date or date outside imported coverage.')
    connections.sort(key=lambda c:(c['dep'],c['arr']))
    if not entries:warnings.append('No validated GTFS imported; transit unavailable.')
    warnings.append('Walking times and geometry are straight-line approximations, not verified pedestrian routes. Indoor navigation is not implemented.')
    return stops,connections,transfers,{'transit_available':bool(connections),'feeds':status,'warnings':warnings}


@lru_cache(maxsize=6)
def _cached_network(root,day,versions):
    return _load_network(root,day)


def load_network(data_dir,day):
    root=Path(data_dir).resolve()
    versions=tuple((p.name,p.stat().st_mtime_ns,p.stat().st_size) for p in sorted((root/'processed').glob('*.json')) if p.name!='foot_routes.json')
    return _cached_network(str(root),day,versions)
