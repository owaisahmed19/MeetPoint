from fastapi.testclient import TestClient
from app.main import app
from app import main


def test_real_group_plan_individual_states_and_stale_proposals(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'db.sqlite3'))
    monkeypatch.setattr(main,'DATA_DIR',tmp_path)
    with TestClient(app) as c:
        def account(name):
            r=c.post('/api/auth/register',json={'name':name,'email':name+'@example.test','password':'test-2026-pass'});assert r.status_code==201
            return r.json()['user']['id'],{'Authorization':'Bearer '+r.json()['token']}
        aid,ah=account('A');bid,bh=account('B')
        v=c.post('/api/venues',headers=ah,json={'name':'Fixture room','lat':47.51,'lon':6.8,'permitted':True,'capacity':6,'availability_status':'confirmed','opening_hours':{'tue':[['08:00','18:00']]}}).json()
        mid=c.post('/api/meetings',headers=ah,json={'title':'Test','date':'2026-11-03','venue_ids':[v['id']]}).json()['meeting']['id']
        assert c.post(f'/api/meetings/{mid}/invitations',headers=ah,json={'user_ids':[bid]}).status_code==200
        assert c.post(f'/api/meetings/{mid}/respond',headers=bh,json={'accept':True}).status_code==200
        for h,lat in [(ah,47.5),(bh,47.509)]:
            # Deliberately no walking-time input.
            r=c.put(f'/api/meetings/{mid}/inputs',headers=h,json={'lat':lat,'lon':6.8,'available_from':'08:00','available_until':'18:00','modes':['walk']});assert r.status_code==200
        d=c.post(f'/api/meetings/{mid}/proposals',headers=ah).json();assert len(d['proposals'])==1
        its=d['proposals'][0]['itineraries'];assert its[0]['departure']!=its[1]['departure']
        old=d['proposals'][0]['id']
        new=c.post(f'/api/meetings/{mid}/proposals',headers=ah).json()['proposals'][0]['id'];assert new!=old
        assert c.post(f'/api/meetings/{mid}/decision',headers=ah,json={'proposal_id':old,'accept':True}).status_code==404
        for h in [ah,bh]:
            r=c.post(f'/api/meetings/{mid}/decision',headers=h,json={'proposal_id':new,'accept':True});assert r.status_code==200
        d=r.json();assert d['meeting']['status']=='confirmed'
        assert all(x['state']!='travelling' for x in d['journey_schedule'])
        d=c.post(f'/api/meetings/{mid}/journey-state',headers=ah,json={'state':'travelling'}).json()
        states={x['user_id']:x['state'] for x in d['journey_schedule']}
        assert states[aid]=='travelling' and states[bid]!='travelling'
        body={k:val for k,val in v.items() if k not in ['id','can_edit','is_default','owner_id']};body['active']=False
        assert c.put('/api/venues/'+v['id'],headers=ah,json=body).status_code==200
        d=c.get(f'/api/meetings/{mid}',headers=bh).json();assert d['meeting']['status']=='waiting' and not d['approvals'] and not d['proposals']


def test_course_closure_route_and_frontend_contract(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'db.sqlite3'))
    with TestClient(app) as c:
        r=c.post('/api/auth/register',json={'name':'Reviewer','email':'reviewer@example.test','password':'test-2026-pass'})
        h={'Authorization':'Bearer '+r.json()['token']}
        d=c.post('/api/graph/closure',headers=h,json={'matrix':[[0,1,8,-1],[-1,0,5,2],[1,-1,0,-1],[3,2,-1,0]]}).json()
        assert d['algorithm']=='Repeated Dijkstra' and d['costs'][0][2]==6
        assert 'id="maxwalk"' not in c.get('/').text
        assert 'id="personal-schedule"' in c.get('/').text
