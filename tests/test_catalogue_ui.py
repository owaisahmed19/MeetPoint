"""Execute catalogue and photo UI behavior with lightweight DOM/map doubles."""
from pathlib import Path
import shutil,subprocess
import pytest
NODE=shutil.which('node');ROOT=Path(__file__).resolve().parents[1]
@pytest.mark.skipif(not NODE, reason='Node unavailable')
def test_photos_preferences_catalogue_submission_and_pin():
    js=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
const elements={};function el(id){return elements[id] ||= {value:'',checked:false,textContent:'',innerHTML:'',querySelectorAll:()=>[],close(){this.closed=true}};}
const ctx={console,ui:(en,fr)=>en,Number,Error,String,Set,PCi18n:{language:'en'},S:{user:{id:'u'},current:null},$:el,esc:x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),initials:x=>String(x||'?')[0].toUpperCase(),tr:x=>x,color:()=> '#19675e',L:{marker:(point,opts)=>({point,opts})}};
vm.createContext(ctx);
const photo=source.slice(source.indexOf('function safeAvatar('),source.indexOf('const catalogueLabels='));
// preferredVenueIds and photo functions have no DOM initialization side effects.
vm.runInContext(photo,ctx);
assert.equal(ctx.safeAvatar('javascript:alert(1)'),'');
assert.equal(ctx.safeAvatar('data:image/svg+xml;base64,PHN2Zz4='),'');
assert.equal(ctx.avatarHtml({name:'<Ahmed>'}),'&lt;');
assert(ctx.avatarHtml({name:'Ahmed',avatar:'data:image/png;base64,YQ=='}).includes('<img'));
assert.equal(ctx.avatarHtml({name:'Ahmed',avatar:'data:image/png;base64,YQ==" onerror="alert(1)'}),'A');
const venues=[{id:'ok',category:'meeting_room',quiet:null,discussion_allowed:true,permitted:true},{id:'cowork',category:'coworking',quiet:null,discussion_allowed:true,permitted:true},{id:'quiet-cafe',category:'cafe',quiet:true,discussion_allowed:true,permitted:true},{id:'quiet-reading',quiet:true,discussion_allowed:false,permitted:true},{id:'unknown',quiet:null,discussion_allowed:true,permitted:true},{id:'private',quiet:true,discussion_allowed:true,permitted:false},{id:'inactive',quiet:true,discussion_allowed:true,permitted:true,active:false}];
assert.deepEqual(Array.from(ctx.preferredVenueIds('work',venues)),['ok','cowork','quiet-cafe']);
assert.deepEqual(Array.from(ctx.preferredVenueIds('all',venues)),[]);
assert.throws(()=>ctx.preferredVenueIds('work',[]),/No permitted work/);
ctx.S.current={members:[{user_id:'u',name:'Ahmed',avatar:'data:image/png;base64,YQ=='}]};ctx.L.divIcon=x=>x;
const marker=ctx.personMarker([47,6],{user_id:'u',name:'Ahmed'});assert(marker.opts.icon.html.includes('<img'));assert.equal(marker.opts.icon.iconAnchor[0],21);
// Venue-pin dragging fills coordinates automatically.
let drag,point={lat:47.6,lng:6.9};ctx.venueMap={};ctx.venuePin=null;
ctx.L.marker=(coords,opts)=>({addTo(){assert.equal(opts.draggable,true);return this},on(event,fn){drag=fn;return this},getLatLng(){return point}});
vm.runInContext(source.slice(source.indexOf('function placeVenuePin('),source.indexOf('function openVenue(')),ctx);
ctx.placeVenuePin(47.5,6.8);assert.equal(el('venue-lat').value,'47.500000');drag();assert.equal(el('venue-lon').value,'6.900000');
// Full save handler persists catalogue data, including split opening intervals.
let posted,refreshed=false;ctx.editingVenue=null;ctx.act=(_,fn)=>fn();ctx.api=async(path,opts)=>{posted={path,...opts}};ctx.reloadVenues=async()=>{refreshed=true};ctx.toast=()=>{};
for(const [id,value] of Object.entries({'venue-name':'Campus room','venue-city':'Montbéliard','venue-address':'Building C','venue-type':'meeting_room','venue-capacity':'6','venue-quiet-value':'true','venue-notes':'Confirm room booking','venue-link':'https://example.org'}))el(id).value=value;
el('venue-discussion').checked=true;el('venue-permitted').checked=true;el('venue-booking').checked=true;
const interval=(from,to)=>({querySelectorAll:()=>[{value:from},{value:to}]});
let intervals=[interval('08:00','12:00'),interval('14:00','18:00')];ctx.document={querySelectorAll:()=>[{dataset:{day:'mon'},querySelectorAll:()=>intervals}]};
vm.runInContext(source.slice(source.indexOf("$('venue-form').onsubmit="),source.indexOf("$('avatar').onclick=")),ctx);
(async()=>{
 await el('venue-form').onsubmit({preventDefault(){},submitter:{}});
 assert.equal(posted.path,'/venues');assert.equal(posted.method,'POST');assert.equal(posted.body.name,'Campus room');assert.equal(posted.body.quiet,true);assert.equal(posted.body.capacity,6);assert.equal(posted.body.lat,47.6);assert.equal(posted.body.opening_hours.mon.length,2);assert(refreshed);assert(el('venue-dialog').closed);
 intervals=[interval('18:00','08:00')];await assert.rejects(()=>el('venue-form').onsubmit({preventDefault(){},submitter:{}}),/start before/);
 el('venue-lat').value='';await assert.rejects(()=>el('venue-form').onsubmit({preventDefault(){},submitter:{}}),/Choose the place/);
 console.log('Catalogue submission, pin, preference and photo behavior passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    p=subprocess.run([NODE,'-e',js,str(ROOT/'app/static/app.js')],text=True,capture_output=True)
    assert p.returncode==0,p.stderr

@pytest.mark.skipif(not NODE,reason='Node unavailable')
def test_brand_switches_and_exclusions_are_expanded():
    js=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');const code=fs.readFileSync(process.argv[1],'utf8');
for(const language of ['en','fr']){
 const name={},mark={},doc={documentElement:{},title:'',querySelectorAll:q=>q==='[data-brand-name]'?[name]:q==='[data-brand-mark]'?[mark]:[]};
 const ctx={window:{},document:doc,Node:{TEXT_NODE:3},localStorage:{getItem:()=>language}};
 vm.runInNewContext(code,ctx);assert.equal(name.textContent,language==='fr'?'PointCommun':'MeetPoint');assert.equal(mark.textContent,language==='fr'?'PC':'MP');assert(doc.title.startsWith(name.textContent));
}
const source=fs.readFileSync(process.argv[2],'utf8');const els={};const el=id=>els[id] ||= {innerHTML:'',querySelectorAll:()=>[]};
const S={current:{proposals:[],meeting:{status:'no_feasible_meeting'},rejections:[{venue_name:'Room <C>',reason:'Closed <today>'}]}};
const ctx={S,$:el,tr:x=>x,ui:(en,fr)=>en,esc:x=>String(x).replace(/</g,'&lt;').replace(/>/g,'&gt;')};
vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function renderProposals()'),source.indexOf('function suppliedGeometry(')),ctx);ctx.renderProposals();
assert.equal(el('rejections').open,true);assert.equal(el('rejections').hidden,false);assert(el('proposals').innerHTML.includes('No place currently fits'));assert(el('rejection-list').innerHTML.includes('Room &lt;C&gt;'));assert(!el('rejection-list').innerHTML.includes('Closed <today>'));
S.current.data_status={planning_incomplete:true};ctx.renderProposals();assert(el('proposals').innerHTML.includes('Search incomplete'));assert(!el('proposals').innerHTML.includes('No place currently fits'));
S.current.rejections=[];ctx.renderProposals();assert(el('proposals').innerHTML.includes('does not prove'));
'''
    p=subprocess.run([NODE,'-e',js,str(ROOT/'app/static/i18n.js'),str(ROOT/'app/static/app.js')],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
