"""Conservative map geometry from official SNCF active rail corridors.

This supplies geographical line geometry only. GTFS remains the sole source of
service, stop order and timetable. A corridor is not a certified train-specific
track shape. Unsupported inter-line paths are deliberately not invented.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import json, math

SOURCE='https://data.sncf.com/explore/dataset/formes-des-lignes-du-rfn/'
NOTE='Official SNCF Réseau active rail corridor, projected between scheduled stops; decametric precision, not a certified trip-specific track.'
R=6371000

def metres(a,b):
    return R*math.hypot(math.radians(a[0]-b[0]),math.radians(a[1]-b[1])*math.cos(math.radians((a[0]+b[0])/2)))

@lru_cache(maxsize=4)
def _load(path,mtime):
    try:return json.loads(Path(path).read_text(encoding='utf-8')).get('records',[])
    except (OSError,ValueError):return []

def _project(point,line):
    best=None;running=0
    coslat=math.cos(math.radians(point[0]))
    for i,(a,b) in enumerate(zip(line,line[1:])):
        ax=R*math.radians(a[1]-point[1])*coslat;ay=R*math.radians(a[0]-point[0])
        bx=R*math.radians(b[1]-point[1])*coslat;by=R*math.radians(b[0]-point[0])
        dx,dy=bx-ax,by-ay;denom=dx*dx+dy*dy
        fraction=max(0.,min(1.,-(ax*dx+ay*dy)/denom)) if denom else 0.
        off=math.hypot(ax+fraction*dx,ay+fraction*dy)
        snapped=[a[0]+fraction*(b[0]-a[0]),a[1]+fraction*(b[1]-a[1])]
        length=metres(a,b)
        candidate=(off,i+fraction,snapped,running+fraction*length)
        if best is None or off<best[0]:best=candidate
        running+=length
    return best

def _slice(line,a,b):
    reverse=a[1]>b[1]
    if reverse:a,b=b,a
    points=[a[2]]
    for i in range(math.floor(a[1])+1,math.ceil(b[1])):
        if i<len(line):points.append(line[i])
    points.append(b[2])
    clean=[points[0]]
    for p in points[1:]:
        if metres(clean[-1],p)>.01:clean.append(p)
    return list(reversed(clean)) if reverse else clean

def rail_shape(a,b,data_dir=None):
    """Return a sourced corridor between two stops, or None if unsupported.

    Both ends must project within 200m onto one continuous active official line.
    Never joins disconnected polylines or substitutes road/car routing.
    """
    data_dir=Path(data_dir) if data_dir is not None else Path(__file__).resolve().parents[1]/'data'
    path=data_dir/'rail_geometry.json'
    try:records=_load(str(path.resolve()),path.stat().st_mtime_ns)
    except OSError:return None
    try:pa=[float(a['lat']),float(a['lon'])];pb=[float(b['lat']),float(b['lon'])]
    except (KeyError,ValueError,TypeError):return None
    direct=metres(pa,pb)
    if direct<1:return None
    candidates=[]; mapped=[]
    for record in records:
        if record.get('mnemo')!='EXPLOITE':continue
        g=record.get('geo_shape',{});g=g.get('geometry',g)
        lines=[g.get('coordinates',[])] if g.get('type')=='LineString' else g.get('coordinates',[]) if g.get('type')=='MultiLineString' else []
        for raw in lines:
            try:line=[[float(p[1]),float(p[0])] for p in raw]
            except (ValueError,IndexError,TypeError):continue
            if len(line)<2:continue
            aa,bb=_project(pa,line),_project(pb,line)
            mapped.append((record.get('code_ligne',''),line,aa,bb))
            if aa is None or bb is None or max(aa[0],bb[0])>200:continue
            along=abs(aa[3]-bb[3])
            if along<direct*.7 or along>max(direct*4,direct+3000):continue
            points=_slice(line,aa,bb)
            if len(points)>1:candidates.append((aa[0]+bb[0],along,record.get('code_ligne',''),points,False))
    # Official corridors can change line identifiers at a junction (e.g. Dole–
    # Belfort joins Paris–Mulhouse before Belfort station). Join only an actual
    # corridor endpoint within 15m of another corridor, within source precision.
    # Never bridge an arbitrary gap or an interior crossing on different levels.
    for code1,line1,aa,_ in mapped:
        if aa is None or aa[0]>200:continue
        for code2,line2,_,bb in mapped:
            if line1 is line2 or bb is None or bb[0]>200:continue
            for first in (True,False):
                endpoint=line1[0] if first else line1[-1]
                join2=_project(endpoint,line2)
                if join2 is None or join2[0]>15:continue
                join1=_project(endpoint,line1)
                along=abs(aa[3]-join1[3])+join2[0]+abs(bb[3]-join2[3])
                if along<direct*.7 or along>max(direct*4,direct+3000):continue
                left=_slice(line1,aa,join1);right=_slice(line2,join2,bb)
                points=left+right
                if len(points)>1:candidates.append((aa[0]+bb[0],along,code1+' / '+code2,points,True))
            for endpoint in (line2[0],line2[-1]):
                join1=_project(endpoint,line1)
                if join1 is None or join1[0]>15:continue
                join2=_project(endpoint,line2)
                along=abs(aa[3]-join1[3])+join1[0]+abs(bb[3]-join2[3])
                if along<direct*.7 or along>max(direct*4,direct+3000):continue
                points=_slice(line1,aa,join1)+_slice(line2,join2,bb)
                if len(points)>1:candidates.append((aa[0]+bb[0],along,code1+' / '+code2,points,True))
    if not candidates:return None
    off,length,code,points,joined=min(candidates,key=lambda c:(c[0],c[1]))
    return {'geometry':points,'geometry_kind':'sncf_rail_corridor','geometry_source':SOURCE,'geometry_note':NOTE+(' Connected at an official corridor endpoint within 15m source precision.' if joined else ''),'rail_line_code':code,'distance_m':round(length),'estimated':True}
