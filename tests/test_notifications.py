"""Recipient-private, durable invitations and upgrade backfill behavior."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.storage import connection

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'notifications.sqlite3'))
    with TestClient(app) as c:yield c

def account(c,name):
    r=c.post('/api/auth/register',json={'name':name,'email':name+'@example.edu','password':'safe-password123'})
    assert r.status_code==201
    u=r.json();return u['user'],{'Authorization':'Bearer '+u['token']}

def meeting(c,h):
    r=c.post('/api/meetings',headers=h,json={'title':'Project discussion','date':'2026-11-03'})
    assert r.status_code==201
    return r.json()['meeting']['id']

def invite(c,h,mid,target):
    r=c.post(f'/api/meetings/{mid}/invitations',headers=h,json={'user_ids':[target]})
    assert r.status_code==200,r.text
    return r.json()

def test_invitation_event_is_durable_private_and_deduplicated(client):
    a,ah=account(client,'Alice');b,bh=account(client,'Bob');_,eh=account(client,'Eve');mid=meeting(client,ah)
    invite(client,ah,mid,b['id'])
    assert client.get('/api/notifications').status_code==401
    assert client.get('/api/notifications',headers=ah).json()==[]
    event=client.get('/api/notifications',headers=bh).json()[0]
    assert event['meeting_id']==mid and event['meeting_title']=='Project discussion'
    assert event['sender_name']=='Alice' and event['kind']=='invitation'
    assert event['read_at'] is None and event['actionable'] is True
    assert not {'email','lat','lon','input','user_id','sender_id'} & event.keys()
    assert client.get('/api/notifications',headers=eh).json()==[]
    assert client.post('/api/notifications/'+event['id']+'/read',headers=eh).status_code==404
    invite(client,ah,mid,b['id'])
    assert len(client.get('/api/notifications',headers=bh).json())==1
    # New API client simulates re-opening after the invite; event is not transient.
    with TestClient(app) as reopened:
        assert reopened.get('/api/notifications',headers=bh).json()==[event]
    assert client.post('/api/notifications/'+event['id']+'/read',headers=bh).status_code==200
    read=client.get('/api/notifications',headers=bh).json()[0]
    assert read['read_at'] and read['actionable']
    assert client.post('/api/notifications/'+event['id']+'/read',headers=bh).status_code==200
    assert client.get('/api/notifications',headers=bh).json()[0]['read_at']==read['read_at']

def test_response_marks_read_and_reinvite_creates_new_event(client):
    a,ah=account(client,'Alice');b,bh=account(client,'Bob');mid=meeting(client,ah)
    invite(client,ah,mid,b['id'])
    old=client.get('/api/notifications',headers=bh).json()[0]
    assert client.post(f'/api/meetings/{mid}/respond',headers=bh,json={'accept':False}).status_code==200
    history=client.get('/api/notifications',headers=bh).json()
    assert history[0]['read_at'] and not history[0]['actionable']
    invite(client,ah,mid,b['id'])
    events=client.get('/api/notifications',headers=bh).json()
    assert len(events)==2 and events[0]['id']!=old['id'] and events[0]['read_at'] is None
    assert client.post('/api/notifications/read-all',headers=bh).status_code==200
    assert all(e['read_at'] for e in client.get('/api/notifications',headers=bh).json())
    assert client.post(f'/api/meetings/{mid}/respond',headers=bh,json={'accept':True}).status_code==200
    invite(client,ah,mid,b['id'])
    assert len(client.get('/api/notifications',headers=bh).json())==2
    assert all(not e['actionable'] for e in client.get('/api/notifications',headers=bh).json())

def test_preupdate_pending_invitation_is_backfilled_once(client):
    a,ah=account(client,'Alice');b,bh=account(client,'Bob');mid=meeting(client,ah)
    # Old releases had membership invitations but no notification records.
    with connection() as db:
        db.execute("INSERT INTO members VALUES (?,?,'invited',NULL)",(mid,b['id']))
    first=client.get('/api/notifications',headers=bh).json()
    assert len(first)==1 and first[0]['actionable']
    assert client.get('/api/notifications',headers=bh).json()==first
    listed=client.get('/api/meetings',headers=bh).json()
    assert listed[0]['organiser_name']=='Alice'
    assert client.post('/api/notifications/read-all',headers=ah).status_code==200
    assert client.get('/api/notifications',headers=bh).json()[0]['read_at'] is None
    with connection() as db:db.execute("UPDATE meetings SET status='completed' WHERE id=?",(mid,))
    assert not client.get('/api/notifications',headers=bh).json()[0]['actionable']
