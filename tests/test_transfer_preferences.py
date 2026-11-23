"""Equal-arrival routes prefer fewer boardings without losing walk feasibility."""
from datetime import date
from app import planner

DAY=date(2026,10,28)
def connection(a,b,dep,arr,trip,mode='train'):
    return {'from':a,'to':b,'dep':planner.seconds(dep),'arr':planner.seconds(arr),'trip_id':trip,'route_name':trip,'mode':mode}
def stop(name,lat):return {'name':name,'lat':lat,'lon':6.8}
def person(lat):return {'user_id':'p','name':'P','lat':lat,'lon':6.8,'available_from':'08:00','available_until':'10:00','modes':['transit'],'max_walk_minutes':20}
def boardings(result):return [l['trip_id'] for l in result['v']['legs'] if l['mode']!='walk']

def test_hericourt_waits_for_same_train_instead_of_belfort_detour(tmp_path):
    # Stop names/times reproduce the imported 28 Oct services. Coordinates are
    # deliberately synthetic to isolate boarding selection from other walking.
    stops={'h':stop('Héricourt',47.5),'b':stop('Belfort',47.7),'m':stop('Montbéliard',47.3)}
    cs=[connection('h','b','08:16','08:24','K13'),connection('b','h','08:36','08:44','C3'),connection('h','m','08:44','08:49','C3')]
    result=planner.journeys(person(47.51),[{'id':'v',**stops['m']}],stops,cs,[],DAY,tmp_path)
    assert result['v']['arrival_seconds']==planner.seconds('08:49')
    assert boardings(result)==['C3']
    assert result['v']['boardings']==1 and result['v']['transfers']==0
    ride=next(l for l in result['v']['legs'] if l['mode']=='train')
    assert ride['from_name']=='Héricourt' and '08:44' in ride['departure']


def test_professor_uses_one_bus_to_station_before_train(tmp_path):
    stops={k:stop(name,lat) for k,name,lat in [('r','République',47.5),('c','Clémenceau',47.53),('x','Colbert',47.56),('g','Gare',47.6),('m','Montbéliard',47.3)]}
    cs=[connection('r','c','08:02','08:03','2-out','bus'),connection('c','x','08:08','08:17','2-back','bus'),connection('r','g','08:10','08:16','2-direct','bus'),connection('x','g','08:21','08:23','3','bus'),connection('g','m','08:36','08:49','C3')]
    result=planner.journeys(person(47.5),[{'id':'v',**stops['m']}],stops,cs,[],DAY,tmp_path)
    assert result['v']['arrival_seconds']==planner.seconds('08:49')
    assert boardings(result)==['2-direct','C3']
    assert result['v']['transfers']==1


def test_earlier_arrival_remains_more_important_than_fewer_changes(tmp_path):
    stops={'a':stop('A',47.5),'b':stop('B',47.7),'d':stop('D',47.3)}
    cs=[connection('a','b','08:01','08:10','first'),connection('b','d','08:15','08:25','second'),connection('a','d','08:20','08:30','direct')]
    result=planner.journeys(person(47.5),[{'id':'v',**stops['d']}],stops,cs,[],DAY,tmp_path)
    assert result['v']['arrival_seconds']==planner.seconds('08:25')
    assert boardings(result)==['first','second']


def test_low_walking_onboard_alternative_survives_for_final_walk_budget(tmp_path):
    stops={'a':stop('A',47.5),'b':stop('B',47.7),'c':stop('C',47.9),'d':stop('D',48.1)}
    p=person(47.5);p['max_walk_minutes']=10
    costs={planner.walking_key(p,stops['c']):{'duration_seconds':480,'distance_m':600,'geometry':[[p['lat'],6.8],[stops['c']['lat'],6.8]],'geometry_kind':'osm_foot_route'}}
    dest={'id':'v',**stop('Venue',48.102)}
    cs=[connection('a','b','08:00','08:05','one'),connection('b','c','08:08','08:15','two'),connection('c','d','08:20','08:25','three')]
    result=planner.journeys(p,[dest],stops,cs,[],DAY,tmp_path,costs)
    # One boarding from C uses eight minutes walking plus almost three at D,
    # exceeding the ten-minute total. The three-boarding alternative is needed.
    assert boardings(result)==['one','two','three']
    assert result['v']['walking_minutes']<=10


def test_fewer_boardings_wins_even_with_more_permitted_walking(tmp_path):
    stops={'a':stop('A',47.5),'b':stop('B',47.503),'d':stop('D',47.7)}
    cs=[connection('a','b','08:00','08:05','feeder','bus'),connection('b','d','08:10','08:30','direct')]
    p=person(47.5);p['max_walk_minutes']=10
    result=planner.journeys(p,[{'id':'v',**stops['d']}],stops,cs,[],DAY,tmp_path)
    assert boardings(result)==['direct']
    assert 0<result['v']['walking_minutes']<=10
