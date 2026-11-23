"""Deferred HTTP responses must not hide fresh calculation results."""
from pathlib import Path
import shutil,subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]
@pytest.mark.skipif(not shutil.which('node'),reason='Node unavailable')
def test_poll_race_busy_result_error_and_navigation():
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync(process.argv[1],'utf8');
const els={};const el=id=>els[id]||={setAttribute(){},textContent:'',hidden:false};
const S={user:{id:'u'},current:{meeting:{id:'m'},proposals:[]}};
let pending=[],renders=0;
const ctx={S,$:el,api:(path)=>new Promise((resolve,reject)=>pending.push({path,resolve,reject})),ui:x=>x,tr:x=>x,Date,renderMeeting:()=>renders++,toast(){},setInterval:()=>1,clearInterval(){}};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('async function pollMeeting()'),src.indexOf('function clearPrivate()')),ctx);
vm.runInContext(src.slice(src.indexOf('function renderCalculationState()'),src.indexOf("$('compute').onclick=calculateMeeting")),ctx);
(async()=>{
 const oldPoll=ctx.pollMeeting();assert.equal(pending.length,1);
 const calc=ctx.calculateMeeting();assert(el('compute').disabled);assert(el('calculation-status').textContent.includes('Calculating'));
 await ctx.pollMeeting();assert.equal(pending.length,2,'no extra polling while calculating');
 pending[1].resolve({meeting:{id:'m'},proposals:[{id:'fresh'}]});await calc;
 pending[0].resolve({meeting:{id:'m'},proposals:[]});assert.equal(await oldPoll,false);
 assert.equal(S.current.proposals[0].id,'fresh');assert.equal(renders,1);assert(!el('compute').disabled);
 const failed=ctx.calculateMeeting();pending[2].reject(Error('Router unavailable'));await failed;
 assert(el('calculation-status').textContent.includes('Router unavailable'));assert(!el('calculation-status').hidden);
 const moved=ctx.calculateMeeting();S.current={meeting:{id:'different'}};
 pending[3].resolve({meeting:{id:'m'},proposals:[{id:'old-page'}]});await moved;
 assert.equal(S.current.meeting.id,'different','late response must not navigate back');
 console.log('calculation race and status passed');
})().catch(e=>{console.error(e);process.exit(1)});
'''
    p=subprocess.run(['node','-e',script,str(ROOT/'app/static/app.js')],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
