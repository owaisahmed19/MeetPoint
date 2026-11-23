"""Timetable re-search must use learned pedestrian costs, not reject the old bus."""
import json
import pytest
from app import planner
from app.walking import FootRouter


def scenario(tmp_path,monkeypatch,transfer=False):
    (tmp_path/'foot_routing.json').write_text(json.dumps({'enabled':True}))
    def stop(name,lat):return {'name':name,'lat':lat,'lon':6.8}
    stops={'a':stop('A',47.501),'d':stop('D',47.54)}
    def conn(a,b,dep,arr,trip):return {'from':a,'to':b,'dep':planner.seconds(dep),'arr':planner.seconds(arr),'trip_id':trip,'mode':'bus','route_name':trip}
    cs=[conn('a','d','08:05','08:15','early'),conn('a','d','08:20','08:30','late')]
    person={'user_id':'p','name':'P','lat':47.5,'lon':6.8,'available_from':'08:00','available_until':'10:00','modes':['walk','transit'],'max_walk_minutes':20}
    if transfer:
        stops={'a':stop('A',47.5),'b':stop('B',47.52),'c':stop('C',47.521),'d':stop('D',47.55)}
        cs=[conn('a','b','08:00','08:05','first'),conn('c','d','08:10','08:20','early'),conn('c','d','08:25','08:35','late')]
    venue={'id':'v','name':'Meeting room','lat':stops['d']['lat'],'lon':6.8,'permitted':True,'capacity':8,'opening_hours':{'thu':[['08:00','10:00']]}}
    meeting={'id':'m','date':'2026-10-29','duration_minutes':30,'objective':'earliest'}
    monkeypatch.setattr(planner,'load_network',lambda *_:(stops,cs,[],{'warnings':[]}))
    calls=[]
    def routed(self,a,b):
        calls.append((a,b));return {'geometry':[a,b],'distance_m':750,'duration_seconds':600,'geometry_kind':'osm_foot_route','estimated':True}
    monkeypatch.setattr(FootRouter,'route',routed)
    return meeting,[person],[venue],calls

@pytest.mark.parametrize('transfer,expected',[(False,'08:30'),(True,'08:35')])
def test_later_scheduled_service_after_network_walk(tmp_path,monkeypatch,transfer,expected):
    m,people,venues,calls=scenario(tmp_path,monkeypatch,transfer)
    r=planner.plan_meeting(m,people,venues,tmp_path)
    assert r['proposals']
    p=r['proposals'][0];legs=p['itineraries'][0]['legs']
    assert p['start'].startswith('2026-10-29T'+expected)
    assert 'late' in [x.get('trip_id') for x in legs]
    assert 'early' not in [x.get('trip_id') for x in legs]
    assert p['itineraries'][0]['walking_minutes']<=20
    assert r['data_status']['pedestrian_routing']['replanning_passes']>=2
    assert not any(x.get('requires_replanning') for x in r['rejections'])
    assert calls


def test_refinement_can_backfill_a_fourth_venue(tmp_path,monkeypatch):
    m,people,venues,_=scenario(tmp_path,monkeypatch)
    people[0].update(modes=['walk'],max_walk_minutes=20)
    # Three apparently closest rooms require long actual walks. Fourth remains feasible.
    venues=[{**venues[0],'id':str(i),'lat':47.5+.001*(i+1)} for i in range(4)]
    def route(self,a,b):
        duration=1500 if b[0]<47.5035 else 600
        return {'geometry':[a,b],'distance_m':duration*1.25,'duration_seconds':duration,'geometry_kind':'osm_foot_route','estimated':True}
    monkeypatch.setattr(FootRouter,'route',route)
    r=planner.plan_meeting(m,people,venues,tmp_path)
    assert [p['venue']['id'] for p in r['proposals']]==['3']
    assert r['proposals'][0]['start'].startswith('2026-10-29T08:10')


def test_unknown_hours_are_not_claimed_closed_or_time_infeasible(tmp_path,monkeypatch):
    m,people,venues,_=scenario(tmp_path,monkeypatch);venues[0]['opening_hours']={}
    r=planner.plan_meeting(m,people,venues,tmp_path)
    assert 'not verified' in r['rejections'][0]['reason']
    assert 'cannot fit' not in r['rejections'][0]['reason']
    assert 'Closed' not in r['rejections'][0]['reason']


def test_unresolved_routes_are_explicit_not_claimed_verified(tmp_path,monkeypatch):
    m,people,venues,_=scenario(tmp_path,monkeypatch)
    monkeypatch.setattr(FootRouter,'route',lambda *_:None)
    r=planner.plan_meeting(m,people,venues,tmp_path)
    assert r['proposals'] and r['data_status']['planning_incomplete']
    assert not r['proposals'][0]['walking_geometry_complete']


def test_transit_geometry_is_cached_without_mutating_merged_paths(monkeypatch):
    from app import planner
    from datetime import date
    calls=[]
    def geometry(c,stops,data_dir):
        calls.append((c['from'],c['to']))
        return ([[47.5,6.8],[47.51,6.81]] if c['from']=='a' else [[47.51,6.81],[47.52,6.82]]),'gtfs_shape'
    monkeypatch.setattr(planner,'shape_geometry',geometry)
    stops={k:{'name':k,'lat':47.5+i*.01,'lon':6.8+i*.01} for i,k in enumerate('abc')}
    conns=[{'trip_id':'bus','from':a,'to':b,'dep':8*3600+i*60,'arr':8*3600+(i+1)*60,'mode':'bus','route_name':'T1'} for i,(a,b) in enumerate([('a','b'),('b','c')])]
    path=[planner.transit(c,stops) for c in conns];cache={}
    first=planner.materialise(path,stops,date(2026,10,29),geometry_cache=cache)
    second=planner.materialise(path,stops,date(2026,10,29),geometry_cache=cache)
    assert first==second and len(calls)==2
    assert len(first)==1 and len(first[0]['geometry'])==3
    assert all(len(value[0])==2 for value in cache.values())
