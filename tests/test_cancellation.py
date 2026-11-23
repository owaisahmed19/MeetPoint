"""Reversible cancellation, stale invite protection and live-data cleanup."""
import json,sys
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.storage import connection

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'cancel.sqlite3'))
    with TestClient(app) as c:yield c

def user(c,name):
    r=c.post('/api/auth/register',json={'name':name,'email':name+'@example.edu','password':'password123'})
    assert r.status_code==201,r.text
    d=r.json();return d['user'],{'Authorization':'Bearer '+d['token']}

def meeting(c,h):
    r=c.post('/api/meetings',headers=h,json={'title':'Retry demo','date':'2026-11-03'})
    assert r.status_code==201,r.text
    return r.json()['meeting']['id']

def invite(c,mid,h,target):
    r=c.post(f'/api/meetings/{mid}/invitations',headers=h,json={'user_ids':[target]})
    assert r.status_code==200,r.text

def input_body():return {'lat':47.5,'lon':6.8,'available_from':'09:00','available_until':'18:00','modes':['walk'],'max_walk_minutes':30}

def test_withdraw_pending_invite_then_reinvite_with_new_event(client):
    a,ah=user(client,'Alice');b,bh=user(client,'Bob');e,eh=user(client,'Eve');mid=meeting(client,ah)
    invite(client,mid,ah,b['id']);url=f'/api/meetings/{mid}/invitations/{b["id"]}/cancel'
    assert client.post(url).status_code==401
    assert client.post(url,headers=bh).status_code==403
    assert client.post(url,headers=eh).status_code==404
    old=client.get('/api/notifications',headers=bh).json()[0]
    r=client.post(url,headers=ah);assert r.status_code==200,r.text
    assert next(m for m in r.json()['members'] if m['user_id']==b['id'])['status']=='withdrawn'
    assert client.post(url,headers=ah).status_code==200
    assert client.post(f'/api/meetings/{mid}/respond',headers=bh,json={'accept':True}).status_code==409
    event=client.get('/api/notifications',headers=bh).json()[0]
    assert event['read_at'] and not event['actionable']
    invite(client,mid,ah,b['id'])
    events=client.get('/api/notifications',headers=bh).json()
    assert len(events)==2 and events[0]['id']!=old['id'] and not events[0]['read_at'] and events[0]['actionable']
    assert client.post(f'/api/meetings/{mid}/respond',headers=bh,json={'accept':True}).status_code==200
    assert client.post(url,headers=ah).status_code==409


def test_cancel_before_inviting_and_reopen_preserves_organiser_inputs(client):
    a,ah=user(client,'Alice');mid=meeting(client,ah)
    draft=meeting(client,ah)
    assert client.post(f'/api/meetings/{draft}/cancel',headers=ah).json()['meeting']['status']=='cancelled'
    assert client.put(f'/api/meetings/{mid}/inputs',headers=ah,json=input_body()).status_code==200
    # The action is also available immediately after creation, before any invite.
    r=client.post(f'/api/meetings/{mid}/cancel',headers=ah);assert r.status_code==200,r.text
    d=r.json();assert d['meeting']['status']=='cancelled' and d['proposals']==[] and d['approvals']==[]
    assert client.post(f'/api/meetings/{mid}/cancel',headers=ah).status_code==200
    assert client.put(f'/api/meetings/{mid}/inputs',headers=ah,json=input_body()).status_code==409
    assert client.post(f'/api/meetings/{mid}/invitations',headers=ah,json={'user_ids':[a['id']]}).status_code==409
    assert client.post(f'/api/meetings/{mid}/proposals',headers=ah).status_code==409
    r=client.post(f'/api/meetings/{mid}/reopen',headers=ah);assert r.status_code==200,r.text
    d=r.json();assert d['meeting']['status']=='waiting' and d['members'][0]['input']['lat']==47.5
    assert d['meeting']['selected_proposal_id'] is None and d['proposals']==[] and d['approvals']==[]
    assert client.post(f'/api/meetings/{mid}/reopen',headers=ah).status_code==409
    assert client.put(f'/api/meetings/{mid}/inputs',headers=ah,json=input_body()).status_code==200


