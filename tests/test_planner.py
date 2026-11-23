import json,tempfile,unittest,zipfile,io,csv
from pathlib import Path
from datetime import date
from unittest.mock import patch
from app.gtfs import import_feed,load_network,service_active
from app.planner import plan_meeting,journeys


def person(uid='a',**kw):return {'user_id':uid,'name':uid,'lat':47.5,'lon':6.8,'available_from':'08:00','available_until':'18:00','modes':['walk','transit'],'max_walk_minutes':30,**kw}
def venue(vid='v',**kw):return {'id':vid,'name':vid,'lat':47.5005,'lon':6.8,'permitted':True,'capacity':8,'availability_status':'unconfirmed','opening_hours':{'tue':[['08:00','18:00']]},**kw}
def meeting(**kw):return {'id':'m','date':'2026-11-03','duration_minutes':30,'objective':'earliest',**kw}


class PlannerTests(unittest.TestCase):
    def test_no_feed_does_not_invent_transit(self):
        with tempfile.TemporaryDirectory() as td:r=plan_meeting(meeting(),[person(modes=['transit'])],[venue()],td)
        self.assertFalse(r['data_status']['transit_available']);self.assertFalse(r['proposals']);self.assertTrue(r['rejections'])
    def test_walk_proposal_conditional_and_approximate(self):
        with tempfile.TemporaryDirectory() as td:r=plan_meeting(meeting(),[person()],[venue()],td)
        p=r['proposals'][0];self.assertTrue(p['conditional']);self.assertEqual(p['itineraries'][0]['legs'][0]['geometry_kind'],'approximate_straight_line');self.assertIn('latest_start',p)
    def test_capacity_group_minimum_and_booking(self):
        with tempfile.TemporaryDirectory() as td:
            for v in [venue(capacity=0),venue(min_group_size=2),venue(max_booking_minutes=10)]:
                self.assertFalse(plan_meeting(meeting(),[person()],[v],td)['proposals'])
    def test_whole_duration_must_fit_opening(self):
        with tempfile.TemporaryDirectory() as td:
            r=plan_meeting(meeting(),[person()],[venue(opening_hours={'tue':[['08:00','08:15']]})],td)
        self.assertFalse(r['proposals'])
    def test_exception_overrides_calendar(self):
        f={'calendar':{'s':{'start_date':'20260101','end_date':'20261231','tuesday':'1'}},'calendar_dates':[{'service_id':'s','date':'20261103','exception_type':'2'}]}
        self.assertFalse(service_active(f,'s',date(2026,11,3)))
        f['calendar_dates'][0]['exception_type']='1';self.assertTrue(service_active(f,'s',date(2026,11,3)))
    def test_transfer_buffer_prevents_impossible_connection(self):
        stops={sid:{'lat':47.5+i*.01,'lon':6.8,'name':sid} for i,sid in enumerate(['a','b','c'])}
        cs=[{'from':'a','to':'b','dep':8*3600,'arr':8*3600+600,'trip_id':'one','route_name':'1','mode':'bus'}, {'from':'b','to':'c','dep':8*3600+660,'arr':8*3600+900,'trip_id':'two','route_name':'2','mode':'bus'}]
        p=person(modes=['transit'],max_walk_minutes=1);dest=venue(lat=stops['c']['lat']);r=journeys(p,[dest],stops,cs,[],date(2026,11,3));self.assertFalse(r)
        cs[1]['dep']+=180;cs[1]['arr']+=180;r=journeys(p,[dest],stops,cs,[],date(2026,11,3));self.assertIn('v',r)
    def test_distinct_objectives(self):
        # A has lower sum (2+2+14), B earlier last arrival (7+7+7).
        def routes(p,venues,*_):
            times={'a':[2,7],'b':[2,7],'c':[14,7]};return {v['id']:{'user_id':p['user_id'],'name':p['name'],'arrival_seconds':28800+times[p['user_id']][i]*60,'arrival':'2026-11-03T08:00:00+01:00','duration_minutes':times[p['user_id']][i],'distance_m':100,'legs':[]} for i,v in enumerate(venues)}
        with tempfile.TemporaryDirectory() as td,patch('app.planner.journeys',routes):
            vs=[venue('A'),venue('B')];ps=[person(x) for x in ['a','b','c']]
            self.assertEqual(plan_meeting(meeting(),ps,vs,td)['proposals'][0]['venue']['id'],'B')
            self.assertEqual(plan_meeting(meeting(objective='min_total'),ps,vs,td)['proposals'][0]['venue']['id'],'A')
    def test_import_namespaces_and_after_midnight(self):
        tables={
        'agency.txt':'agency_id,agency_name,agency_url,agency_timezone\na,Demo,https://example.org,Europe/Paris\n',
        'stops.txt':'stop_id,stop_name,stop_lat,stop_lon\na,A,47.5,6.8\nb,B,47.51,6.8\n',
        'routes.txt':'route_id,route_short_name,route_type\nr,R,3\n',
        'trips.txt':'route_id,service_id,trip_id\nr,s,t\n',
        'stop_times.txt':'trip_id,arrival_time,departure_time,stop_id,stop_sequence\nt,24:05:00,24:05:00,a,1\nt,24:10:00,24:10:00,b,2\n',
        'calendar_dates.txt':'service_id,date,exception_type\ns,20261102,1\n'}
        with tempfile.TemporaryDirectory() as td:
            z=Path(td)/'f.zip'
            with zipfile.ZipFile(z,'w') as f:
                for name,body in tables.items():f.writestr(name,body)
            out=Path(td)/'processed';import_feed(z,out,'first');import_feed(z,out,'second')
            stops,cs,_,status=load_network(td,date(2026,11,3))
            self.assertIn('first:a',stops);self.assertIn('second:a',stops);self.assertEqual(len(cs),2);self.assertEqual(cs[0]['dep'],300);self.assertTrue(status['transit_available'])

if __name__=='__main__':unittest.main()


def test_dominated_alighting_label_still_stays_on_same_vehicle():
    stops={sid:{'lat':47.5+i*.02,'lon':6.8,'name':sid} for i,sid in enumerate(['a','b','c'])}
    cs=[{'from':a,'to':b,'dep':d,'arr':r,'trip_id':trip,'route_name':trip,'mode':'bus'} for a,b,d,r,trip in [
        ('a','b',28800,29400,'first'),('a','b',28860,29460,'through'),('b','c',29490,29700,'through')]]
    p=person(modes=['transit'],max_walk_minutes=1)
    result=journeys(p,[venue(lat=stops['c']['lat'])],stops,cs,[],date(2026,11,3))
    assert result['v']['arrival_seconds']==29700
    assert next(l for l in result['v']['legs'] if l['mode']=='bus')['route_name']=='through'
