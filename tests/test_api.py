import sys
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.storage import connection
@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'app.sqlite3'))
    def plan(*args):return {'proposals':[{'id':'p1','venue':{'id':'v','name':'Fixture room'},'start':'2026-11-03T10:00:00+01:00','itineraries':[]}],'rejections':[],'od_matrix':[{'user_id':p['user_id'],'venue_id':'v','duration_minutes':5} for p in args[1]],'data_status':{'fixture':True}}
    monkeypatch.setitem(sys.modules,'app.planner',SimpleNamespace(plan_meeting=plan))
    with TestClient(app) as c:yield c

def user(c,name):
    r=c.post('/api/auth/register',json={'name':name,'email':name+'@edu.umlp.fr','password':'safe-password123'});assert r.status_code==201,r.text
    b=r.json();assert b['user']['email_verified'] is False
    return b['user'],{'Authorization':'Bearer '+b['token']}
def meeting(c,h):
    r=c.post('/api/meetings',headers=h,json={'title':'Project','date':'2026-11-03','duration_minutes':30});assert r.status_code==201,r.text
    return r.json()['meeting']['id']
def inputs(c,m,h):
    r=c.put('/api/meetings/'+m+'/inputs',headers=h,json={'lat':47.5,'lon':6.8,'available_from':'09:00','available_until':'18:00','modes':['walk'],'max_walk_minutes':30});assert r.status_code==200,r.text
    return r.json()
def group(c):
    a,ah=user(c,'Alice');b,bh=user(c,'Bob');m=meeting(c,ah)
    assert c.post(f'/api/meetings/{m}/invitations',headers=ah,json={'user_ids':[b['id']]}).status_code==200
    assert c.post(f'/api/meetings/{m}/respond',headers=bh,json={'accept':True}).status_code==200
    inputs(c,m,ah);inputs(c,m,bh)
    assert c.post(f'/api/meetings/{m}/proposals',headers=ah).status_code==200
    for h in [ah,bh]:assert c.post(f'/api/meetings/{m}/decision',headers=h,json={'proposal_id':'p1','accept':True}).status_code==200
    assert c.get(f'/api/meetings/{m}',headers=ah).json()['meeting']['status']=='confirmed'
    return m,ah,bh

def test_invitation_privacy(client):
    a,ah=user(client,'Alice');b,bh=user(client,'Bob');e,eh=user(client,'Eve');m=meeting(client,ah);inputs(client,m,ah)
    assert client.get(f'/api/meetings/{m}',headers=eh).status_code==404
    assert client.get('/api/users?q=Ali',headers=bh).json()==[{'id':a['id'],'name':'Alice'}]
    client.post(f'/api/meetings/{m}/invitations',headers=ah,json={'user_ids':[b['id']]})
    data=client.get(f'/api/meetings/{m}',headers=bh).json();assert all(x['input'] is None for x in data['members'])
    assert data['proposals']==[]
    assert client.put(f'/api/meetings/{m}/location',headers=bh,json={'lat':47,'lon':6}).status_code==403

def test_live_consent_member_access_and_deletion(client):
    m,ah,bh=group(client);_,eh=user(client,'Eve')
    assert client.get(f'/api/meetings/{m}/locations',headers=ah).json()==[]
    assert client.post(f'/api/meetings/{m}/chat',headers=ah,json={'text':'At the station'}).status_code==201
    assert client.get(f'/api/meetings/{m}/chat',headers=bh).json()[0]['text']=='At the station'
    assert client.get(f'/api/meetings/{m}/chat',headers=eh).status_code==404
    assert client.put(f'/api/meetings/{m}/location',headers=ah,json={'lat':47.5,'lon':6.8,'accuracy':5}).status_code==200
    assert len(client.get(f'/api/meetings/{m}/locations',headers=bh).json())==1
    client.delete(f'/api/meetings/{m}/location',headers=ah)
    assert client.get(f'/api/meetings/{m}/locations',headers=bh).json()==[]
    client.put(f'/api/meetings/{m}/location',headers=bh,json={'lat':47.5,'lon':6.8})
    assert client.post(f'/api/meetings/{m}/complete',headers=bh).status_code==403
    assert client.post(f'/api/meetings/{m}/complete',headers=ah).status_code==200
    with connection() as db:assert db.execute('SELECT COUNT(*) FROM locations').fetchone()[0]==0
    assert client.post(f'/api/meetings/{m}/chat',headers=ah,json={'text':'after completion'}).status_code==409

