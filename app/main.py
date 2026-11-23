"""Shared meeting API. Email ownership verification is not configured in this local prototype."""
from __future__ import annotations
import base64,binascii,csv,io,json,re,secrets,sqlite3,threading,time
from datetime import date as Date,datetime,timedelta,timezone
from pathlib import Path
from typing import Literal
from fastapi import FastAPI,Depends,HTTPException,Request
from fastapi.responses import FileResponse,Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,field_validator
from .storage import ROOT,connection,password_hash,check_password,token_hash
from .venues import Venue,catalogue,payload
app=FastAPI(title='MeetPoint / PointCommun — multimodal meetings',version='0.5.0')
DATA_DIR=ROOT/'data';ACTIVE=('confirmed','travelling')
_CALCULATING=set();_CALCULATING_LOCK=threading.Lock()
def now():return datetime.now(timezone.utc).isoformat()
def uid():return secrets.token_urlsafe(18)
def current_user(request:Request):
    a=request.headers.get('authorization','')
    if not a.startswith('Bearer ') or len(a)>256:raise HTTPException(401,'Authentication required')
    with connection() as db:r=db.execute('SELECT u.*,p.avatar FROM users u LEFT JOIN profiles p ON p.user_id=u.id JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires_at>?',(token_hash(a[7:]),now())).fetchone()
    if not r:raise HTTPException(401,'Invalid or expired session')
    return dict(r)
def public_user(u):return {k:u[k] for k in ['id','name','email']}|{'email_verified':False,'avatar':u.get('avatar')}
def session(db,u):
    if 'avatar' not in u:
        profile=db.execute('SELECT avatar FROM profiles WHERE user_id=?',(u['id'],)).fetchone()
        u={**u,'avatar':profile['avatar'] if profile else None}
    token=secrets.token_urlsafe(40);db.execute('INSERT INTO sessions VALUES (?,?,?)',(token_hash(token),u['id'],(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()))
    return {'token':token,'user':public_user(u)}
class Register(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    email:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=8,max_length=128)
    @field_validator('name')
    @classmethod
    def name_ok(cls,v):
        if not v.strip():raise ValueError('Name is required')
        return v.strip()
    @field_validator('email')
    @classmethod
    def email_ok(cls,v):
        v=v.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v):raise ValueError('Invalid email')
        return v
class Login(BaseModel):
    email:str=Field(max_length=254)
    password:str=Field(max_length=128)
class MeetingCreate(BaseModel):
    title:str=Field(min_length=1,max_length=160)
    date:Date
    duration_minutes:int=Field(default=30,ge=5,le=480)
    objective:Literal['earliest','min_total']='earliest'
    venue_ids:list[str]=Field(default_factory=list,max_length=100)
    @field_validator('title')
    @classmethod
    def title_ok(cls,v):
        if not v.strip():raise ValueError('Title is required')
        return v.strip()
class Invite(BaseModel):user_ids:list[str]=Field(min_length=1,max_length=30)
class Respond(BaseModel):accept:bool
class Input(BaseModel):
    lat:float=Field(ge=-90,le=90,allow_inf_nan=False)
    lon:float=Field(ge=-180,le=180,allow_inf_nan=False)
    available_from:str
    available_until:str
    modes:list[Literal['walk','transit','bus','train']]=Field(min_length=1,max_length=4)
    boarding_margin_minutes:float=Field(default=3,ge=0,le=60,allow_inf_nan=False)
    attendance_from:str|None=None
    attendance_until:str|None=None
    max_walk_minutes:float=Field(default=30,ge=0,le=240,allow_inf_nan=False)
    @field_validator('available_from','available_until','attendance_from','attendance_until')
    @classmethod
    def clock(cls,v):
        if v is None:return v
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',v):raise ValueError('Use HH:MM')
        return v
class Decision(Respond):proposal_id:str=Field(max_length=100)
class Message(BaseModel):
    text:str=Field(min_length=1,max_length=2000)
    @field_validator('text')
    @classmethod
    def clean(cls,v):
        if not v.strip():raise ValueError('Message is empty')
        return v.strip()
