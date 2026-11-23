"""Pedestrian geometry must affect feasibility, not merely decorate old times."""
import copy,io,json
from pathlib import Path
import pytest
from app.walking import FootRouter
from app.planner import _refine_walking


def configured(tmp_path):
    (tmp_path/'foot_routing.json').write_text(json.dumps({'enabled':True}),encoding='utf-8')
    return tmp_path


def test_router_cache_and_geojson_coordinate_order(tmp_path,monkeypatch):
    from app import walking
    configured(tmp_path);calls=[]
    payload={'code':'Ok','routes':[{'distance':180,'duration':130,'geometry':{'type':'LineString','coordinates':[[6.8,47.5],[6.8004,47.5005],[6.8,47.501]]}}]}
    def open_request(request,timeout):calls.append(request.full_url);return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(walking.urllib.request,'urlopen',open_request)
    monkeypatch.setattr(walking.time,'sleep',lambda _:None)
    router=FootRouter(tmp_path);route=router.route([47.5,6.8],[47.501,6.8])
    assert route['geometry'][0]==[47.5,6.8] and route['duration_seconds']==130
    assert '/routed-foot/' in calls[0] and route['geometry_kind']=='osm_foot_route'
    assert FootRouter(tmp_path).route([47.5,6.8],[47.501,6.8])['duration_seconds']==130
    assert len(calls)==1


def test_no_route_never_fabricates_street_geometry(tmp_path,monkeypatch):
    from app import walking
    configured(tmp_path)
    monkeypatch.setattr(walking.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(b'{"code":"NoRoute"}'))
    monkeypatch.setattr(walking.time,'sleep',lambda _:None)
    router=FootRouter(tmp_path)
    assert router.route([47.5,6.8],[47.501,6.8]) is None
    assert router.errors


def test_car_profile_and_far_snapping_are_rejected(tmp_path):
    (tmp_path/'foot_routing.json').write_text(json.dumps({'enabled':True,'base_url':'https://routing.openstreetmap.de/routed-car/route/v1/driving'}))
    with pytest.raises(ValueError):FootRouter(tmp_path)
    with pytest.raises(ValueError):FootRouter.validate({'code':'Ok','routes':[{'distance':200,'duration':150,'geometry':{'type':'LineString','coordinates':[[6.9,47.5],[6.9,47.501]]}}]},[47.5,6.8],[47.501,6.8])


def fixture():
    def walk(a,b,dep,arr):return {'mode':'walk','departure':dep,'arrival':arr,'distance_m':100,'duration_minutes':1,'geometry':[a,b],'geometry_kind':'approximate_straight_line','from_name':'A','to_name':'B'}
    first=walk([47.5,6.8],[47.501,6.8],'2026-11-03T10:00:00+01:00','2026-11-03T10:02:00+01:00')
    ride={'mode':'bus','trip_id':'published','departure':'2026-11-03T10:05:00+01:00','arrival':'2026-11-03T10:20:00+01:00','distance_m':3000,'duration_minutes':15,'geometry':[[47.501,6.8],[47.52,6.8]],'geometry_kind':'gtfs_shape'}
    final=walk([47.52,6.8],[47.521,6.8],'2026-11-03T10:20:00+01:00','2026-11-03T10:21:00+01:00')
    itinerary={'user_id':'a','name':'A','arrival':final['arrival'],'duration_minutes':21,'distance_m':3200,'legs':[first,ride,final]}
    venue={'id':'v','name':'Venue','opening_hours':{'tue':[['10:00','12:00']]}}
    result={'proposals':[{'id':'p','venue':venue,'start':final['arrival'],'end':'2026-11-03T10:51:00+01:00','itineraries':[itinerary]}],'rejections':[],'od_matrix':[{'user_id':'a','venue_id':'v','reachable':True}],'data_status':{'warnings':[]}}
    meeting={'id':'m','date':'2026-11-03','duration_minutes':30}
    people=[{'user_id':'a','name':'A','available_from':'10:00','available_until':'12:00','max_walk_minutes':30}]
    return result,meeting,people


def network(a,b,seconds):return {'geometry':[a,[(a[0]+b[0])/2,a[1]+.0001],b],'distance_m':200,'duration_seconds':seconds,'geometry_kind':'osm_foot_route','source':'test-foot-router','estimated':True}


def test_real_walking_replays_arrival_and_meeting_window(tmp_path,monkeypatch):
    configured(tmp_path)
    monkeypatch.setattr(FootRouter,'route',lambda self,a,b:network(a,b,180 if a[0]<47.51 else 120))
    result,meeting,people=fixture();updated=_refine_walking(result,meeting,people,tmp_path)
    p=updated['proposals'][0];it=p['itineraries'][0]
    assert p['start']=='2026-11-03T10:22:00+01:00'
    assert it['legs'][0]['arrival']=='2026-11-03T10:03:00+01:00'
    assert it['legs'][1]['departure']=='2026-11-03T10:05:00+01:00'
    assert it['duration_minutes']==22 and it['walking_minutes']==5
    assert updated['od_matrix'][0]['legs'][0]['geometry_kind']=='osm_foot_route'


def test_longer_real_walk_cannot_keep_a_missed_bus(tmp_path,monkeypatch):
    configured(tmp_path)
    monkeypatch.setattr(FootRouter,'route',lambda self,a,b:network(a,b,600))
    result,meeting,people=fixture();updated=_refine_walking(result,meeting,people,tmp_path)
    assert updated['proposals']==[]
    assert updated['rejections'][0]['requires_replanning'] is True
    assert 'scheduled connection' in updated['rejections'][0]['reason']
