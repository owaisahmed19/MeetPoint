"""Independent API integration using the actual walking planner, no timetable fixture."""
import json
from fastapi.testclient import TestClient
import app.main as main

def test_real_planner_group_lifecycle_and_private_exports(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'review.sqlite3'))
    data=tmp_path/'data';data.mkdir()
    (data/'venues.json').write_text(json.dumps([{'id':'review-room','name':'Permitted test room','lat':47.5,'lon':6.8,'permitted':True,'capacity':4,'min_group_size':2,'availability_status':'unconfirmed','opening_hours':{'tue':[['08:00','18:00']]}}]),encoding='utf-8')
    monkeypatch.setattr(main,'DATA_DIR',data)
    with TestClient(main.app) as c:
        def account(name):
            r=c.post('/api/auth/register',json={'name':name,'email':name.lower().replace(' ','')+'@edu.umlp.fr','password':'review-password1'});assert r.status_code==201
            d=r.json();return d['user']['id'],{'Authorization':'Bearer '+d['token']}
        a,ah=account('Reviewer A');b,bh=account('Reviewer B');_,eh=account('Other group')
        r=c.post('/api/meetings',headers=ah,json={'title':'Real planner review','date':'2026-11-03','duration_minutes':30});mid=r.json()['meeting']['id'];base=f'/api/meetings/{mid}'
        c.post(base+'/invitations',headers=ah,json={'user_ids':[b]})
        inp={'lat':47.5001,'lon':6.8001,'available_from':'09:00','available_until':'12:00','modes':['walk'],'max_walk_minutes':20}
        c.put(base+'/inputs',headers=ah,json=inp)
        before=c.get(base,headers=bh).json();assert all(m['input'] is None for m in before['members'])
        assert c.get(base+'/od-matrix.csv',headers=eh).status_code==404
        c.post(base+'/respond',headers=bh,json={'accept':True});c.put(base+'/inputs',headers=bh,json=inp)
        r=c.post(base+'/proposals',headers=ah);assert r.status_code==200,r.text
        d=r.json();p=d['proposals'][0]
        assert p['conditional'] is True and len(p['itineraries'])==2
        assert all(leg['mode']=='walk' for it in p['itineraries'] for leg in it['legs'])
        assert all(leg['estimated'] for it in p['itineraries'] for leg in it['legs'])
        assert len(d['od_matrix'])==2 and d['data_status']['transit_available'] is False
        assert c.get(base+'/od-matrix.csv',headers=ah).status_code==200
        for h in [ah,bh]:assert c.post(base+'/decision',headers=h,json={'proposal_id':p['id'],'accept':True}).status_code==200
        assert c.get(base,headers=ah).json()['meeting']['status']=='confirmed'
        assert c.get(base+'/locations',headers=ah).json()==[]
        c.put(base+'/location',headers=bh,json={'lat':47.5,'lon':6.8,'accuracy':5})
        locs=c.get(base+'/locations',headers=ah).json();assert len(locs)==1 and locs[0]['user_id']==b
        assert c.get(base+'/locations',headers=eh).status_code==404
        c.post(base+'/complete',headers=ah)
        from app.storage import connection
        with connection() as db:assert db.execute('SELECT COUNT(*) FROM locations').fetchone()[0]==0
