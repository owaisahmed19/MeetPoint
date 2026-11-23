"""Conservative arrival estimates from opt-in positions; no operator live data."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import math
PARIS=ZoneInfo('Europe/Paris')
def parse(v):
 d=v if isinstance(v,datetime) else datetime.fromisoformat(str(v).replace('Z','+00:00'))
 return d if d.tzinfo else d.replace(tzinfo=PARIS)
def distance(a,b):
 return 6371000*math.hypot(math.radians(a[0]-b[0]),math.radians(a[1]-b[1])*math.cos(math.radians((a[0]+b[0])/2)))
def projection(p,g):
 if not g:return None
 if len(g)==1:return distance(p,g[0]),1
 pts=[(6371000*math.radians(x[1]-p[1])*math.cos(math.radians(p[0])),6371000*math.radians(x[0]-p[0])) for x in g]
 lengths=[math.dist(a,b) for a,b in zip(pts,pts[1:])];total=sum(lengths)
 if total<.01:return math.hypot(*pts[0]),1
 best=None;passed=0
 for a,b,length in zip(pts,pts[1:],lengths):
  dx,dy=b[0]-a[0],b[1]-a[1];f=max(0,min(1,-(a[0]*dx+a[1]*dy)/(length*length))) if length else 0
  q=(math.hypot(a[0]+f*dx,a[1]+f*dy),(passed+f*length)/total)
  if best is None or q[0]<best[0]:best=q
  passed+=length
 return best

def estimate_progress(position,itinerary,proposal,meeting_date,now=None):
 now=parse(now or datetime.now(timezone.utc));scheduled=(itinerary or {}).get('arrival')
 base={'status':'no_itinerary','estimated_arrival':None,'delay_minutes':None,'scheduled_arrival':scheduled,'note':'No usable selected itinerary.'}
 def unknown(status,note):return dict(base,status=status,note=note)
 if not itinerary or not itinerary.get('legs'):return base
 if now.astimezone(PARIS).date().isoformat()!=str(meeting_date):return unknown('not_on_trip_date','Outside the planned trip date.')
 try:
  age=(now-parse(position['timestamp'])).total_seconds()
  if age>120 or age < -30:return unknown('stale','Old or invalid position timestamp.')
  accuracy=position.get('accuracy')
  if accuracy is not None and (not math.isfinite(float(accuracy)) or float(accuracy)>150):return unknown('inaccurate','Location accuracy exceeds 150 metres.')
  point=(float(position['lat']),float(position['lon']));start=parse(proposal['start']);legs=itinerary['legs'];v=proposal.get('venue',{})
  dest=(float(v['lat']),float(v['lon'])) if v.get('lat') is not None else tuple(legs[-1]['geometry'][-1])
 except (TypeError,KeyError,ValueError,IndexError):return base
 def arrived(status,eta,note):return dict(base,status=status,estimated_arrival=eta.astimezone(PARIS).isoformat(),delay_minutes=round((eta-start).total_seconds()/60,1),note=note)
 if distance(point,dest)<=50:return arrived('arrived',parse(position['timestamp']),'Near venue only; indoor room arrival is not verified.')
 if now<parse(legs[0]['departure']):return unknown('not_started','Before the scheduled journey departure.')
 candidates=[]
 for i,l in enumerate(legs):
  try:
   q=projection(point,l.get('geometry',[]));dep,arr=parse(l['departure']),parse(l['arrival'])
   if q is not None and q[0]<=min(150,max(30,float(accuracy or 30))):candidates.append((q[0],max((dep-now).total_seconds(),(now-arr).total_seconds(),0),i,q[1],dep,arr))
  except (KeyError,ValueError,TypeError):continue
 if not candidates:return unknown('off_route','Position is outside the planned route; replanning needed.')
 nearest=min(x[0] for x in candidates)
 _,_,idx,f,dep,arr=min((x for x in candidates if x[0]<=nearest+10),key=lambda x:(x[1],x[0],x[2]))
 current=legs[idx];transit=current['mode']!='walk'
 if transit and f<.02 and now>dep+timedelta(seconds=60):return unknown('missed_connection','Boarding time has passed; boarding/vehicle delay cannot be verified.')
 cursor=arr if transit and now<=dep else now+timedelta(seconds=max(0,(arr-dep).total_seconds())*(1-f))
 has_boarded=transit or any(l['mode']!='walk' for l in legs[:idx]);last_trip=current.get('trip_id') if transit else None
 for j,l in enumerate(legs[idx+1:],idx+1):
  d,a=parse(l['departure']),parse(l['arrival'])
  if l['mode']=='walk':cursor+=a-d
  else:
   allowance=max(0,min(180,(d-parse(legs[j-1]['arrival'])).total_seconds())) if has_boarded and l.get('trip_id')!=last_trip else 0
   if cursor+timedelta(seconds=allowance)>d:return unknown('missed_connection','A scheduled connection is no longer reachable; ETA unknown until replanning.')
   cursor=a;has_boarded=True;last_trip=l.get('trip_id')
 return arrived('estimated',cursor,'Approximate estimate from person position and planned route durations; not a live vehicle delay or verified map matching.')
