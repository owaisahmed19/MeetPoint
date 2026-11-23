/* Foreground invitation inbox. This does not claim background push delivery. */
'use strict';
window.MeetPointNotifications = (() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function create({userId,api,openMeeting,ui,locale='en-GB',document:doc=document,storage=localStorage,AudioClass=window.Audio,timers=window,confirmAction=message=>window.confirm(message)}) {
    const key='mp-notifications-seen:'+userId, soundKey='mp-invitation-sound:'+userId;
    const readStored=(k,fallback)=>{try{return JSON.parse(storage.getItem(k))??fallback;}catch{return fallback;}};
    const storedSeen=readStored(key,[]);
    let seen=new Set(Array.isArray(storedSeen)?storedSeen:[]), sound=readStored(soundKey,false)===true;
    let records=[],queued=[],current=null,seeded=false,stopped=false,busy=false,timer=null;
    let audio=null;
    const host=doc.createElement('div');host.className='notification-center';
    host.innerHTML=`<button type="button" class="secondary notification-bell" aria-expanded="false"><span aria-hidden="true">🔔</span> ${ui('Notifications','Notifications')} <b class="notification-count" hidden>0</b></button><dialog class="notification-dialog"><div class="panel-title"><h2>${ui('Your invitations','Vos invitations')}</h2><button type="button" class="text-button notification-inbox-close" aria-label="${ui('Close','Fermer')}">×</button></div><p class="fine">${ui('Pop-up alerts work while the app is open.','Les alertes apparaissent lorsque l’application est ouverte.')}</p><div class="notification-sound-controls"><button type="button" class="secondary notification-sound"></button><button type="button" class="text-button notification-test">${ui('Test sound','Tester le son')}</button></div><p class="fine notification-sound-status" role="status"></p><button type="button" class="text-button notification-read-all">${ui('Mark all as read','Tout marquer comme lu')}</button><div class="notification-list"></div></dialog>`;
    const popup=doc.createElement('section');popup.className='invitation-popup';popup.hidden=true;popup.setAttribute('role','alert');popup.setAttribute('aria-live','assertive');
    popup.innerHTML=`<div class="panel-title"><strong>✦ ${ui('Meeting invitation','Invitation à une rencontre')}</strong><button type="button" class="text-button notification-popup-close" aria-label="${ui('Dismiss alert','Fermer l’alerte')}">×</button></div><p class="notification-popup-text"></p><div class="buttons"><button type="button" class="primary notification-popup-open">${ui('View invitation','Voir l’invitation')} ↗</button><button type="button" class="secondary notification-popup-decline">${ui('Decline','Refuser')}</button><button type="button" class="secondary notification-popup-sound"></button></div><p class="fine notification-popup-status" role="status"></p>`;
    const find=selector=>host.querySelector(selector), pop=selector=>popup.querySelector(selector);
    const bell=find('.notification-bell'),inbox=find('dialog'),badge=find('.notification-count');
    doc.querySelector('header').append(host);doc.body.append(popup);
    function store(k,value){try{storage.setItem(k,JSON.stringify(value));}catch{}}
    function remember(rows){for(const n of rows)seen.add(n.id);seen=new Set([...seen].slice(-200));store(key,[...seen]);}
    function soundLabel(){return sound?ui('Mute invitation sound','Couper le son des invitations'):ui('Enable invitation sound','Activer le son des invitations');}
    function soundButtons(){find('.notification-sound').textContent=soundLabel();pop('.notification-popup-sound').textContent=soundLabel();find('.notification-sound').setAttribute('aria-pressed',String(sound));pop('.notification-popup-sound').setAttribute('aria-pressed',String(sound));}
    function soundStatus(text){find('.notification-sound-status').textContent=text;pop('.notification-popup-status').textContent=text;}
    function getAudio(){if(!audio&&AudioClass){audio=new AudioClass('/static/meetpoint-invite.wav');audio.preload='auto';audio.volume=.65;}return audio;}
    async function playTone(){
      if(stopped)return false;
      try{const a=getAudio();if(!a)throw Error('Audio unavailable');a.currentTime=0;await a.play();if(!stopped)soundStatus(ui('MeetPoint invitation chime.','Son d’invitation PointCommun.'));return true;}
      catch{if(!stopped)soundStatus(ui('Sound was blocked. Tap Test sound and check your media volume.','Son bloqué. Touchez Tester le son et vérifiez le volume multimédia.'));return false;}
    }
    async function toggleSound(){sound=!sound;store(soundKey,sound);soundButtons();if(sound)await playTone();else {audio?.pause();soundStatus(ui('Invitation sound muted.','Son des invitations coupé.'));}}
    function message(n){return ui(`${n.sender_name} invited you to “${n.meeting_title}”.`,`${n.sender_name} vous invite à « ${n.meeting_title} ».`);}
    function nextPopup(){
      if(stopped||current)return;
      current=queued.shift();if(!current){popup.hidden=true;return;}
      pop('.notification-popup-text').textContent=message(current);popup.hidden=false;soundButtons();
    }
    function dismiss(){current=null;popup.hidden=true;nextPopup();}
    function showNew(rows){for(const n of rows)if(n.actionable&&!n.read_at)queued.push(n);nextPopup();}
    function render(){
      const unread=records.filter(n=>!n.read_at&&n.actionable).length;
      badge.textContent=String(unread);badge.hidden=!unread;
      bell.setAttribute('aria-label',ui(`Notifications: ${unread} unread invitations`,`Notifications : ${unread} invitations non lues`));
      find('.notification-list').innerHTML=records.length?records.map(n=>`<article class="notification-item ${!n.read_at&&n.actionable?'unread':''}"><p>${escape(message(n))}</p><small>${escape(new Date(n.created_at).toLocaleString(locale))}</small><button type="button" class="${n.actionable?'primary':'secondary'}" data-notification-id="${escape(n.id)}">${n.actionable?ui('View invitation','Voir l’invitation'):ui('View meeting','Voir la rencontre')} ↗</button>${n.actionable?`<button type="button" class="text-button" data-decline-notification="${escape(n.id)}">${ui('Decline','Refuser')}</button>`:''}${!n.actionable?`<p class="fine">${ui('This invitation has already been answered or is no longer active.','Cette invitation a déjà reçu une réponse ou n’est plus active.')}</p>`:''}</article>`).join(''):`<p class="muted">${ui('No invitations yet.','Aucune invitation pour le moment.')}</p>`;
      find('.notification-list').querySelectorAll('[data-notification-id]').forEach(button=>button.onclick=()=>view(button.dataset.notificationId));
      find('.notification-list').querySelectorAll('[data-decline-notification]').forEach(button=>button.onclick=()=>decline(button.dataset.declineNotification,button));
      queued=queued.filter(n=>records.some(r=>r.id===n.id&&r.actionable&&!r.read_at));
      if(current&&!records.some(n=>n.id===current.id&&n.actionable&&!n.read_at))dismiss();
    }
    async function view(id){
      const n=records.find(n=>n.id===id);if(!n||stopped)return;
      try{await api('/notifications/'+encodeURIComponent(id)+'/read',{method:'POST'});if(stopped)return;n.read_at=new Date().toISOString();queued=queued.filter(r=>r.id!==id);if(current?.id===id)dismiss();render();inbox.close();bell.setAttribute('aria-expanded','false');await openMeeting(n.meeting_id);}
      catch(error){if(!stopped)soundStatus(error.message);}
    }
    async function decline(id,button){
      const n=records.find(n=>n.id===id);if(!n||!n.actionable||stopped)return;
      if(!confirmAction(ui('Decline this invitation? The organiser can invite you again.','Refuser cette invitation ? L’organisateur pourra vous inviter de nouveau.')))return;
      if(button)button.disabled=true;
      try{
        await api('/meetings/'+encodeURIComponent(n.meeting_id)+'/respond',{method:'POST',body:{accept:false}});
        if(stopped)return;n.actionable=false;n.read_at=new Date().toISOString();
        queued=queued.filter(r=>r.id!==id);render();await refresh();
        soundStatus(ui('Invitation declined.','Invitation refusée.'));
      }catch(error){if(!stopped)soundStatus(error.message);}
      finally{if(button)button.disabled=false;}
    }
    async function refresh(){
      if(stopped||busy||doc.hidden)return;
      busy=true;
      try{
        const fetched=await api('/notifications');if(stopped)return;
        const rows=Array.isArray(fetched)?fetched:[];
        const fresh=rows.filter(n=>!seen.has(n.id));records=rows;
        remember(rows);render();showNew(fresh);
        // Existing invitations surface on first sync silently. Only later events chime.
        if(seeded&&fresh.some(n=>!n.read_at&&n.actionable)&&sound)await playTone();
        seeded=true;
      }catch(error){if(!stopped)console.warn('Invitation refresh unavailable',error.message);}
      finally{busy=false;}
    }
    bell.onclick=()=>{render();if(inbox.showModal)inbox.showModal();else inbox.setAttribute('open','');bell.setAttribute('aria-expanded','true');refresh();};
    find('.notification-inbox-close').onclick=()=>{inbox.close();bell.setAttribute('aria-expanded','false');};
    find('.notification-sound').onclick=toggleSound;pop('.notification-popup-sound').onclick=toggleSound;
    find('.notification-test').onclick=()=>{sound=true;store(soundKey,true);soundButtons();return playTone();};
    find('.notification-read-all').onclick=async()=>{try{await api('/notifications/read-all',{method:'POST'});if(stopped)return;queued=[];current=null;popup.hidden=true;records.forEach(n=>n.read_at=new Date().toISOString());render();}catch(error){if(!stopped)soundStatus(error.message);}};
    pop('.notification-popup-close').onclick=dismiss;
    pop('.notification-popup-open').onclick=()=>current&&view(current.id);
    pop('.notification-popup-decline').onclick=()=>current&&decline(current.id,pop('.notification-popup-decline'));
    const visibility=()=>{if(!doc.hidden)refresh();};doc.addEventListener('visibilitychange',visibility);
    soundButtons();
    return {
      async start(){await refresh();if(!stopped)timer=timers.setInterval(refresh,4000);},refresh,
      destroy(){stopped=true;timers.clearInterval(timer);audio?.pause();doc.removeEventListener('visibilitychange',visibility);queued=[];records=[];current=null;host.remove();popup.remove();}
    };
  }
  return {create};
})();
