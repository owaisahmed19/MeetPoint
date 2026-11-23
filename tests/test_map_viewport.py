"""Map refreshes preserve a user's view; origin markers use the displayed itinerary."""
from pathlib import Path
import subprocess, shutil
import pytest
ROOT=Path(__file__).resolve().parents[1]
@pytest.mark.skipif(not shutil.which('node'),reason='Node unavailable')
def test_map_refresh_and_explicit_reframe():
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync(process.argv[1],'utf8');
const segment=src.slice(src.indexOf('function plannedOrigin('),src.indexOf("$('complete').onclick"));
const els={},points=[];let fits=0;
const chain=()=>({addTo(){return this},remove(){},bindPopup(){return this},bindTooltip(){return this}});
const p={id:'p',venue:{name:'Library',lat:47.64,lon:6.86},itineraries:[{user_id:'prof',name:'Professor',legs:[{mode:'walk',geometry_kind:'approximate_straight_line',geometry:[[47.5,6.8],[47.64,6.86]],routing_endpoints:[[47.51,6.81],[47.64,6.86]]}]}]};
const S={map:{fitBounds(){fits++}},layers:[],current:{meeting:{id:'m1'},members:[{user_id:'prof',name:'Professor',input:{lat:47.63,lon:6.87}}]}};
const ctx={S,$:id=>els[id]||= {},chosen:()=>p,ensureMap:()=>true,tr:x=>x,ui:x=>x,esc:x=>String(x||''),color:()=> 'teal',modeLabel:x=>x,time:x=>x,routePopup:()=>'',geometryNote:()=>'',suppliedGeometry:()=>false,personMarker:(point)=>{points.push(point);return chain()},L:{layerGroup:chain,marker:chain,circleMarker:chain}};
vm.createContext(ctx);vm.runInContext(segment,ctx);
ctx.renderRoutes();assert.equal(fits,1);assert.equal(points[0][0],47.51);
ctx.renderRoutes();assert.equal(fits,1,'poll must not reset zoom');
p.id='p2';ctx.renderRoutes();assert.equal(fits,1,'server proposal update must preserve view');
els['show-all-routes'].onclick();assert.equal(fits,2);
S.current.meeting.id='m2';ctx.renderRoutes();assert.equal(fits,3,'new meeting fits initially');
assert.equal(ctx.plannedOrigin({legs:[]}),null);
console.log('viewport and route origin passed');
'''
    p=subprocess.run(['node','-e',script,str(ROOT/'app/static/app.js')],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
