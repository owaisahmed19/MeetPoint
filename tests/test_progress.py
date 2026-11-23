from datetime import datetime,timedelta
from app.progress import estimate_progress
BASE='2026-11-03T10:00:00+01:00'
def sample():
 leg={'mode':'walk','departure':BASE,'arrival':'2026-11-03T10:10:00+01:00','geometry':[[47.5,6.8],[47.51,6.8]]}
 return {'lat':47.505,'lon':6.8,'accuracy':10,'timestamp':'2026-11-03T10:05:00+01:00'},{'arrival':leg['arrival'],'legs':[leg]},{'start':'2026-11-03T10:12:00+01:00','venue':{'lat':47.51,'lon':6.8}}
def test_estimate_and_advance():
 p,it,pr=sample();r=estimate_progress(p,it,pr,'2026-11-03',p['timestamp']);assert r['estimated_arrival']==it['arrival'];assert r['delay_minutes']==-2

def test_stale_inaccurate_wrongdate_offroute():
 p,it,pr=sample();assert estimate_progress(p,it,pr,'2026-11-03','2026-11-03T10:08:00+01:00')['status']=='stale'
 p['accuracy']=200;assert estimate_progress(p,it,pr,'2026-11-03',p['timestamp'])['status']=='inaccurate'
 p['accuracy']=10;assert estimate_progress(p,it,pr,'2026-11-04',p['timestamp'])['status']=='not_on_trip_date'
 p['lon']=6.9;assert estimate_progress(p,it,pr,'2026-11-03',p['timestamp'])['status']=='off_route'

def test_nearvenue_not_room():
 p,it,pr=sample();p['lat']=47.51;r=estimate_progress(p,it,pr,'2026-11-03',p['timestamp']);assert r['status']=='arrived';assert 'room' in r['note']

def test_late_progress_is_delay_against_meeting_start():
 p,it,pr=sample();p['timestamp']='2026-11-03T10:10:00+01:00'
 r=estimate_progress(p,it,pr,'2026-11-03',p['timestamp'])
 assert r['estimated_arrival']=='2026-11-03T10:15:00+01:00' and r['delay_minutes']==3

def test_missed_following_train_suppresses_eta():
 p,it,pr=sample();p['timestamp']='2026-11-03T10:10:00+01:00'
 it['legs'].append({'mode':'train','trip_id':'real-fixture','departure':'2026-11-03T10:12:00+01:00','arrival':'2026-11-03T10:22:00+01:00','geometry':[[47.51,6.8],[47.52,6.8]]})
 pr['venue']={'lat':47.52,'lon':6.8}
 r=estimate_progress(p,it,pr,'2026-11-03',p['timestamp'])
 assert r['status']=='missed_connection' and r['estimated_arrival'] is None
