"""Locale selection and translations execute in Node without browser dependencies."""
import json
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'app/static/i18n.js'
NODE=shutil.which('node')

@pytest.mark.skipif(not NODE,reason='Node unavailable')
def test_locale_defaults_persistence_and_ui_only():
    js=r'''
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const code=fs.readFileSync(process.argv[1],'utf8');
function env(saved){
 const values=new Map(saved===undefined?[]:[['pc-language',saved]]);
 const html={lang:'fr'};
 const ctx={window:{},navigator:{language:'fr-FR'},document:{documentElement:html,title:'',querySelectorAll(){return []}},Node:{TEXT_NODE:3},localStorage:{getItem(k){return values.get(k)||null},setItem(k,v){values.set(k,v)}}};
 vm.runInNewContext(code,ctx);return {ui:ctx.window.PCi18n,values,html};
}
for(const saved of [undefined,'invalid','EN','ar']){
 const e=env(saved);assert.equal(e.ui.language,'en');assert.equal(e.ui.locale,'en-GB');assert.equal(e.html.lang,'en');assert.equal(e.ui.translate('Bon retour.'),'Welcome back.');
 assert.equal(e.ui.translate('Password? [unknown]'),'Password? [unknown]');
 assert.equal(e.ui.translate('Se connecter ↗'),'Sign in ↗');
}
const e=env('fr');assert.equal(e.ui.language,'fr');assert.equal(e.ui.locale,'fr-FR');assert.equal(e.ui.translate('Bon retour.'),'Bon retour.');
e.ui.setLanguage('en');assert.equal(e.values.get('pc-language'),'en');assert.equal(env(e.values.get('pc-language')).ui.language,'en');
// UI rendering leaves dynamic content untouched: no mutation observer or automatic
// text walker is installed. Source constants are the only translation call sites.
assert(!code.includes('MutationObserver'));
console.log('locale checks passed');
'''
    p=subprocess.run([NODE,'-e',js,str(SCRIPT)],capture_output=True,text=True)
    assert p.returncode==0,p.stderr


def test_html_has_english_default_and_language_controls():
    source=(ROOT/'app/static/index.html').read_text(encoding='utf-8')
    assert 'lang="en"' in source
    assert 'Welcome back.' in source and 'University email' in source
    assert source.count('data-language-selector="true"')==2
    assert source.index('/static/i18n.js')<source.index('/static/app.js')
    assert 'data-i18n-text="Bon retour."' in source
