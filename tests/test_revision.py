"""Revision acceptance: independent departures, course f1, single winner."""
from datetime import date
from app import planner
from app.graph import closure,indoor_route
from app.walking import FootRouter

DAY=date(2026,11,3)
def person(uid='p',**kw):return dict(user_id=uid,name=uid,lat=47.5,lon=6.8,available_from='08:00',available_until='12:00',modes=['walk','transit'],max_walk_minutes=30,**kw)
def venue(vid='v',**kw):return {**dict(id=vid,name=vid,lat=47.55,lon=6.8,permitted=True,capacity=10,opening_hours={'tue':[['08:00','12:00']]}),**kw}
def meeting(**kw):return dict(id='m',date=DAY.isoformat(),duration_minutes=30,fast_mode=True,**kw)
def connection(a,b,dep,arr,trip):return dict(from_=a,to=b,dep=dep,arr=arr,trip_id=trip,route_name=trip,mode='bus')


def test_course_matrix_and_unreachable():
    r=closure([[0,1,8,-1],[-1,0,5,2],[1,-1,0,-1],[3,2,-1,0]])
    assert r['costs']==[[0,1,6,3],[5,0,5,2],[1,2,0,4],[3,2,7,0]]
    assert r['routes'][0][2]==[0,1,2]
    assert closure([[0,-1],[-1,0]])['costs'][0][1] is None


def test_indoor_graph_requires_verification_and_recovers_instructions():
    network={'verified':True,'nodes':{'a':{'name':'Entrance'},'b':{'name':'Room'}},'edges':[{'from':'a','to':'b','seconds':70}]}
    r=indoor_route(network,'a','b');assert r['duration_seconds']==70 and r['instructions']=='Entrance → Room'


def test_reverse_scan_latest_departure_keeps_scheduled_service(tmp_path,monkeypatch):
    p=person(boarding_margin_minutes=5);v=venue()
    stops={'s':dict(name='Stop',lat=47.501,lon=6.8),'d':dict(name='Destination',lat=v['lat'],lon=v['lon'])}
    c={'from':'s','to':'d','dep':planner.seconds('09:37'),'arr':planner.seconds('09:46'),'trip_id':'B','route_name':'B','mode':'bus'}
    monkeypatch.setattr(planner,'load_network',lambda *_:(stops,[c],[],{'warnings':[]}))
    r=planner.plan_meeting(meeting(),[p],[v],tmp_path)
    it=r['proposals'][0]['itineraries'][0];first=it['legs'][0];ride=next(l for l in it['legs'] if l['mode']=='bus')
    assert '09:46' in it['arrival']
    assert first['departure']>'2026-11-03T09:20:00+01:00'
    assert '09:37' in ride['departure']
    gap=(planner.datetime.fromisoformat(ride['departure'])-planner.datetime.fromisoformat(first['arrival'])).total_seconds()
    assert gap>=300 and it['duration_minutes']<20


def test_walkers_leave_independently_and_one_winner(tmp_path,monkeypatch):
    people=[person('long'),person('short')]
    people[1]['lat']=47.549
    venues=[venue(),venue('later',lat=47.56)]
    monkeypatch.setattr(planner,'load_network',lambda *_:({},[],[],{'warnings':[]}))
    people[0]['max_walk_minutes']=120
    r=planner.plan_meeting(meeting(),people,venues,tmp_path)
    assert len(r['proposals'])==1
    its=r['proposals'][0]['itineraries']
    assert its[0]['departure']!=its[1]['departure']
    assert its[0]['arrival']==its[1]['arrival']
    assert r['selection_evidence']['candidate_count']==2


def test_fast_api_mode_never_calls_pedestrian_network(tmp_path,monkeypatch):
    import json
    (tmp_path/'foot_routing.json').write_text(json.dumps({'enabled':True}))
    monkeypatch.setattr(FootRouter,'route',lambda *_:(_ for _ in ()).throw(AssertionError('Unexpected network call')))
    r=planner.plan_meeting(meeting(),[person()],[venue(lat=47.501)],tmp_path)
    assert r['data_status']['pedestrian_routing']['requests']==0


def test_minimum_sum_is_computed_on_current_itineraries(tmp_path,monkeypatch):
    monkeypatch.setattr(planner,'load_network',lambda *_:({},[],[],{'warnings':[]}))
    r=planner.plan_meeting(meeting(objective='min_total'),[person()],[venue('a',lat=47.501),venue('b',lat=47.502)],tmp_path)
    assert r['proposals'][0]['venue']['id']=='a'
    assert r['selection_evidence']['minimum_total_venue_id']=='a'


def test_no_walking_duration_input_or_dom_reference():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    assert 'id="maxwalk"' not in (root/'app/static/index.html').read_text()
    assert "$('maxwalk')" not in (root/'app/static/app.js').read_text()
    assert "'maxwalk'" not in (root/'app/static/app.js').read_text()


def test_verified_indoor_cost_is_included_in_meeting_and_departure(tmp_path,monkeypatch):
    import json
    network={'verified':True,'nodes':{'entry':{'name':'Entrance'},'room':{'name':'Room 1'}},'edges':[{'from':'entry','to':'room','seconds':120}]}
    (tmp_path/'indoor_networks.json').write_text(json.dumps({'building':network}))
    v=venue(lat=47.501,indoor={'network_id':'building','entrance_node':'entry','destination_node':'room'})
    monkeypatch.setattr(planner,'load_network',lambda *_:({},[],[],{'warnings':[]}))
    r=planner.plan_meeting(meeting(),[person()],[v],tmp_path)
    it=r['proposals'][0]['itineraries'][0]
    assert it['legs'][-1]['indoor']
    assert it['legs'][-1]['duration_minutes']==2
    assert it['arrival']==r['proposals'][0]['start']
    assert it['duration_minutes']>2