class Location(BaseModel):
    lat:float=Field(ge=-90,le=90,allow_inf_nan=False)
    lon:float=Field(ge=-180,le=180,allow_inf_nan=False)
    accuracy:float|None=Field(default=None,ge=0,allow_inf_nan=False)
def access(db,mid,u,accepted=True,owner=False):
    m=db.execute('SELECT * FROM meetings WHERE id=?',(mid,)).fetchone();member=db.execute('SELECT * FROM members WHERE meeting_id=? AND user_id=?',(mid,u['id'])).fetchone()
    if not m or not member:raise HTTPException(404,'Meeting not found')
    if owner and m['organiser_id']!=u['id']:raise HTTPException(403,'Organiser access required')
    if accepted and member['status']!='accepted':raise HTTPException(403,'Accept the invitation first')
    return dict(m),dict(member)
def editable(m):
    if m['status'] in ('travelling','completed','cancelled'):raise HTTPException(409,'Meeting is not editable; reopen a cancelled meeting before changing inputs')
def invalidate(db,mid):
    db.execute("UPDATE meetings SET status='waiting',result='{}',selected_proposal_id=NULL WHERE id=?",(mid,));db.execute('DELETE FROM approvals WHERE meeting_id=?',(mid,));db.execute('DELETE FROM locations WHERE meeting_id=?',(mid,));db.execute('DELETE FROM journey_states WHERE meeting_id=?',(mid,))
def live_access(db,mid,u):
    m,_=access(db,mid,u)
    if m['status'] not in ACTIVE:raise HTTPException(409,'Meeting must be confirmed and active')
    return m
def venues_list():return catalogue(DATA_DIR,include_inactive=False)
def venue_changed(vid):
    with connection() as db:
        for row in db.execute("SELECT id,venue_ids,result,status FROM meetings WHERE status NOT IN ('completed','cancelled')").fetchall():
            ids=json.loads(row['venue_ids'])
            if not ids or vid in ids:invalidate(db,row['id'])


def journey_schedule(meeting,result,members):
    proposal=next((p for p in result.get('proposals',[]) if p['id']==meeting.get('selected_proposal_id')),None)
    if not proposal:proposal=next(iter(result.get('proposals',[])),None)
    if not proposal:return []
    with connection() as db:
        states={r['user_id']:r['state'] for r in db.execute('SELECT * FROM journey_states WHERE meeting_id=?',(meeting['id'],))}
    confirmed=meeting['status'] in ACTIVE
    output=[]
    for it in proposal.get('itineraries',[]):
        departure=it.get('departure') or next(iter(it.get('legs',[])),{}).get('departure')
        state=states.get(it['user_id'],'scheduled' if confirmed else 'awaiting_confirmation')
        if confirmed and state=='scheduled' and departure and datetime.fromisoformat(departure)<=datetime.now(timezone.utc):
            state='ready_to_leave' if datetime.now(timezone.utc)<=datetime.fromisoformat(proposal.get('end',proposal['start'])) else 'departure_passed'
        output.append({'user_id':it['user_id'],'name':it.get('name'),'departure':departure,'arrival':it.get('arrival'),'meeting_start':proposal['start'],'state':state})
    return output

class JourneyState(BaseModel):
    state:Literal['travelling','arrived']

@app.post('/api/meetings/{mid}/journey-state')
def set_journey_state(mid:str,b:JourneyState,u=Depends(current_user)):
    with connection() as db:
        live_access(db,mid,u)
        db.execute('INSERT INTO journey_states VALUES (?,?,?,?) ON CONFLICT(meeting_id,user_id) DO UPDATE SET state=excluded.state,updated_at=excluded.updated_at',(mid,u['id'],b.state,now()))
        if b.state=='travelling':db.execute("UPDATE meetings SET status='travelling' WHERE id=?",(mid,))
    return details(mid,u)

class GraphInput(BaseModel):
    matrix:list[list[float|None]]=Field(min_length=1,max_length=80)

@app.post('/api/graph/closure')
def graph_closure(b:GraphInput,u=Depends(current_user)):
    from .graph import closure
    try:return closure(b.matrix)
    except ValueError as e:raise HTTPException(422,str(e))

