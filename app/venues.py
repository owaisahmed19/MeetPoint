"""Default venue catalogue with persistent, authenticated local-demo overrides."""
from __future__ import annotations
import json,re
from pathlib import Path
from pydantic import BaseModel,Field,ConfigDict,field_validator
from .storage import connection

class Venue(BaseModel):
    model_config=ConfigDict(extra='allow')
    name:str=Field(min_length=1,max_length=180)
    city:str=Field(default='',max_length=100)
    address:str=Field(default='',max_length=300)
    lat:float=Field(ge=-90,le=90,allow_inf_nan=False)
    lon:float=Field(ge=-180,le=180,allow_inf_nan=False)
    capacity:int|None=Field(default=None,ge=1,le=100000)
    min_group_size:int=Field(default=1,ge=1,le=100000)
    opening_hours:dict[str,list[tuple[str,str]]]=Field(default_factory=dict)
    opening_exceptions:dict[str,list[tuple[str,str]]]=Field(default_factory=dict)
    category:str=Field(default='meeting_room',max_length=80)
    quiet:bool|None=None
    quiet_level:str=Field(default='unknown',max_length=40)
    discussion_allowed:bool|None=None
    permitted:bool=False
    active:bool=True
    availability_status:str=Field(default='unconfirmed',max_length=80)
    booking_required:bool=False
    booking_url:str=Field(default='',max_length=2000)
    source_url:str=Field(default='',max_length=2000)
    notes:str=Field(default='',max_length=4000)
    building:str=Field(default='',max_length=180)
    floor:str=Field(default='',max_length=80)
    room:str=Field(default='',max_length=100)
    cost_note:str=Field(default='',max_length=500)
    @field_validator('name')
    @classmethod
    def nonempty(cls,v):
        if not v.strip():raise ValueError('Place name is required')
        return v.strip()
    @field_validator('booking_url','source_url')
    @classmethod
    def safe_url(cls,v):
        if v and not re.match(r'^https?://[^\s]+$',v,re.I):raise ValueError('Booking URL must use http or https')
        return v
    @field_validator('opening_hours','opening_exceptions')
    @classmethod
    def hours(cls,v,info):
        for key,intervals in v.items():
            if info.field_name=='opening_hours' and key not in {'mon','tue','wed','thu','fri','sat','sun'}:raise ValueError('Unknown weekday')
            if info.field_name=='opening_exceptions':
                from datetime import date
                date.fromisoformat(key)
            for a,b in intervals:
                if not all(re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',x) for x in (a,b)) or b<=a:raise ValueError('Opening intervals need HH:MM and an end after start')
        return v

def defaults(data_dir):
    p=Path(data_dir)/'venues.json'
    if not p.exists():return []
    data=json.loads(p.read_text(encoding='utf-8'))
    return data if isinstance(data,list) else data.get('venues',[])

def catalogue(data_dir,user_id=None,include_inactive=True):
    records={v['id']:{**v,'is_default':True,'owner_id':None} for v in defaults(data_dir)}
    with connection() as db:rows=db.execute('SELECT * FROM venue_overrides').fetchall()
    for r in rows:
        if r['deleted']:records.pop(r['id'],None);continue
        records[r['id']]={**json.loads(r['payload']),'id':r['id'],'is_default':bool(r['is_default']),'owner_id':r['owner_id']}
    result=[]
    for v in records.values():
        if not include_inactive and not v.get('active',True):continue
        if 'quiet' not in v:v['quiet']={'quiet':True,'moderate':False,'unknown':None}.get(v.get('quiet_level'))
        v['can_edit']=bool(user_id and (v['is_default'] or v['owner_id']==user_id))
        result.append(v)
    return result

def payload(body):
    value=body.model_dump(mode='json')
    for key in ('id','is_default','owner_id','can_edit','deleted'):value.pop(key,None)
    return value
