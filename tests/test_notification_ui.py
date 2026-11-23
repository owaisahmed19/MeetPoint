"""Invitation inbox lifecycle and sound permission behavior without a browser."""
from pathlib import Path
import shutil,subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]
NODE=shutil.which('node')

@pytest.mark.skipif(not NODE,reason='Node unavailable')
def test_invitation_popup_inbox_sound_dedup_and_logout():
    js=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Element {
 constructor(){this.nodes=new Map();this.hidden=false;this.attrs={};this.textContent='';this.innerHTML='';this.children=[];this.removed=false;}
 querySelector(s){if(!this.nodes.has(s))this.nodes.set(s,new Element());return this.nodes.get(s);}
 querySelectorAll(s){return [];}
 append(e){this.children.push(e);}setAttribute(k,v){this.attrs[k]=v;}remove(){this.removed=true;}
 showModal(){this.open=true;}close(){this.open=false;}
}
const header=new Element(),body=new Element(),listeners=new Map();
const doc={hidden:false,body,createElement:()=>new Element(),querySelector:()=>header,addEventListener:(k,f)=>listeners.set(k,f),removeEventListener:k=>listeners.delete(k)};
const values=new Map(),storage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)};
let plays=0,paused=0,scheduled,opened=[],requests=[],rows=[];
class Audio {constructor(path){assert.equal(path,'/static/meetpoint-invite.wav');}async play(){plays++;}pause(){paused++;}}
const timers={setInterval:f=>{scheduled=f;return 1},clearInterval:()=>{scheduled=null}};
const ctx={window:{},console,Date,Set,JSON,String,encodeURIComponent};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const event=(id,extra={})=>({id,kind:'invitation',meeting_id:'meeting-'+id,meeting_title:'<img src=x onerror=bad()>',sender_name:'Ahmed',created_at:'2026-10-28T10:00:00Z',read_at:null,actionable:true,...extra});
const api=async(path,opt)=>{requests.push({path,opt});return path==='/notifications'?JSON.parse(JSON.stringify(rows)):{ok:true};};
const config={userId:'alice',api,openMeeting:async id=>opened.push(id),ui:en=>en,document:doc,storage,AudioClass:Audio,timers};
(async()=>{
 rows=[event('old')];let controller=ctx.window.MeetPointNotifications.create(config);await controller.start();
 const host=header.children.at(-1),popup=body.children.at(-1);
 assert.equal(popup.hidden,false);assert.equal(plays,0,'historical unread invitation must not chime');
 assert(popup.querySelector('.notification-popup-text').textContent.includes('<img'),'popup uses safe textContent');
 assert(host.querySelector('.notification-list').innerHTML.includes('&lt;img'));
 assert.equal(host.querySelector('.notification-count').textContent,'1');
 // Sound can only be armed by its explicit gesture control, and previews the chime.
 await popup.querySelector('.notification-popup-sound').onclick();assert.equal(plays,1);
 popup.querySelector('.notification-popup-close').onclick();assert.equal(popup.hidden,true);
 await scheduled();assert.equal(plays,1,'repeated polls must not chime again');assert.equal(popup.hidden,true);
 rows=[event('new'),event('old')];await scheduled();assert.equal(popup.hidden,false);assert.equal(plays,2);
 await scheduled();assert.equal(plays,2);assert.equal(host.querySelector('.notification-count').textContent,'2');
 await popup.querySelector('.notification-popup-open').onclick();assert.deepEqual(opened,['meeting-new']);
 assert(requests.some(r=>r.path==='/notifications/new/read'&&r.opt.method==='POST'));
 controller.destroy();assert(popup.removed&&host.removed);assert.equal(scheduled,null);assert(!listeners.has('visibilitychange'));
 // A reload for the same user neither repeats the popup nor chimes.
 controller=ctx.window.MeetPointNotifications.create(config);await controller.start();assert.equal(body.children.at(-1).hidden,true);assert.equal(plays,2);
 controller.destroy();
 // Another account keeps a separate notification history and muted-by-default setting.
 controller=ctx.window.MeetPointNotifications.create({...config,userId:'bob'});await controller.start();const bobPopup=body.children.at(-1);assert.equal(bobPopup.hidden,false);assert.equal(plays,2);
 assert(bobPopup.querySelector('.notification-popup-sound').textContent.includes('Enable'));
 controller.destroy();
 console.log('Popup, inbox, sound gesture, deduplication and logout checks passed');
})().catch(e=>{console.error(e);process.exit(1)});
'''
    r=subprocess.run([NODE,'-e',js,str(ROOT/'app/static/notifications.js')],capture_output=True,text=True)
    assert r.returncode==0,r.stderr


def test_notification_polling_is_global_and_assets_load_before_app():
    html=(ROOT/'app/static/index.html').read_text()
    app=(ROOT/'app/static/app.js').read_text()
    script=(ROOT/'app/static/notifications.js').read_text()
    assert html.index('/static/notifications.js')<html.index('/static/app.js')
    assert 'S.notifications = MeetPointNotifications.create' in app
    assert 'S.notifications?.destroy()' in app
    assert 'setInterval(refresh,4000)' in script
    assert "!$('home').hidden" not in script and 'meeting-page' not in script
    assert 'if(stopped||busy||doc.hidden)return' in script
    assert 'if(seeded&&fresh.some' in script