@app.get('/api/indoor/{network_id}/route')
def indoor_navigation(network_id:str,origin:str,destination:str,u=Depends(current_user)):
    from .graph import indoor_route
    path=DATA_DIR/'indoor_networks.json'
    networks=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if network_id not in networks:raise HTTPException(404,'No verified indoor network supplied for this building')
    try:return indoor_route(networks[network_id],origin,destination)
    except ValueError as e:raise HTTPException(422,str(e))

@app.get('/api/health')
def health():return {'status':'ok','version':'0.5.0'}
@app.post('/api/auth/register',status_code=201)
def register(b:Register):
    u={'id':uid(),'name':b.name,'email':b.email}
    try:
        with connection() as db:
            db.execute('INSERT INTO users VALUES (?,?,?,?,?)',(u['id'],u['name'],u['email'],password_hash(b.password),now()));r=session(db,u)
        return r
    except sqlite3.IntegrityError:raise HTTPException(409,'Email already registered')
@app.post('/api/auth/login')
def login(b:Login):
    with connection() as db:
        u=db.execute('SELECT * FROM users WHERE email=?',(b.email.strip().lower(),)).fetchone()
        if not u or not check_password(b.password,u['password_hash']):raise HTTPException(401,'Incorrect email or password')
        return session(db,dict(u))
@app.post('/api/auth/logout')
def logout(request:Request,u=Depends(current_user)):
    with connection() as db:db.execute('DELETE FROM sessions WHERE token_hash=?',(token_hash(request.headers['authorization'][7:]),))
    return {'ok':True}
@app.get('/api/me')
def me(u=Depends(current_user)):return public_user(u)
class AvatarUpdate(BaseModel):
    avatar:str|None=Field(default=None,max_length=550000)
    @field_validator('avatar')
    @classmethod
    def raster(cls,value):
        if value is None:return None
        match=re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',value)
        if not match:raise ValueError('Choose a PNG, JPEG or WebP image')
        from PIL import Image,ImageOps
        try:
            raw=base64.b64decode(match[2],validate=True)
            if len(raw)>384*1024:raise ValueError('Photo must be at most 384 KB')
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {'PNG','JPEG','WEBP'}:raise ValueError('Unsupported image')
                if max(image.size)>4096 or min(image.size)<1:raise ValueError('Image dimensions must be between 1 and 4096 pixels')
                image.load()
                clean=ImageOps.exif_transpose(image).convert('RGBA');clean.thumbnail((256,256))
                out=io.BytesIO();clean.save(out,format='PNG')
                return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode('ascii')
        except (ValueError,binascii.Error,OSError,Image.DecompressionBombError) as exc:
            raise ValueError('Invalid or oversized photo') from exc
@app.put('/api/me/avatar')
@app.put('/api/profile/avatar',include_in_schema=False)
def set_avatar(b:AvatarUpdate,u=Depends(current_user)):
    with connection() as db:db.execute('INSERT INTO profiles(user_id,avatar) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET avatar=excluded.avatar',(u['id'],b.avatar))
    return public_user({**u,'avatar':b.avatar})
@app.get('/api/users')
def users(q:str='',u=Depends(current_user)):
    q=q.strip()[:100]
    if len(q)<2:return []
    q=q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
    with connection() as db:r=db.execute("SELECT u.id,u.name,p.avatar FROM users u LEFT JOIN profiles p ON p.user_id=u.id WHERE u.id<>? AND u.name LIKE ? ESCAPE '\\' ORDER BY name LIMIT 30",(u['id'],'%'+q+'%')).fetchall()
    return [{k:v for k,v in dict(x).items() if k!='avatar' or v is not None} for x in r]
@app.get('/api/venues')
def venues(u=Depends(current_user)):return catalogue(DATA_DIR,u['id'])
@app.post('/api/venues',status_code=201)
def add_venue(b:Venue,u=Depends(current_user)):
    vid='custom-'+uid();value=payload(b)
    if len(json.dumps(value))>50000:raise HTTPException(422,'Place record is too large')
    with connection() as db:db.execute('INSERT INTO venue_overrides VALUES (?,?,?,0,0)',(vid,u['id'],json.dumps(value)))
    venue_changed(vid)
    return {**value,'id':vid,'is_default':False,'owner_id':u['id'],'can_edit':True}
