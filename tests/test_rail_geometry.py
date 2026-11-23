import json
from app.rail_geometry import rail_shape

def source(tmp_path,status='EXPLOITE'):
    records=[{'mnemo':status,'code_ligne':'fixture','geo_shape':{'type':'Feature','geometry':{'type':'LineString','coordinates':[[6.8,47.5],[6.81,47.505],[6.82,47.5]]}}}]
    (tmp_path/'rail_geometry.json').write_text(json.dumps({'records':records}),encoding='utf-8')

def test_sourced_curved_geometry_and_reverse(tmp_path):
    source(tmp_path);a={'lat':47.5,'lon':6.8};b={'lat':47.5,'lon':6.82}
    f=rail_shape(a,b,tmp_path);r=rail_shape(b,a,tmp_path)
    assert f['geometry_kind']=='sncf_rail_corridor' and len(f['geometry'])==3
    assert f['geometry']==list(reversed(r['geometry']))
    assert f['rail_line_code']=='fixture' and 'not a certified' in f['geometry_note']

def test_no_invented_offnetwork_or_inactive_geometry(tmp_path):
    source(tmp_path);a={'lat':47.5,'lon':6.8};b={'lat':47.7,'lon':6.82}
    assert rail_shape(a,b,tmp_path) is None
    source(tmp_path,'FERME');assert rail_shape(a,{'lat':47.5,'lon':6.82},tmp_path) is None

def test_no_join_across_disconnected_corridors(tmp_path):
    records=[{'mnemo':'EXPLOITE','geo_shape':{'type':'MultiLineString','coordinates':[[[6.8,47.5],[6.801,47.5]],[[6.9,47.6],[6.901,47.6]]]}}]
    (tmp_path/'rail_geometry.json').write_text(json.dumps({'records':records}),encoding='utf-8')
    assert rail_shape({'lat':47.5,'lon':6.8},{'lat':47.6,'lon':6.9},tmp_path) is None

def test_connected_official_line_endpoints_can_form_corridor(tmp_path):
    records=[{'mnemo':'EXPLOITE','code_ligne':'A','geo_shape':{'type':'LineString','coordinates':[[6.8,47.5],[6.81,47.5]]}},
             {'mnemo':'EXPLOITE','code_ligne':'B','geo_shape':{'type':'LineString','coordinates':[[6.81,47.5],[6.81,47.51]]}}]
    (tmp_path/'rail_geometry.json').write_text(json.dumps({'records':records}),encoding='utf-8')
    r=rail_shape({'lat':47.5,'lon':6.8},{'lat':47.51,'lon':6.81},tmp_path)
    assert r and r['rail_line_code']=='A / B' and len(r['geometry'])>=3
    assert 'within 15m' in r['geometry_note']
