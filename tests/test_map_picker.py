"""Behaviour of draggable origin selection without a browser or map provider."""
from pathlib import Path
import shutil,subprocess
import pytest
NODE=shutil.which('node');ROOT=Path(__file__).resolve().parents[1]
@pytest.mark.skipif(not NODE,reason='Node is unavailable')
def test_drag_updates_origin_and_respects_locked_journey():
 js=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
const segment=source.slice(source.indexOf('function originEditable()'),source.indexOf('function openCreate()'));
const els={lat:{value:''},lon:{value:''},'pin-status':{},'choose-map':{},'route-map':{scrollIntoView(){}}};
let marker,drag,options;let point={lat:47.51,lng:6.81};
const S={current:{meeting:{status:'waiting'}},map:{panTo(){},getCenter(){return {lat:47.5,lng:6.8}},invalidateSize(){}}};
const ctx={S,$:id=>els[id],tr:x=>x,me:()=>({status:'accepted'}),ensureMap:()=>true,act:(_,f)=>f(),setTimeout:f=>f(),Number,
 L:{marker:(coords,opt)=>{options=opt;marker={bindPopup(){return this},addTo(){return this},on(_,f){drag=f;return this},getLatLng(){return point},remove(){},openPopup(){}};return marker}}};
vm.createContext(ctx);vm.runInContext(segment,ctx);ctx.markDraft(47.5,6.8);
assert.equal(options.draggable,true);assert.equal(els.lat.value,'47.500000');
drag();assert.equal(els.lat.value,'47.510000');assert.equal(els.lon.value,'6.810000');
S.current.meeting.status='completed';point={lat:48,lng:7};drag();assert.equal(els.lat.value,'47.510000');
console.log('drag origin behaviour passed');
'''
 p=subprocess.run([NODE,'-e',js,str(ROOT/'app/static/app.js')],text=True,capture_output=True)
 assert p.returncode==0,p.stderr