@app.put('/api/venues/{vid}')
def edit_venue(vid:str,b:Venue,u=Depends(current_user)):
    old=next((v for v in catalogue(DATA_DIR,u['id']) if v['id']==vid),None)
    if old is None:raise HTTPException(404,'Place not found')
    if not old['can_edit']:raise HTTPException(403,'Only the creator can edit this place')
    value={**old,**payload(b)}
    for key in ('id','is_default','owner_id','can_edit'):value.pop(key,None)
    if len(json.dumps(value))>50000:raise HTTPException(422,'Place record is too large')
    with connection() as db:db.execute('INSERT INTO venue_overrides VALUES (?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,deleted=0',(vid,old['owner_id'],json.dumps(value),int(old['is_default'])))
    venue_changed(vid)
    return {**value,'id':vid,'is_default':old['is_default'],'owner_id':old['owner_id'],'can_edit':True}
@app.delete('/api/venues/{vid}')
def delete_venue(vid:str,u=Depends(current_user)):
    old=next((v for v in catalogue(DATA_DIR,u['id']) if v['id']==vid),None)
    if old is None:raise HTTPException(404,'Place not found')
    if not old['can_edit']:raise HTTPException(403,'Only the creator can delete this place')
    with connection() as db:db.execute('INSERT INTO venue_overrides VALUES (?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET deleted=1',(vid,old['owner_id'],json.dumps(old),int(old['is_default'])))
    venue_changed(vid)
    return {'ok':True}
@app.get('/api/data-status')
def data_status(u=Depends(current_user)):
    p=DATA_DIR/'processed'/'manifest.json';d=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'status':'not_imported','feeds':[]}
    return {'transport':d,'venue_count':len(venues_list()),'email_verification':'not_configured_local_demo','live_transit':'not_integrated'}
@app.get('/api/meetings')
def meetings(u=Depends(current_user)):
    with connection() as db:r=db.execute('SELECT m.id,m.title,m.date,m.duration_minutes,m.objective,m.status,m.organiser_id,u.name AS organiser_name,b.status AS invitation_status FROM meetings m JOIN users u ON u.id=m.organiser_id JOIN members b ON b.meeting_id=m.id WHERE b.user_id=? ORDER BY m.created_at DESC',(u['id'],)).fetchall()
    return [dict(x) for x in r]
@app.get('/api/notifications')
def notifications(u=Depends(current_user)):
    with connection() as db:
        # Preserve invitations sent by an older install. Each pending member gets
        # one event only; later explicit reinvitations create their own events.
        pending=db.execute("SELECT m.id,m.organiser_id FROM meetings m JOIN members b ON b.meeting_id=m.id WHERE b.user_id=? AND b.status='invited' AND m.status NOT IN ('completed','cancelled') AND NOT EXISTS (SELECT 1 FROM notifications n WHERE n.user_id=b.user_id AND n.meeting_id=m.id AND n.kind='invitation')",(u['id'],)).fetchall()
        for m in pending:
            db.execute("INSERT INTO notifications SELECT ?,?,?,?,?,?,NULL WHERE NOT EXISTS (SELECT 1 FROM notifications WHERE user_id=? AND meeting_id=? AND kind='invitation')",(uid(),u['id'],m['organiser_id'],'invitation',m['id'],now(),u['id'],m['id']))
        rows=db.execute("SELECT n.id,n.kind,n.meeting_id,m.title AS meeting_title,s.name AS sender_name,n.created_at,n.read_at,b.status AS member_status,m.status AS meeting_status FROM notifications n JOIN meetings m ON m.id=n.meeting_id JOIN users s ON s.id=n.sender_id LEFT JOIN members b ON b.meeting_id=n.meeting_id AND b.user_id=n.user_id WHERE n.user_id=? ORDER BY n.created_at DESC,n.id DESC LIMIT 50",(u['id'],)).fetchall()
    return [{k:r[k] for k in ('id','kind','meeting_id','meeting_title','sender_name','created_at','read_at')} | {'actionable':r['member_status']=='invited' and r['meeting_status'] not in ('completed','cancelled','travelling')} for r in rows]