def test_input_change_invalidates_approval(client):
    m,ah,bh=group(client);r=inputs(client,m,bh)
    assert r['meeting']['status']=='waiting' and r['proposals']==[] and r['approvals']==[]
    assert client.post(f'/api/meetings/{m}/decision',headers=ah,json={'proposal_id':'p1','accept':True}).status_code==409

def test_wait_for_group_inputs_and_owner_compute(client):
    a,ah=user(client,'Alice');b,bh=user(client,'Bob');m=meeting(client,ah);inputs(client,m,ah)
    client.post(f'/api/meetings/{m}/invitations',headers=ah,json={'user_ids':[b['id']]})
    assert client.post(f'/api/meetings/{m}/proposals',headers=ah).status_code==409
    client.post(f'/api/meetings/{m}/respond',headers=bh,json={'accept':True})
    assert client.post(f'/api/meetings/{m}/proposals',headers=ah).status_code==409
    inputs(client,m,bh)
    assert client.post(f'/api/meetings/{m}/proposals',headers=bh).status_code==403
    assert client.post(f'/api/meetings/{m}/proposals',headers=ah).status_code==200

def test_credentials_and_logout(client):
    u,h=user(client,'Alice')
    with connection() as db:
        row=db.execute('SELECT * FROM users').fetchone();token=db.execute('SELECT token_hash FROM sessions').fetchone()[0]
        assert row['password_hash'].startswith('pbkdf2_sha256$') and 'safe-password123' not in row['password_hash']
        assert token not in h['Authorization']
    assert client.post('/api/auth/login',json={'email':u['email'],'password':'incorrect'}).status_code==401
    assert client.get('/api/me').status_code==401
    assert client.post('/api/auth/logout',headers=h).status_code==200
    assert client.get('/api/me',headers=h).status_code==401


def test_edit_meeting_retains_people_and_inputs_but_resets_results(client):
    mid,ah,bh=group(client)
    before=client.get(f'/api/meetings/{mid}',headers=ah).json()
    payload={'title':'Afternoon retry','date':'2026-11-04','duration_minutes':45,'objective':'min_total','venue_ids':[]}
    assert client.put(f'/api/meetings/{mid}',headers=bh,json=payload).status_code==403
    edited=client.put(f'/api/meetings/{mid}',headers=ah,json=payload)
    assert edited.status_code==200,edited.text
    d=edited.json()
    assert d['meeting']['title']=='Afternoon retry' and d['meeting']['date']=='2026-11-04'
    assert d['meeting']['status']=='waiting' and not d['proposals'] and not d['approvals']
    assert d['members']==before['members']
    with connection() as db:db.execute("UPDATE meetings SET status='completed' WHERE id=?",(mid,))
    assert client.put(f'/api/meetings/{mid}',headers=ah,json=payload).json()['meeting']['status']=='waiting'


def test_delete_meeting_authorisation_cleanup_and_other_meeting_preserved(client):
    mid,ah,bh=group(client);other=meeting(client,ah)
    client.post(f'/api/meetings/{mid}/chat',headers=ah,json={'text':'Test message'})
    assert client.delete(f'/api/meetings/{mid}',headers=bh).status_code==403
    assert client.delete(f'/api/meetings/{mid}',headers=ah).status_code==204
    assert client.get(f'/api/meetings/{mid}',headers=ah).status_code==404
    assert client.get(f'/api/meetings/{other}',headers=ah).status_code==200
    assert client.get('/api/notifications',headers=bh).json()==[]
    with connection() as db:
        for table in ('members','messages','locations','approvals','notifications'):
            assert db.execute(f'SELECT COUNT(*) FROM {table} WHERE meeting_id=?',(mid,)).fetchone()[0]==0
