import base64,io,json
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app,venues_list
from app.storage import connection

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'meetings.sqlite3'))
    import app.main as api
    data=tmp_path/'data';data.mkdir()
    (data/'venues.json').write_text(json.dumps([{'id':'default-room','name':'Default room','lat':47.5,'lon':6.8,'permitted':True,'opening_hours':{'tue':[['09:00','18:00']]}}]))
    monkeypatch.setattr(api,'DATA_DIR',data)
    with TestClient(app) as c:yield c

def register(c,name):
    body=c.post('/api/auth/register',json={'name':name,'email':name+'@edu.umlp.fr','password':'password123'}).json()
    return body['user'],{'Authorization':'Bearer '+body['token']}

def place(**extra):
    return {'name':'Added room','lat':47.51,'lon':6.81,'city':'Montbéliard','permitted':True,'opening_hours':{'tue':[['09:00','18:00']]},**extra}

def test_venue_crud_persists_and_checks_creator(client):
    owner,headers=register(client,'Owner');other,oh=register(client,'Other')
    assert client.post('/api/venues',json=place()).status_code==401
    r=client.post('/api/venues',headers=headers,json=place());assert r.status_code==201,r.text
    venue=r.json();vid=venue['id'];assert venue['can_edit'] and not venue['is_default']
    assert next(v for v in client.get('/api/venues',headers=oh).json() if v['id']==vid)['can_edit'] is False
    assert client.put('/api/venues/'+vid,headers=oh,json=place(name='Other edit')).status_code==403
    assert client.delete('/api/venues/'+vid,headers=oh).status_code==403
    assert client.put('/api/venues/'+vid,headers=headers,json=place(name='Renamed',active=False)).status_code==200
    assert vid not in [v['id'] for v in venues_list()]
    assert next(v for v in client.get('/api/venues',headers=headers).json() if v['id']==vid)['name']=='Renamed'
    with connection() as db:assert json.loads(db.execute('SELECT payload FROM venue_overrides WHERE id=?',(vid,)).fetchone()[0])['name']=='Renamed'
    assert client.delete('/api/venues/'+vid,headers=headers).status_code==200
    assert vid not in [v['id'] for v in client.get('/api/venues',headers=headers).json()]

def test_default_edits_and_deletions_survive_json_reload(client):
    _,h=register(client,'Owner')
    assert client.put('/api/venues/default-room',headers=h,json=place(name='Campus room')).status_code==200
    assert client.get('/api/venues',headers=h).json()[0]['name']=='Campus room'
    assert client.delete('/api/venues/default-room',headers=h).status_code==200
    assert client.get('/api/venues',headers=h).json()==[]
    assert venues_list()==[]

def test_place_validation_rejects_invalid_hours_coordinates_and_url(client):
    _,h=register(client,'Owner')
    for extra in ({'lat':91},{'name':'  '},{'booking_url':'javascript:alert(1)'},{'opening_hours':{'tue':[['18:00','09:00']]}},{'opening_hours':{'tomorrow':[['09:00','18:00']]}}):
        assert client.post('/api/venues',headers=h,json=place(**extra)).status_code==422

def test_avatar_sanitised_and_visible_without_location_disclosure(client):
    owner,h=register(client,'Owner');_,oh=register(client,'Other')
    image=Image.new('RGB',(600,300),'teal');out=io.BytesIO();image.save(out,format='JPEG')
    avatar='data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode()
    response=client.put('/api/me/avatar',headers=h,json={'avatar':avatar});assert response.status_code==200,response.text
    saved=response.json()['avatar'];assert saved.startswith('data:image/png;base64,')
    with Image.open(io.BytesIO(base64.b64decode(saved.split(',')[1]))) as pic:assert pic.size==(256,128)
    assert client.get('/api/me',headers=h).json()['avatar']==saved
    assert client.post('/api/auth/login',json={'email':owner['email'],'password':'password123'}).json()['user']['avatar']==saved
    found=client.get('/api/users?q=Owner',headers=oh).json()[0]
    assert found=={'id':owner['id'],'name':'Owner','avatar':saved}
    mid=client.post('/api/meetings',headers=h,json={'title':'Photo test','date':'2026-11-03'}).json()['meeting']['id']
    assert client.get('/api/meetings/'+mid,headers=h).json()['members'][0]['avatar']==saved
    assert client.put('/api/me/avatar',headers=h,json={'avatar':None}).json()['avatar'] is None

def test_avatar_rejects_svg_bad_image_and_oversized_payload(client):
    _,h=register(client,'Owner')
    assert client.put('/api/me/avatar',json={'avatar':None}).status_code==401
    for avatar in ('data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,YmFk', 'data:image/png;base64,'+base64.b64encode(b'x'*(385*1024)).decode()):
        assert client.put('/api/me/avatar',headers=h,json={'avatar':avatar}).status_code==422