@app.post('/api/notifications/read-all')
def read_all_notifications(u=Depends(current_user)):
    with connection() as db:db.execute('UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL',(now(),u['id']))
    return {'ok':True}
@app.post('/api/notifications/{nid}/read')
def read_notification(nid:str,u=Depends(current_user)):
    with connection() as db:
        row=db.execute('SELECT 1 FROM notifications WHERE id=? AND user_id=?',(nid,u['id'])).fetchone()
        if not row:raise HTTPException(404,'Notification not found')
        db.execute('UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE id=? AND user_id=?',(now(),nid,u['id']))
    return {'ok':True}
@app.post('/api/meetings',status_code=201)
def create(b:MeetingCreate,u=Depends(current_user)):
    mid=uid()
    with connection() as db:
        db.execute('INSERT INTO meetings(id,organiser_id,title,date,duration_minutes,objective,venue_ids,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)',(mid,u['id'],b.title,b.date.isoformat(),b.duration_minutes,b.objective,json.dumps(b.venue_ids),'draft',now()));db.execute('INSERT INTO members VALUES (?,?,?,NULL)',(mid,u['id'],'accepted'))
    return details(mid,u)
@app.put('/api/meetings/{mid}')
def update_meeting(mid:str,b:MeetingCreate,u=Depends(current_user)):
    with connection() as db:
        access(db,mid,u,owner=True)
        db.execute('UPDATE meetings SET title=?,date=?,duration_minutes=?,objective=?,venue_ids=? WHERE id=?',(b.title,b.date.isoformat(),b.duration_minutes,b.objective,json.dumps(b.venue_ids),mid))
        invalidate(db,mid)
    return details(mid,u)
@app.delete('/api/meetings/{mid}',status_code=204)
def delete_meeting(mid:str,u=Depends(current_user)):
    with connection() as db:
        access(db,mid,u,owner=True)
        for table in ('notifications','messages','locations','approvals','members','journey_states'):
            db.execute(f'DELETE FROM {table} WHERE meeting_id=?',(mid,))
        db.execute('DELETE FROM meetings WHERE id=?',(mid,))
    return Response(status_code=204)
@app.get('/api/meetings/{mid}')
def details(mid:str,u=Depends(current_user)):
    with connection() as db:
        m,member=access(db,mid,u,accepted=False);rows=db.execute('SELECT b.*,u.name,p.avatar FROM members b JOIN users u ON u.id=b.user_id LEFT JOIN profiles p ON p.user_id=u.id WHERE b.meeting_id=?',(mid,)).fetchall();votes=db.execute('SELECT proposal_id,user_id,accepted FROM approvals WHERE meeting_id=?',(mid,)).fetchall()
    full=member['status']=='accepted';result=json.loads(m.pop('result')) if full else {};m['venue_ids']=json.loads(m['venue_ids'])
    return {'meeting':m,'members':[{'user_id':r['user_id'],'name':r['name'],'avatar':r['avatar'],'status':r['status'],'input':json.loads(r['input']) if r['input'] and full else None} for r in rows],'proposals':result.get('proposals',[]),'rejections':result.get('rejections',[]),'od_matrix':result.get('od_matrix',[]),'data_status':result.get('data_status',{}),'selection_evidence':result.get('selection_evidence',{}),'journey_schedule':journey_schedule(m,result,rows),'approvals':[dict(r) for r in votes] if full else []}
@app.post('/api/meetings/{mid}/invitations')
def invite(mid:str,b:Invite,u=Depends(current_user)):
    with connection() as db:
        m,_=access(db,mid,u,owner=True);editable(m);targets=set(b.user_ids)-{u['id']}
        for target in targets:
            if not db.execute('SELECT 1 FROM users WHERE id=?',(target,)).fetchone():raise HTTPException(422,'Unknown participant')
        changed=False
        for target in targets:
            old=db.execute('SELECT status FROM members WHERE meeting_id=? AND user_id=?',(mid,target)).fetchone()
            if old and old['status'] in ('accepted','invited'):continue
            db.execute("INSERT INTO members VALUES (?,?,'invited',NULL) ON CONFLICT(meeting_id,user_id) DO UPDATE SET status='invited',input=NULL",(mid,target));changed=True
            db.execute('INSERT INTO notifications VALUES (?,?,?,?,?,?,NULL)',(uid(),target,u['id'],'invitation',mid,now()))
        if changed:invalidate(db,mid)
    return details(mid,u)
