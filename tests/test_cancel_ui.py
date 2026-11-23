"""User actions for withdrawing invitations, cancelling/reopening and declining."""
from pathlib import Path
import shutil,subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]
NODE=shutil.which('node')

@pytest.mark.skipif(not NODE,reason='Node unavailable')
def test_cancel_actions_and_terminal_invitation_controls():
    js=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
const elements={};const el=id=>elements[id] ||= {hidden:false,textContent:'',innerHTML:'',value:'',querySelectorAll:()=>[]};
let requests=[],confirmed=true,stops=0,clears=0,refreshes=0,renders=0;
const S={user:{id:'owner'},selected:'old',current:{meeting:{id:'m'},members:[]},notifications:{refresh:async()=>refreshes++}};
const ctx={S,$:el,ui:en=>en,tr:x=>x,confirm:()=>confirmed,encodeURIComponent,act:async(_,fn)=>fn(),api:async(path,opt)=>{requests.push({path,opt});return {meeting:{id:'m',status:path.endsWith('/cancel')?'cancelled':'waiting'},members:[]}},renderMeeting:()=>renders++,stopSharing:async()=>stops++,clearPrivate:()=>clears++,toast:()=>{}};
vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('async function cancelInvitation('),source.indexOf("$('accept').onclick")),ctx);
(async()=>{
 await ctx.cancelInvitation('target/user',{});assert.equal(requests.at(-1).path,'/meetings/m/invitations/target%2Fuser/cancel');assert.equal(requests.at(-1).opt.method,'POST');assert.equal(S.selected,null);assert.equal(el('search').value,'');
 const before=requests.length;confirmed=false;await ctx.cancelInvitation('target',{});assert.equal(requests.length,before);
 confirmed=true;await el('cancel-meeting').onclick();assert.equal(requests.at(-1).path,'/meetings/m/cancel');assert.equal(stops,1);assert.equal(clears,1);
 await el('reopen-meeting').onclick();assert.equal(requests.at(-1).path,'/meetings/m/reopen');assert.equal(stops,1);assert.equal(clears,2);assert.equal(refreshes,3);assert.equal(renders,3);
 // Meeting-level controls exist before the member-only area, including an empty draft.
 const html=fs.readFileSync(process.argv[2],'utf8');assert(html.indexOf('id="cancel-meeting"')<html.indexOf('id="member-area"'));
 let member={user_id:'owner',status:'accepted'};let own=true;
 Object.assign(ctx,{me:()=>member,owner:()=>own,statuses:{draft:'Draft',cancelled:'Cancelled'},day:()=>'',navigator:{userAgent:''},live:()=>false,esc:x=>String(x),avatarHtml:()=>'',color:()=>'',renderProposals:()=>{},renderPersonalSchedule:()=>{},renderRoutes:()=>{},renderCalculationState:()=>{},sharingButtons:()=>{}});
 S.current={meeting:{id:'m',title:'Test',status:'draft',organiser_id:'owner'},members:[member],proposals:[]};
 vm.runInContext(source.slice(source.indexOf('function renderMeeting('),source.indexOf('async function cancelInvitation(')),ctx);
 ctx.renderMeeting();assert.equal(el('cancel-meeting').hidden,false);assert.equal(el('reopen-meeting').hidden,true);
 S.current.meeting.status='cancelled';member={user_id:'guest',status:'invited'};own=false;
 ctx.renderMeeting();assert.equal(el('invitation').hidden,true);assert.equal(el('cancel-meeting').hidden,true);assert.equal(el('reopen-meeting').hidden,true);assert(el('meeting-access-note').textContent.includes('cancelled'));
 S.current.meeting.status='waiting';member.status='withdrawn';ctx.renderMeeting();assert(el('meeting-access-note').textContent.includes('withdrew'));assert.equal(el('member-area').hidden,true);
 console.log('Cancel/reopen and stale invitation controls passed');
})().catch(e=>{console.error(e);process.exit(1)});
'''
    r=subprocess.run([NODE,'-e',js,str(ROOT/'app/static/app.js'),str(ROOT/'app/static/index.html')],capture_output=True,text=True)
    assert r.returncode==0,r.stderr

@pytest.mark.skipif(not NODE,reason='Node unavailable')
def test_inline_notification_decline_requires_confirmation_and_clears_popup():
    js=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class E {constructor(){this.nodes=new Map();this.hidden=false;this.innerHTML='';this.textContent='';this.children=[];}querySelector(s){if(!this.nodes.has(s))this.nodes.set(s,new E());return this.nodes.get(s);}querySelectorAll(){return [];}append(x){this.children.push(x);}setAttribute(){}remove(){}close(){}showModal(){}}
const header=new E(),body=new E();const doc={hidden:false,body,createElement:()=>new E(),querySelector:()=>header,addEventListener(){},removeEventListener(){}};
const ctx={window:{},console,Date,Set,JSON,String,encodeURIComponent};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
let requests=[],confirm=false;let rows=[{id:'n',meeting_id:'m',sender_name:'Alice',meeting_title:'Test',created_at:'2026-10-28T10:00:00Z',actionable:true,read_at:null}];
const api=async(path,opt)=>{requests.push({path,opt});if(path==='/notifications')return JSON.parse(JSON.stringify(rows));if(path==='/meetings/m/respond'){rows[0].actionable=false;rows[0].read_at='now';}return {ok:true};};
const controller=ctx.window.MeetPointNotifications.create({userId:'u',api,openMeeting:async()=>{},ui:en=>en,document:doc,storage:{getItem:()=>null,setItem(){}},timers:{setInterval:()=>1,clearInterval(){}},confirmAction:()=>confirm});
(async()=>{
 await controller.start();const popup=body.children.at(-1),host=header.children.at(-1);
 assert(host.querySelector('.notification-list').innerHTML.includes('data-decline-notification="n"'));
 await popup.querySelector('.notification-popup-decline').onclick();assert(!requests.some(r=>r.path.endsWith('/respond')));assert.equal(popup.hidden,false);
 confirm=true;await popup.querySelector('.notification-popup-decline').onclick();
 const request=requests.find(r=>r.path.endsWith('/respond'));assert.equal(request.opt.method,'POST');assert.equal(request.opt.body.accept,false);assert.equal(popup.hidden,true);assert.equal(host.querySelector('.notification-count').textContent,'0');controller.destroy();
 console.log('Inline confirmed decline passed');
})().catch(e=>{console.error(e);process.exit(1)});
'''
    r=subprocess.run([NODE,'-e',js,str(ROOT/'app/static/notifications.js')],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
