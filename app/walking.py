"""Cached, rate-limited pedestrian geometry from an explicitly foot-profile router.

Only shortlisted itineraries are requested. The public demo endpoint is not used
without the administrator's data/foot_routing.json configuration. Its network
routes do not prove indoor access or real-world opening permissions.
"""
from __future__ import annotations
import hashlib,json,math,os,threading,time,urllib.request
from pathlib import Path

DEFAULT_URL='https://routing.openstreetmap.de/routed-foot/route/v1/driving'
_LOCK=threading.Lock()
_LAST_REQUEST=0.0

def _distance(a,b):
    return 6371000*math.hypot(math.radians(a[0]-b[0]),math.radians(a[1]-b[1])*math.cos(math.radians((a[0]+b[0])/2)))

class FootRouter:
    def __init__(self,data_dir):
        self.data_dir=Path(data_dir)
        path=self.data_dir/'foot_routing.json'
        self.config=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        self.enabled=bool(self.config.get('enabled')) and os.environ.get('POINTCOMMUN_OFFLINE')!='1'
        self.base=str(self.config.get('base_url',DEFAULT_URL)).rstrip('/')
        if self.config.get('profile','foot')!='foot' or '/routed-car/' in self.base or '/routed-bike/' in self.base:
            raise ValueError('Walking configuration must use a pedestrian routing profile')
        self.limit=max(0,min(30,int(self.config.get('max_requests_per_plan',12))))
        self.timeout=max(1,min(20,float(self.config.get('timeout_seconds',5))))
        self.cache_path=self.data_dir/'processed'/'foot_routes.json'
        self.cache={};self.errors=[];self.requests=0
        if self.cache_path.exists():
            try:self.cache=json.loads(self.cache_path.read_text(encoding='utf-8'))
            except (OSError,ValueError):pass
        self.memo={};self.allow_network=True

    def cached_costs(self):
        """Use valid stored foot paths before doing any timetable search."""
        result={}
        if not self.enabled:return result
        for value in self.cache.values():
            geometry=value.get('geometry',[])
            if len(geometry)<2 or value.get('cached_at',0)<time.time()-30*86400:continue
            if value.get('source',self.base)!=self.base:continue
            key=tuple(round(float(x),6) for x in (*geometry[0],*geometry[-1]))
            result[key]=value
        return result

    def route(self,a,b):
        """Return validated OSM lat/lon geometry + actual model distance/duration.

        None means unknown/unavailable, never an invented road geometry. Tiny
        coincident endpoint walks stay the planner's zero/approximate segment.
        """
        if not self.enabled:return None
        a,b=tuple(map(float,a)),tuple(map(float,b))
        if _distance(a,b)<3:return None
        coords=f'{a[1]:.6f},{a[0]:.6f};{b[1]:.6f},{b[0]:.6f}'
        key=hashlib.sha256((self.base+'|'+coords).encode()).hexdigest()
        if key in self.memo:return self.memo[key]
        cached=self.cache.get(key)
        if cached and cached.get('cached_at',0)>time.time()-30*86400:
            self.memo[key]=cached;return cached
        if not self.allow_network:return None
        if self.requests>=self.limit:
            self.memo[key]=None;self.errors.append('Pedestrian lookup limit reached; remaining walks are approximate.');return None
        self.requests+=1
        try:
            global _LAST_REQUEST
            with _LOCK:
                # Shared across HTTP worker threads: never exceed public 1 req/s.
                wait=1.05-(time.monotonic()-_LAST_REQUEST)
                if wait>0:time.sleep(wait)
                _LAST_REQUEST=time.monotonic()
                req=urllib.request.Request(self.base+'/'+coords+'?overview=full&geometries=geojson&steps=false',headers={'User-Agent':'PointCommun-academic-meeting-planner/0.1','Accept':'application/json'})
                with urllib.request.urlopen(req,timeout=self.timeout) as response:payload=json.load(response)
            result=self.validate(payload,a,b)
            result.update({'source':self.base,'attribution':'© OpenStreetMap contributors, ODbL; routing by FOSSGIS OSRM','cached_at':time.time()})
            with _LOCK:
                self.cache_path.parent.mkdir(parents=True,exist_ok=True)
                # Merge concurrent plans instead of dropping another plan's cache.
                disk={}
                if self.cache_path.exists():
                    try:disk=json.loads(self.cache_path.read_text(encoding='utf-8'))
                    except (OSError,ValueError):pass
                disk[key]=result;self.cache=disk
                tmp=self.cache_path.with_suffix('.tmp')
                tmp.write_text(json.dumps(disk,separators=(',',':')),encoding='utf-8');tmp.replace(self.cache_path)
            self.memo[key]=result;return result
        except (OSError,ValueError,TypeError,KeyError,IndexError) as exc:
            self.memo[key]=None;self.errors.append('Pedestrian router unavailable or no trusted foot route: '+str(exc)[:120]);return None

    @staticmethod
    def validate(payload,a,b):
        if payload.get('code')!='Ok' or not payload.get('routes'):raise ValueError('No pedestrian route returned')
        r=payload['routes'][0];coordinates=r['geometry']['coordinates']
        if r['geometry'].get('type')!='LineString' or len(coordinates)<2:raise ValueError('No usable pedestrian geometry')
        geom=[[float(p[1]),float(p[0])] for p in coordinates]
        if any(not(-90<=p[0]<=90 and -180<=p[1]<=180) for p in geom):raise ValueError('Invalid coordinate')
        dm=float(r['distance']);duration=float(r['duration'])
        if not(math.isfinite(dm) and math.isfinite(duration)) or dm<=0 or duration<=0:raise ValueError('Invalid pedestrian metrics')
        # Large snapping gaps must not be hidden as a valid route to a building.
        snaps=[_distance(a,geom[0]),_distance(b,geom[-1])]
        if max(snaps)>75:raise ValueError('Foot route endpoint is more than 75 m from requested point')
        if dm+sum(snaps)<_distance(a,b)*.9:raise ValueError('Route distance inconsistent with endpoints')
        connector=sum(snaps)
        # Explicit short access connectors; do not discard their time/distance.
        if snaps[0]>.5:geom.insert(0,list(a))
        if snaps[1]>.5:geom.append(list(b))
        return {'geometry':geom,'distance_m':dm+connector,'duration_seconds':math.ceil(duration+connector/1.25),'geometry_kind':'osm_foot_route','snap_distance_m':round(connector,1),'access_connectors_estimated':connector>1,'estimated':True}