@app.post('/api/meetings/{mid}/invitations/{target}/cancel')
def cancel_invitation(mid:str,target:str,u=Depends(current_user)):
    with connection() as db:
        m,_=access(db,mid,u,owner=True);editable(m)
        member=db.execute('SELECT status FROM members WHERE meeting_id=? AND user_id=?',(mid,target)).fetchone()
        if not member:raise HTTPException(404,'Invitation not found')
        if member['status'] not in ('invited','withdrawn'):raise HTTPException(409,'Only a pending invitation can be cancelled')
        if member['status']=='invited':
            db.execute("UPDATE members SET status='withdrawn',input=NULL WHERE meeting_id=? AND user_id=?",(mid,target));invalidate(db,mid)
        db.execute("UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE user_id=? AND meeting_id=? AND kind='invitation'",(now(),target,mid))
    return details(mid,u)
@app.post('/api/meetings/{mid}/cancel')
def cancel_meeting(mid:str,u=Depends(current_user)):
    with connection() as db:
        m,_=access(db,mid,u,owner=True)
        if m['status']=='completed':raise HTTPException(409,'A completed meeting cannot be cancelled')
        db.execute("UPDATE meetings SET status='cancelled',result='{}',selected_proposal_id=NULL WHERE id=?",(mid,));db.execute('DELETE FROM journey_states WHERE meeting_id=?',(mid,))
        db.execute("UPDATE members SET status='withdrawn',input=NULL WHERE meeting_id=? AND status='invited'",(mid,))
        db.execute('DELETE FROM approvals WHERE meeting_id=?',(mid,));db.execute('DELETE FROM locations WHERE meeting_id=?',(mid,))
        db.execute("UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE meeting_id=? AND kind='invitation'",(now(),mid))
    return details(mid,u)
@app.post('/api/meetings/{mid}/reopen')
def reopen_meeting(mid:str,u=Depends(current_user)):
    with connection() as db:
        m,_=access(db,mid,u,owner=True)
        if m['status']!='cancelled':raise HTTPException(409,'Only a cancelled meeting can be reopened')
        invalidate(db,mid)
    return details(mid,u)
@app.post('/api/meetings/{mid}/respond')
def respond(mid:str,b:Respond,u=Depends(current_user)):
    with connection() as db:
        m,member=access(db,mid,u,accepted=False);editable(m)
        if m['organiser_id']==u['id']:raise HTTPException(409,'Organiser already participates')
        if member['status']!='invited':raise HTTPException(409,'There is no pending invitation to answer')
        db.execute('UPDATE members SET status=?,input=NULL WHERE meeting_id=? AND user_id=?',('accepted' if b.accept else 'declined',mid,u['id']));invalidate(db,mid)
        db.execute("UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE user_id=? AND meeting_id=? AND kind='invitation'",(now(),u['id'],mid))
    return details(mid,u)
@app.put('/api/meetings/{mid}/inputs')
def inputs(mid:str,b:Input,u=Depends(current_user)):
    if b.available_until<=b.available_from:raise HTTPException(422,'End must be after start on the same day')
    if b.attendance_from and b.attendance_until and b.attendance_from>=b.attendance_until:raise HTTPException(422,'Attendance end must be after its start')
    with connection() as db:
        m,_=access(db,mid,u);editable(m);db.execute('UPDATE members SET input=? WHERE meeting_id=? AND user_id=?',(b.model_dump_json(),mid,u['id']));invalidate(db,mid)
    return details(mid,u)
@app.post('/api/meetings/{mid}/proposals')
def proposals(mid:str,refine:bool=False,u=Depends(current_user)):
    with _CALCULATING_LOCK:
        if mid in _CALCULATING:raise HTTPException(409,'A calculation is already running for this meeting')
        _CALCULATING.add(mid)
    try:return calculate_proposals(mid,u,refine)
    finally:
        with _CALCULATING_LOCK:_CALCULATING.discard(mid)