def test_active_cancel_clears_locations_votes_and_withdraws_pending(client):
    a,ah=user(client,'Alice');b,bh=user(client,'Bob');p,ph=user(client,'Pending');mid=meeting(client,ah)
    invite(client,mid,ah,b['id']);invite(client,mid,ah,p['id'])
    assert client.post(f'/api/meetings/{mid}/respond',headers=bh,json={'accept':True}).status_code==200
    assert client.put(f'/api/meetings/{mid}/inputs',headers=ah,json=input_body()).status_code==200
    with connection() as db:
        db.execute("UPDATE meetings SET status='travelling',result=?,selected_proposal_id='p1' WHERE id=?",(json.dumps({'proposals':[{'id':'p1'}]}),mid))
        db.execute('INSERT INTO approvals VALUES (?,?,?,1)',(mid,'p1',a['id']))
        db.execute('INSERT INTO locations VALUES (?,?,?,?,?,?)',(mid,a['id'],47.5,6.8,5,'2026-11-03T10:00:00Z'))
    assert client.post(f'/api/meetings/{mid}/cancel',headers=bh).status_code==403
    r=client.post(f'/api/meetings/{mid}/cancel',headers=ah);assert r.status_code==200,r.text
    assert r.json()['meeting']['status']=='cancelled'
    assert client.get(f'/api/meetings/{mid}/locations',headers=ah).status_code==409
    assert client.post(f'/api/meetings/{mid}/respond',headers=ph,json={'accept':True}).status_code==409
    assert not client.get('/api/notifications',headers=ph).json()[0]['actionable']
    assert client.post(f'/api/meetings/{mid}/reopen',headers=bh).status_code==403
    r=client.post(f'/api/meetings/{mid}/reopen',headers=ah);assert r.status_code==200
    assert next(x for x in r.json()['members'] if x['user_id']==p['id'])['status']=='withdrawn'
    assert next(x for x in r.json()['members'] if x['user_id']==b['id'])['status']=='accepted'
    assert client.post(f'/api/meetings/{mid}/respond',headers=ph,json={'accept':True}).status_code==409
    assert client.post(f'/api/meetings/{mid}/decision',headers=ah,json={'proposal_id':'p1','accept':True}).status_code==409
    with connection() as db:
        assert db.execute('SELECT COUNT(*) FROM locations WHERE meeting_id=?',(mid,)).fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM approvals WHERE meeting_id=?',(mid,)).fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM notifications WHERE meeting_id=?',(mid,)).fetchone()[0]==2
        db.execute("UPDATE meetings SET status='completed' WHERE id=?",(mid,))
    assert client.post(f'/api/meetings/{mid}/cancel',headers=ah).status_code==409
    assert client.post(f'/api/meetings/{mid}/reopen',headers=ah).status_code==409


def test_late_plan_cannot_revive_cancelled_meeting(client,monkeypatch):
    a,ah=user(client,'Alice');mid=meeting(client,ah)
    assert client.put(f'/api/meetings/{mid}/inputs',headers=ah,json=input_body()).status_code==200
    def plan(*args):
        # A cancellation commits while a slow route calculation is outstanding.
        with connection() as db:db.execute("UPDATE meetings SET status='cancelled',result='{}' WHERE id=?",(mid,))
        return {'proposals':[{'id':'old'}]}
    monkeypatch.setitem(sys.modules,'app.planner',SimpleNamespace(plan_meeting=plan))
    assert client.post(f'/api/meetings/{mid}/proposals',headers=ah).status_code==409
    assert client.get(f'/api/meetings/{mid}',headers=ah).json()['meeting']['status']=='cancelled'


def test_late_plan_cannot_publish_old_starting_point(client,monkeypatch):
    a,ah=user(client,'Alice');mid=meeting(client,ah)
    assert client.put(f'/api/meetings/{mid}/inputs',headers=ah,json=input_body()).status_code==200
    changed={**input_body(),'lat':47.64,'lon':6.86}
    def plan(*args):
        with connection() as db:
            db.execute('UPDATE members SET input=? WHERE meeting_id=? AND user_id=?',(json.dumps(changed),mid,a['id']))
            db.execute("UPDATE meetings SET status='waiting',result='{}' WHERE id=?",(mid,))
        return {'proposals':[{'id':'stale-route'}]}
    monkeypatch.setitem(sys.modules,'app.planner',SimpleNamespace(plan_meeting=plan))
    r=client.post(f'/api/meetings/{mid}/proposals',headers=ah)
    assert r.status_code==409,r.text
    assert 'changed during calculation' in r.json()['detail']
    d=client.get(f'/api/meetings/{mid}',headers=ah).json()
    assert d['proposals']==[] and d['members'][0]['input']['lat']==47.64


def test_deleted_meeting_is_not_recreated_by_late_calculation(client,monkeypatch):
    a,ah=user(client,'Alice');mid=meeting(client,ah)
    assert client.put(f'/api/meetings/{mid}/inputs',headers=ah,json=input_body()).status_code==200
    def plan(*args):
        with connection() as db:
            db.execute('DELETE FROM members WHERE meeting_id=?',(mid,))
            db.execute('DELETE FROM meetings WHERE id=?',(mid,))
        return {'proposals':[{'id':'late'}]}
    monkeypatch.setitem(sys.modules,'app.planner',SimpleNamespace(plan_meeting=plan))
    assert client.post(f'/api/meetings/{mid}/proposals',headers=ah).status_code==409
    assert client.get(f'/api/meetings/{mid}',headers=ah).status_code==404