def calculate_proposals(mid,u,refine=False):
    with connection() as db:
        m,_=access(db,mid,u,owner=True);editable(m);rows=db.execute('SELECT b.*,u.name,p.avatar FROM members b JOIN users u ON u.id=b.user_id LEFT JOIN profiles p ON p.user_id=u.id WHERE b.meeting_id=?',(mid,)).fetchall()
        if any(r['status']=='invited' for r in rows):raise HTTPException(409,'Wait for invitations to be answered')
        accepted=[r for r in rows if r['status']=='accepted']
        if any(not r['input'] for r in accepted):raise HTTPException(409,'All accepted participants must provide inputs')
        people=[{'user_id':r['user_id'],'name':r['name'],**json.loads(r['input'])} for r in accepted];m['venue_ids']=json.loads(m['venue_ids'])
        from .planner import plan_meeting
        initial_venues=venues_list();m['fast_mode']=not refine
        started=time.perf_counter()
        try:result=plan_meeting(m,people,initial_venues,DATA_DIR)
        
        except (ValueError,FileNotFoundError) as e:raise HTTPException(422,str(e))
        result.setdefault('data_status',{})['calculation_ms']=round((time.perf_counter()-started)*1000,1)
        if initial_venues!=venues_list():raise HTTPException(409,'Meeting places changed during calculation. Calculate again.')
        for p in result.get('proposals',[]):p.setdefault('id',uid())
        # A cancellation may arrive while the expensive route calculation runs.
        latest=db.execute('SELECT * FROM meetings WHERE id=?',(mid,)).fetchone()
        if not latest:raise HTTPException(409,'Meeting was deleted during calculation')
        editable(dict(latest))
        # Never publish a route computed from inputs that changed during routing.
        current_rows=db.execute('SELECT user_id,status,input FROM members WHERE meeting_id=?',(mid,)).fetchall()
        snapshot=lambda records:sorted((r['user_id'],r['status'],r['input']) for r in records)
        if snapshot(current_rows)!=snapshot(rows) or any(latest[k]!=m[k] for k in ('title','date','duration_minutes','objective')) or json.loads(latest['venue_ids'])!=m['venue_ids']:
            raise HTTPException(409,'Journey details changed during calculation. Calculate again using the latest starting points.')
        db.execute('DELETE FROM journey_states WHERE meeting_id=?',(mid,))
        db.execute('DELETE FROM approvals WHERE meeting_id=?',(mid,));db.execute('UPDATE meetings SET result=?,status=?,selected_proposal_id=NULL WHERE id=?',(json.dumps(result),'proposal' if result.get('proposals') else 'no_feasible_meeting',mid))
    return details(mid,u)
@app.post('/api/meetings/{mid}/decision')
def decision(mid:str,b:Decision,u=Depends(current_user)):
    with connection() as db:
        m,_=access(db,mid,u)
        if m['status']!='proposal':raise HTTPException(409,'No pending proposal')
        if b.proposal_id not in {p['id'] for p in json.loads(m['result']).get('proposals',[])}:raise HTTPException(404,'Proposal not found')
        db.execute('INSERT INTO approvals VALUES (?,?,?,?) ON CONFLICT(meeting_id,proposal_id,user_id) DO UPDATE SET accepted=excluded.accepted',(mid,b.proposal_id,u['id'],int(b.accept)))
        n=db.execute("SELECT COUNT(*) FROM members WHERE meeting_id=? AND status='accepted'",(mid,)).fetchone()[0];votes=db.execute('SELECT COUNT(*) FROM approvals WHERE meeting_id=? AND proposal_id=? AND accepted=1',(mid,b.proposal_id)).fetchone()[0]
        if n==votes:db.execute("UPDATE meetings SET status='confirmed',selected_proposal_id=? WHERE id=?",(b.proposal_id,mid))
    return details(mid,u)
@app.get('/api/meetings/{mid}/chat')
def chat(mid:str,u=Depends(current_user)):
    with connection() as db:
        live_access(db,mid,u);r=db.execute('SELECT m.id,m.user_id,u.name,m.text,m.timestamp FROM messages m JOIN users u ON u.id=m.user_id WHERE m.meeting_id=? ORDER BY m.timestamp DESC LIMIT 300',(mid,)).fetchall()
    return [dict(x) for x in reversed(r)]
@app.post('/api/meetings/{mid}/chat',status_code=201)
def send_chat(mid:str,b:Message,u=Depends(current_user)):
    msg={'id':uid(),'user_id':u['id'],'name':u['name'],'text':b.text,'timestamp':now()}
    with connection() as db:live_access(db,mid,u);db.execute('INSERT INTO messages VALUES (?,?,?,?,?)',(msg['id'],mid,u['id'],b.text,msg['timestamp']))
    return msg
@app.put('/api/meetings/{mid}/location')
def location(mid:str,b:Location,u=Depends(current_user)):
    timestamp=now()
    with connection() as db:
        live_access(db,mid,u);db.execute("INSERT INTO journey_states VALUES (?,?,'travelling',?) ON CONFLICT(meeting_id,user_id) DO UPDATE SET state='travelling',updated_at=excluded.updated_at",(mid,u['id'],timestamp));db.execute('INSERT INTO locations VALUES (?,?,?,?,?,?) ON CONFLICT(meeting_id,user_id) DO UPDATE SET lat=excluded.lat,lon=excluded.lon,accuracy=excluded.accuracy,timestamp=excluded.timestamp',(mid,u['id'],b.lat,b.lon,b.accuracy,timestamp));db.execute("UPDATE meetings SET status='travelling' WHERE id=?",(mid,))
    return {'sharing':True,'timestamp':timestamp}
@app.get('/api/meetings/{mid}/locations')
def locations(mid:str,u=Depends(current_user)):
    with connection() as db:
        m=live_access(db,mid,u);db.execute('DELETE FROM locations WHERE meeting_id=? AND timestamp<?',(mid,(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()));r=db.execute('SELECT l.user_id,u.name,p.avatar,l.lat,l.lon,l.accuracy,l.timestamp FROM locations l JOIN users u ON u.id=l.user_id LEFT JOIN profiles p ON p.user_id=u.id WHERE l.meeting_id=?',(mid,)).fetchall()
    result=[dict(x) for x in r]
    try:
        from .progress import estimate_progress
        proposal=next((p for p in json.loads(m['result']).get('proposals',[]) if p['id']==m['selected_proposal_id']),None)
        if proposal:
            for x in result:
                it=next((i for i in proposal.get('itineraries',[]) if i['user_id']==x['user_id']),None);x['progress']=estimate_progress(x,it,proposal,m['date'])
    except ImportError:pass
    return result
@app.delete('/api/meetings/{mid}/location')
def stop_location(mid:str,u=Depends(current_user)):
    with connection() as db:access(db,mid,u);db.execute('DELETE FROM locations WHERE meeting_id=? AND user_id=?',(mid,u['id']))
    return {'sharing':False}
@app.post('/api/meetings/{mid}/complete')
def complete(mid:str,u=Depends(current_user)):
    with connection() as db:
        m,_=access(db,mid,u,owner=True)
        if m['status'] not in ACTIVE:raise HTTPException(409,'Only a confirmed active meeting can be completed')
        db.execute("UPDATE meetings SET status='completed' WHERE id=?",(mid,));db.execute('DELETE FROM locations WHERE meeting_id=?',(mid,))
    return details(mid,u)
@app.get('/api/meetings/{mid}/od-matrix.csv')
def od_csv(mid:str,u=Depends(current_user)):
    with connection() as db:m,_=access(db,mid,u)
    rows=json.loads(m['result']).get('od_matrix',[]);buff=io.StringIO();keys=list(dict.fromkeys(k for r in rows for k in r)) if rows else ['user_id','venue_id','duration_minutes','distance_m'];w=csv.DictWriter(buff,fieldnames=keys);w.writeheader()
    for r in rows:
        out={k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()};out={k:' '+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for k,v in out.items()};w.writerow(out)
    return Response(buff.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="od-matrix.csv"'})
@app.get('/')
def index():return FileResponse(ROOT/'app'/'static'/'index.html')
app.mount('/static',StaticFiles(directory=ROOT/'app'/'static'),name='static')
