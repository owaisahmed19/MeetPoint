'use strict';
const tr = PCi18n.translate;
const ui = (en, fr) => PCi18n.language === 'fr' ? fr : en;

const $ = id => document.getElementById(id),
  colors = ['#19675e', '#bd8336', '#6658a5', '#3474a9', '#b5596b', '#71833f'];
const S = {
  token: localStorage.getItem('pc-token'),
  user: null,
  meetings: [],
  venues: [],
  current: null,
  selected: null,
  map: null,
  overview: null,
  layers: [],
  positions: null,
  watch: null,
  sharing: null,
  poll: null,
  auth: 'login',
  searchTimer: null
};
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
})[c]);
const statuses = {
  draft: tr("À organiser"),
  waiting: tr("En attente"),
  proposal: tr("Propositions prêtes"),
  confirmed: tr("Confirmée"),
  travelling: tr("En route"),
  completed: tr("Terminée"),
  cancelled: tr("Annulée"),
  no_feasible_meeting: tr("Aucun lieu possible")
};
const time = x => {
  if (!x) return '—';
  if (/^\d\d:\d\d$/.test(x)) return x;
  const d = new Date(x);
  return isNaN(d) ? x : d.toLocaleTimeString(PCi18n.locale, {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/Paris'
  });
};
const day = x => x ? new Date(x + 'T12:00:00').toLocaleDateString(PCi18n.locale, {
  weekday: 'short',
  day: 'numeric',
  month: 'short'
}) : '';
const initials = x => String(x || '?').trim().split(/\s+/).slice(0, 2).map(x => x[0]).join('').toUpperCase();
const live = () => ['confirmed', 'travelling'].includes(S.current?.meeting?.status),
  owner = () => S.current?.meeting?.organiser_id === S.user?.id;
const me = () => S.current?.members?.find(x => x.user_id === S.user?.id);
const chosen = () => S.current?.proposals?.find(p => p.id === (S.current.meeting.selected_proposal_id || S.selected));
function modeLabel(mode) { return mode === 'walk' ? tr('Marche') : mode === 'train' ? 'Train' : mode === 'bus' ? 'Bus' : mode; }
function color(id) {
  const p = chosen();
  const rows = p?.itineraries || S.current?.members || [];
  const i = rows.findIndex(x => x.user_id === id);
  return colors[Math.max(0, i) % colors.length];
}
function toast(message, bad = false) {
  $('toast').textContent = message;
  $('toast').className = 'visible' + (bad ? ' bad' : '');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => $('toast').className = '', 5500);
}
async function api(path, opt = {}) {
  const r = await fetch('/api' + path, {
    ...opt,
    headers: {
      ...(S.token ? {
        Authorization: 'Bearer ' + S.token
      } : {}),
      ...(opt.body ? {
        'Content-Type': 'application/json'
      } : {}),
      ...opt.headers
    },
    body: opt.body ? JSON.stringify(opt.body) : undefined
  });
  if (!r.ok) {
    let detail;
    try {
      const e = await r.json();
      detail = typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail);
    } catch {}
    if (r.status === 401 && S.user) {
      await logout(false);
      throw Error(tr("Session expirée. Reconnectez-vous."));
    }
    throw Error(detail || tr("Erreur ") + r.status);
  }
  return r.status === 204 ? null : r.json();
}
async function act(button, fn) {
  if (button) button.disabled = true;
  try {
    return await fn();
  } catch (e) {
    toast(e.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}
function authMode(mode) {
  S.auth = mode;
  $('login-tab').classList.toggle('active', mode === 'login');
  $('register-tab').classList.toggle('active', mode === 'register');
  $('name-label').hidden = mode === 'login';
  $('auth-name').required = mode === 'register';
  $('auth-password').autocomplete = mode === 'register' ? 'new-password' : 'current-password';
  $('auth-title').textContent = mode === 'register' ? tr("Votre prochain point commun.") : tr("Bon retour.");
  $('auth-submit').textContent = mode === 'register' ? tr("Créer mon compte ↗") : tr("Se connecter ↗");
  $('auth-error').textContent = '';
}
$('login-tab').onclick = () => authMode('login');
$('register-tab').onclick = () => authMode('register');
$('auth-form').onsubmit = async e => {
  e.preventDefault();
  $('auth-submit').disabled = true;
  $('auth-error').textContent = '';
  try {
    const r = await api('/auth/' + S.auth, {
      method: 'POST',
      body: {
        email: $('auth-email').value.trim(),
        password: $('auth-password').value,
        ...(S.auth === 'register' ? {
          name: $('auth-name').value.trim()
        } : {})
      }
    });
    S.token = r.token;
    S.user = r.user;
    localStorage.setItem('pc-token', r.token);
    $('auth-password').value = '';
    await enter();
  } catch (e) {
    $('auth-error').textContent = e.message;
  } finally {
    $('auth-submit').disabled = false;
  }
};
async function enter() {
  S.user = S.user || (await api('/me'));
  $('auth').hidden = true;
  $('app').hidden = false;
  $('profile-name').textContent = S.user.name;
  renderProfilePhoto();
  S.notifications?.destroy();
  S.notifications = MeetPointNotifications.create({userId:S.user.id,api,openMeeting,ui,locale:PCi18n.locale});
  S.notifications.start();
  await home();
  const restoreJson = sessionStorage.getItem('pc-language-restore');
  sessionStorage.removeItem('pc-language-restore');
  if (restoreJson) {
    try {
      const restore = JSON.parse(restoreJson);
      if (restore.userId === S.user.id && restore.meetingId) {
        await openMeeting(restore.meetingId);
        if (!S.current.meeting.selected_proposal_id && S.current.proposals.some(p => p.id === restore.selected)) {
          S.selected = restore.selected; renderProposals(); renderRoutes();
        }
        if (restore.inputs && me()?.status === 'accepted') {
          for (const id of ['lat','lon','from','until','boarding-margin','attendance-from','attendance-until']) $(id).value = restore.inputs[id];
          $('walk').checked = restore.inputs.walk; $('transit').checked = restore.inputs.transit;
        }
      }
    } catch (error) { console.warn('Could not restore meeting view', error); }
  }
  clearInterval(S.poll);
  S.poll = setInterval(async () => {
    if (document.hidden || !S.user) return;
    try {
      if (S.current && !$('meeting-page').hidden) {
        const updated=await pollMeeting();
        if (!updated) return;
        if (live()) await refreshLive();else if (S.watch !== null) await stopSharing();
      } else if (!$('home').hidden) await loadMeetings();
    } catch (e) {
      console.warn('Refresh unavailable', e.message);
    }
  }, 6000);
}
async function pollMeeting() {
  const id=S.current?.meeting.id, epoch=S.detailEpoch || 0;
  if (!id || S.calculating?.id===id) return false;
  const d=await api('/meetings/'+id);
  if(S.current?.meeting.id!==id || (S.detailEpoch || 0)!==epoch || S.calculating?.id===id)return false;
  S.current=d;renderMeeting(false);return true;
}
function clearPrivate() {
  S.draft?.remove();
  S.draft = null;
  S.mapViewportMeeting = null;
  for (const layer of S.layers) layer?.remove();
  S.layers = [];
  S.positions?.remove();
  S.positions = null;
  $('messages').innerHTML = '';
  $('positions').innerHTML = '';
  $('routes').innerHTML = '';
  $('chat-text').value = '';
  $('search').value = '';
  $('search-results').innerHTML = '';
}
async function logout(remote = true) {
  await stopSharing();
  if (remote) try {
    await api('/auth/logout', {
      method: 'POST'
    });
  } catch {}
  clearInterval(S.poll);
  S.notifications?.destroy();
  S.notifications = null;
  clearPrivate();
  S.token = null;
  S.user = null;
  S.current = null;
  S.selected = null;
  S.venues = [];
  S.meetings = [];
  localStorage.removeItem('pc-token');
  $('app').hidden = true;
  $('auth').hidden = false;
  $('meeting-list').innerHTML = '';
  $('venues-list').innerHTML = '';
}
$('logout').onclick = () => act($('logout'), () => logout());
function screen(name) {
  for (const [id, n] of [['home', 'home'], ['venues-page', 'venues'], ['meeting-page', 'meeting']]) $(id).hidden = name !== n;
  $('nav-home').classList.toggle('active', name !== 'venues');
  $('nav-venues').classList.toggle('active', name === 'venues');
  $('breadcrumb').textContent = tr("Votre espace / ") + {
    home: tr("Rencontres"),
    venues: tr("Les lieux"),
    meeting: tr("Votre rencontre")
  }[name];
  setTimeout(() => {
    S.map?.invalidateSize();
    S.overview?.invalidateSize();
  }, 60);
}
async function leave() {
  await stopSharing();
  clearPrivate();
  S.current = null;
  S.selected = null;
}
async function home() {
  await leave();
  screen('home');
  const [, venues, status] = await Promise.all([loadMeetings(), api('/venues'), api('/data-status')]);
  S.venues = Array.isArray(venues) ? venues : venues.venues || [];
  renderStatus(status);
  overviewMap();
}
$('nav-home').onclick = () => act($('nav-home'), home);
$('back').onclick = () => act($('back'), home);
$('nav-venues').onclick = () => act($('nav-venues'), async () => {
  await leave();
  S.venues = await api('/venues');
  screen('venues');
  renderVenues();
});
$('refresh').onclick = () => act($('refresh'), async () => S.current ? openMeeting(S.current.meeting.id) : !$('venues-page').hidden ? reloadVenues() : home());
function renderStatus(d) {
  const feeds = d.transport?.feeds || d.feeds || [];
  const loaded = Array.isArray(feeds) && feeds.length > 0;
  $('data-banner').classList.toggle('warning', !loaded);
  $('data-banner').textContent = loaded ? tr("✓ Données de transport importées : les services sont vérifiés pour la date du trajet. Les retards réels des véhicules ne sont pas intégrés.") : tr("◷ Données GTFS non importées : aucun trajet en bus ou train ne peut encore être calculé. La marche reste estimative.");
}
async function loadMeetings() {
  const r = await api('/meetings');
  S.meetings = Array.isArray(r) ? r : r.meetings || [];
  const list = $('meeting-list');
  if (!S.meetings.length) {
    list.innerHTML = tr("<div class=\"empty\"><h3>Votre prochain rendez-vous commence ici.</h3><p>Créez une rencontre, puis invitez votre groupe par son nom.</p><button id=\"first-create\" class=\"primary\">＋ Créer une rencontre</button></div>");
    $('first-create').onclick = openCreate;
    return;
  }
  list.innerHTML = S.meetings.map(m => `<button class="meeting-card" data-id="${esc(m.id)}"><span class="status ${esc(m.status)} ${m.invitation_status === 'invited' ? 'invited' : ''}">${esc(m.status==='cancelled' ? statuses.cancelled : m.invitation_status === 'invited' ? tr("Invitation reçue") : m.invitation_status==='withdrawn' ? ui('Invitation withdrawn','Invitation retirée') : m.invitation_status==='declined' ? tr('Invitation refusée') : statuses[m.status] || m.status)}</span><h3>${esc(m.title)}</h3><p>${esc(day(m.date))} · ${esc(m.duration_minutes || '—')} min</p><p>${m.objective === 'min_total' ? tr("Trajets cumulés minimisés") : tr("Se retrouver au plus tôt")}</p><span class="arrow">↗</span></button>`).join('');
  list.querySelectorAll('[data-id]').forEach(b => b.onclick = () => act(b, () => openMeeting(b.dataset.id)));
}
function safeUrl(x) {
  try {
    const u = new URL(x);
    return ['https:', 'http:'].includes(u.protocol) ? u.href : '';
  } catch {
    return '';
  }
}
function renderVenues() {
  const category = $('venue-category').value;
  const categoryKeys = [...new Set([...venueCategories, ...S.venues.map(v=>v.category).filter(Boolean)])];
  $('venue-category').innerHTML = `<option value="">${ui('All categories','Toutes les catégories')}</option>` + categoryKeys.map(k=>`<option value="${esc(k)}">${esc(categoryLabel(k))}</option>`).join('');
  $('venue-category').value = category;
  const q = $('venue-search').value.trim().toLocaleLowerCase();
  const rows = S.venues.filter(v => (!q || [v.name,v.city,v.address].join(' ').toLocaleLowerCase().includes(q)) && (!$('venue-category').value || v.category === $('venue-category').value) && (!$('venue-quiet').checked || v.quiet === true));
  $('venue-count').textContent = `${rows.length} / ${S.venues.length} ` + ui('places · opening hours and room availability are separate.','lieux · horaires et disponibilité des salles sont distincts.');
  $('venues-list').innerHTML = rows.map(v => `<article class="panel"><span class="eyebrow">${esc(v.city || tr("LIEU CANDIDAT"))}</span><h2 style="margin-top:12px">${esc(v.name)}</h2><p class="muted">${esc(v.address || '')}</p><div class="venue-tags"><span class="mini">${esc(categoryLabel(v.category))}</span>${v.quiet === true ? `<span class="mini">${ui('Quiet','Calme')}</span>` : ''}${v.discussion_allowed ? `<span class="mini">${ui('Discussion','Discussion')}</span>` : ''}</div><p>${v.capacity ? tr("Jusqu’à ") + esc(v.capacity) + tr(" personnes") : tr("Capacité exacte à confirmer")}</p><p class="notice ${v.permitted !== true ? 'warning' : ''}">${v.permitted !== true ? ui('Use permission needs confirmation.','Autorisation d’utilisation à confirmer.') : v.availability_status === 'confirmed' ? tr("Disponibilité indiquée dans les données.") : tr("Disponibilité et réservation à confirmer auprès du lieu.")}</p><p class="fine">${esc(v.opening_hours_note || tr("Vérifier les horaires et les conditions d’accès à la date choisie."))}</p>${!Object.values(v.opening_hours || {}).some(x=>x.length) ? `<p class="fine">${ui('Opening hours unknown: not eligible for automatic proposals yet.','Horaires inconnus : exclu des propositions automatiques pour le moment.')}</p>` : ''}${safeUrl(v.booking_url || v.source_url) ? `<a href="${esc(safeUrl(v.booking_url || v.source_url))}" target="_blank" rel="noopener">${tr("Consulter le lieu / la réservation ↗")}</a>` : ''}${v.can_edit ? `<div class="buttons venue-actions"><button class="secondary" data-edit-venue="${esc(v.id)}">${ui('Edit','Modifier')}</button><button class="text-button" data-delete-venue="${esc(v.id)}">${ui('Delete','Supprimer')}</button></div>` : ''}</article>`).join('') || `<p class="muted">${ui('No places match these filters.','Aucun lieu ne correspond aux filtres.')}</p>`;
  $('venues-list').querySelectorAll('[data-edit-venue]').forEach(b=>b.onclick=()=>openVenue(S.venues.find(v=>v.id===b.dataset.editVenue)));
  $('venues-list').querySelectorAll('[data-delete-venue]').forEach(b=>b.onclick=()=>act(b,async()=>{
    if(!confirm(ui('Delete this place from the catalogue?','Supprimer ce lieu du catalogue ?')))return;
    await api('/venues/'+encodeURIComponent(b.dataset.deleteVenue),{method:'DELETE'}); await reloadVenues();
  }));
}

function tile(map) {
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · <a href="https://routing.openstreetmap.de/about.html">FOSSGIS routing</a> · <a href="https://www.openstreetmap.org">Fix the map</a>',
    maxZoom: 19
  }).addTo(map);
}
function overviewMap() {
  if (!window.L) return;
  try {
    if (!S.overview) {
      $('overview-map').innerHTML = '';
      S.overview = L.map('overview-map').setView([47.56, 6.83], 11);
      tile(S.overview);
    }
    if (S.overviewLayer) S.overviewLayer.remove();
    S.overviewLayer = L.layerGroup().addTo(S.overview);
    for (const v of S.venues) if (Number.isFinite(v.lat) && Number.isFinite(v.lon)) L.circleMarker([v.lat, v.lon], {
      radius: 7,
      color: '#19675e',
      fillOpacity: .8
    }).bindPopup(esc(v.name)).addTo(S.overviewLayer);
    S.overview.invalidateSize();
  } catch (e) {
    console.warn('Map unavailable', e);
  }
}
function ensureMap() {
  if (!window.L) return false;
  try {
    if (!S.map) {
      $('route-map').innerHTML = '';
      S.map = L.map('route-map').setView([47.56, 6.83], 11);
      tile(S.map);
      S.map.on('click', e => {
        if (!me() || me().status !== 'accepted' || ['travelling', 'completed', 'cancelled'].includes(S.current?.meeting.status)) return;
        $('lat').value = e.latlng.lat.toFixed(6);
        $('lon').value = e.latlng.lng.toFixed(6);
        markDraft(e.latlng.lat, e.latlng.lng);
      });
    }
    return true;
  } catch {
    return false;
  }
}
function originEditable() {
  return me()?.status === 'accepted' && !['travelling','completed','cancelled'].includes(S.current?.meeting.status);
}
function writeOrigin(lat,lon) {
  $('lat').value = Number(lat).toFixed(6);
  $('lon').value = Number(lon).toFixed(6);
  $('pin-status').textContent = tr("Point choisi. Déplacez le repère pour ajuster, puis enregistrez votre trajet.");
}
function markDraft(lat, lon) {
  S.draft?.remove();
  writeOrigin(lat,lon);
  if (ensureMap()) {
    S.draft = L.marker([lat,lon], {draggable:true, title:tr("Déplacez votre point de départ"), autoPan:true}).bindPopup(tr("Déplacez ce repère, puis enregistrez votre trajet.")).addTo(S.map);
    S.draft.on('dragend',()=>{
      if(!originEditable())return;
      const point=S.draft.getLatLng();writeOrigin(point.lat,point.lng);
    });
    S.map.panTo([lat,lon]);
  }
}
$('choose-map').onclick = ()=>act($('choose-map'),async()=>{
  if(!originEditable())return;
  if(!ensureMap())throw Error(tr("Carte indisponible. Utilisez votre position ou les coordonnées avancées."));
  const lat=$('lat').value,lon=$('lon').value;
  const current=S.map.getCenter();
  const point=lat!==''&&lon!==''?[Number(lat),Number(lon)]:[current.lat,current.lng];
  markDraft(point[0],point[1]);
  $('route-map').scrollIntoView({behavior:'smooth',block:'center'});
  setTimeout(()=>{S.map.invalidateSize();S.draft?.openPopup();},150);
});
function setMeetingFormLabels(editing) {
  $('create-form').querySelector('h2').textContent=editing ? ui('Edit meeting','Modifier la rencontre') : ui('A new meeting','Une nouvelle rencontre');
  $('create-form').querySelector('button.primary').textContent=editing ? ui('Save changes','Enregistrer les modifications') : ui('Create meeting ↗','Créer la rencontre ↗');
}
function openCreate() {
  S.editingMeeting=null;
  $('meeting-place-preference').disabled=false;
  $('create-form').reset();
  setMeetingFormLabels(false);
  const date = new Date().toLocaleDateString('en-CA', {
    timeZone: 'Europe/Paris'
  });
  $('date').value = date;
  $('create-dialog').showModal();
}
$('create-open').onclick = openCreate;
$('create-close').onclick = () => $('create-dialog').close();
$('create-form').onsubmit = e => {
  e.preventDefault();
  act(e.submitter, async () => {
    const editing=S.editingMeeting;
    if(editing && !confirm(ui('Update this meeting? Existing proposals, approvals and shared positions will be cleared. Participants and journey inputs will be kept.','Modifier cette rencontre ? Les propositions, accords et positions partagées seront effacés. Les participants et leurs trajets seront conservés.')))return;
    const venue_ids = editing ? S.current.meeting.venue_ids : preferredVenueIds($('meeting-place-preference').value, S.venues);
    S.detailEpoch=(S.detailEpoch || 0)+1;
    const d = await api(editing ? '/meetings/'+editing : '/meetings', {
      method: editing ? 'PUT' : 'POST',
      body: {
        title: $('title').value.trim(),
        date: $('date').value,
        duration_minutes: Number($('duration').value),
        objective: $('objective').value,
        venue_ids
      }
    });
    $('create-dialog').close();
    S.editingMeeting=null;
    $('create-form').reset();
    await openMeeting(d.meeting?.id || d.id);
    if(editing)toast(ui('Meeting updated. Journey inputs were kept; calculate new proposals.','Rencontre modifiée. Les trajets sont conservés ; recalculez les propositions.'));
  });
};
async function openMeeting(id) {
  const epoch=S.detailEpoch=(S.detailEpoch || 0)+1;
  await stopSharing();
  clearPrivate();
  const d=await api('/meetings/' + id);
  if(S.detailEpoch!==epoch)return;
  S.current=d;
  S.selected = S.current.meeting.selected_proposal_id || S.current.proposals?.[0]?.id || null;
  screen('meeting');
  renderMeeting(true);
  if (live()) await refreshLive();
}
function renderMeeting(fill = false) {
  const m = S.current.meeting,
    mem = me(),
    accepted = mem?.status === 'accepted';
  $('meeting-title').textContent = m.title;
  $('meeting-status').className = 'status ' + m.status;
  $('meeting-status').textContent = m.status === 'no_feasible_meeting' && S.current.data_status?.planning_incomplete ? ui('Search incomplete','Recherche incomplète') : statuses[m.status] || m.status;
  $('meeting-meta').textContent = `${day(m.date)} · ${m.duration_minutes} minutes · ${m.objective === 'min_total' ? tr("Trajets cumulés minimisés") : tr("Se retrouver au plus tôt")}`;
  const terminal = ['cancelled','completed'].includes(m.status);
  $('invitation').hidden = mem?.status !== 'invited' || terminal;
  $('cancel-meeting').textContent=ui('Cancel meeting','Annuler la rencontre');
  $('reopen-meeting').textContent=ui('Reopen meeting','Rouvrir la rencontre');
  $('cancel-meeting').hidden=!owner() || terminal;
  $('reopen-meeting').hidden=!owner() || m.status!=='cancelled';
  $('meeting-access-note').hidden=accepted && m.status!=='cancelled' || (!terminal && !['withdrawn','declined'].includes(mem?.status));
  $('meeting-access-note').textContent=m.status==='cancelled' ? ui('This meeting has been cancelled. Reopening requires the organiser; pending invitations must be sent again.','Cette rencontre a été annulée. L’organisateur peut la rouvrir ; les invitations en attente doivent être renvoyées.') : mem?.status==='withdrawn' ? ui('The organiser withdrew your invitation. You cannot accept this old invitation.','L’organisateur a retiré votre invitation. Vous ne pouvez pas accepter cette ancienne invitation.') : mem?.status==='declined' ? ui('You declined this invitation. The organiser can invite you again.','Vous avez refusé cette invitation. L’organisateur peut vous inviter de nouveau.') : ui('This meeting has ended.','Cette rencontre est terminée.');
  $('member-area').hidden = !accepted;
  $('export').hidden = !accepted || !S.current.od_matrix?.length || /; wv\)/.test(navigator.userAgent);
  $('complete').hidden = !owner() || !live();
  $('edit-meeting').hidden=!owner();$('delete-meeting').hidden=!owner();
  $('edit-meeting').textContent=ui('Edit meeting','Modifier la rencontre');
  $('delete-meeting').textContent=ui('Delete meeting','Supprimer la rencontre');
  $('edit-meeting').disabled=S.calculating?.id===m.id;
  if (!accepted) {
    clearPrivate();
    return;
  }
  if (m.selected_proposal_id) S.selected = m.selected_proposal_id;else if (!S.current.proposals?.some(p => p.id === S.selected)) S.selected = S.current.proposals?.[0]?.id || null;
  $('member-count').textContent = S.current.members.filter(p => p.status === 'accepted').length + ' participants';
  $('members').innerHTML = S.current.members.map(p => `<div class="member"><div class="avatar" style="color:${color(p.user_id)}">${avatarHtml(p)}</div><div><strong>${esc(p.name)}${p.user_id === S.user.id ? tr(" · vous") : ''}</strong><small>${p.user_id === m.organiser_id ? tr("Organisateur") : p.status === 'invited' ? tr("Invitation en attente") : p.status === 'declined' ? tr("Invitation refusée") : p.status === 'withdrawn' ? ui('Invitation withdrawn','Invitation retirée') : p.input ? tr("Trajet renseigné") : tr("Trajet à renseigner")}</small></div>${owner() && p.status==='invited' && !['travelling','completed','cancelled'].includes(m.status) ? `<button type="button" class="text-button" data-cancel-invite="${esc(p.user_id)}">${ui('Cancel invitation','Retirer l’invitation')}</button>` : `<span>${p.input ? '✓' : ''}</span>`}</div>`).join('');
  $('members').querySelectorAll('[data-cancel-invite]').forEach(button=>button.onclick=()=>cancelInvitation(button.dataset.cancelInvite,button));
  const locked = ['travelling', 'completed', 'cancelled'].includes(m.status);
  $('invite-tools').hidden = !owner() || locked;
  $('compute').hidden = !owner() || locked;
  $('inputs').querySelectorAll('input,button').forEach(e => e.disabled = locked);
  $('live').hidden = !live();
  if (!live()) {
    S.positions?.remove();
    S.positions = null;
    $('positions').innerHTML = '';
    $('messages').innerHTML = '';
  }
  if (fill) {
    const v = mem.input || {};
    $('lat').value = v.lat ?? '';
    $('lon').value = v.lon ?? '';
    $('from').value = v.available_from || '08:00';
    $('until').value = v.available_until || '18:00';
    $('walk').checked = !v.modes || v.modes.includes('walk');
    $('transit').checked = !v.modes || v.modes.some(x => ['transit', 'bus', 'train'].includes(x));
    $('boarding-margin').value=v.boarding_margin_minutes??3;
    $('attendance-from').value=v.attendance_from || '';
    $('attendance-until').value=v.attendance_until || '';
  }
  renderProposals();
  renderPersonalSchedule();
  $('verify-walks').hidden=!owner() || !S.current.proposals?.length || ['travelling','completed','cancelled'].includes(S.current.meeting.status);
  renderRoutes();
  renderCalculationState();
  sharingButtons();
}
async function cancelInvitation(userId,button) {
  if(!confirm(ui('Withdraw this pending invitation? You can invite this person again.','Retirer cette invitation en attente ? Vous pourrez inviter cette personne de nouveau.')))return;
  return act(button,async()=>{
    S.current=await api(`/meetings/${S.current.meeting.id}/invitations/${encodeURIComponent(userId)}/cancel`,{method:'POST'});
    $('search-results').innerHTML='';$('search').value='';S.selected=null;renderMeeting();
    await S.notifications?.refresh();toast(ui('Invitation withdrawn. You can invite this person again.','Invitation retirée. Vous pouvez inviter cette personne de nouveau.'));
  });
}
async function changeMeetingState(action,button) {
  const cancelling=action==='cancel';
  if(!confirm(cancelling ? ui('Cancel this meeting? Live sharing will stop and pending invitations will be withdrawn.','Annuler cette rencontre ? Le partage de position s’arrêtera et les invitations en attente seront retirées.') : ui('Reopen this meeting? Recalculate and approve a new proposal. Pending invitations will not be resent automatically.','Rouvrir cette rencontre ? Recalculez et approuvez une nouvelle proposition. Les invitations ne seront pas renvoyées automatiquement.')))return;
  return act(button,async()=>{
    if(cancelling)await stopSharing();
    S.current=await api(`/meetings/${S.current.meeting.id}/${action}`,{method:'POST'});
    S.selected=null;clearPrivate();renderMeeting(true);await S.notifications?.refresh();
    toast(cancelling ? ui('Meeting cancelled.','Rencontre annulée.') : ui('Meeting reopened. Send any withdrawn invitations again, then recalculate.','Rencontre rouverte. Renvoyez les invitations retirées, puis recalculez.'));
  });
}
$('cancel-meeting').onclick=()=>changeMeetingState('cancel',$('cancel-meeting'));
$('reopen-meeting').onclick=()=>changeMeetingState('reopen',$('reopen-meeting'));
$('accept').onclick = () => respond(true);
$('decline').onclick = () => respond(false);
function respond(accept) {
  act($(accept ? 'accept' : 'decline'), async () => {
    S.current = await api(`/meetings/${S.current.meeting.id}/respond`, {
      method: 'POST',
      body: {
        accept
      }
    });
    renderMeeting(true);
    await S.notifications?.refresh();
    toast(accept ? tr("Invitation acceptée.") : tr("Invitation refusée."));
  });
}
$('search').oninput = () => {
  clearTimeout(S.searchTimer);
  const q = $('search').value.trim(),
    id = S.current?.meeting.id;
  if (q.length < 2) {
    $('search-results').innerHTML = '';
    return;
  }
  S.searchTimer = setTimeout(async () => {
    try {
      const rows = await api('/users?q=' + encodeURIComponent(q));
      if (S.current?.meeting.id !== id || $('search').value.trim() !== q) return;
      const members = new Set(S.current.members.filter(m => ['accepted','invited'].includes(m.status)).map(m => m.user_id));
      $('search-results').innerHTML = rows.filter(x => !members.has(x.id)).map(x => "<div class=\"search-person\"><span>" + esc(x.name) + "</span><button class=\"secondary\" data-invite=\"" + esc(x.id) + tr("\">Inviter</button></div>")).join('') || tr("<p class=\"fine\">Aucun profil correspondant à inviter.</p>");
      $('search-results').querySelectorAll('[data-invite]').forEach(b => b.onclick = () => act(b, async () => {
        S.current = await api(`/meetings/${id}/invitations`, {
          method: 'POST',
          body: {
            user_ids: [b.dataset.invite]
          }
        });
        $('search').value = '';
        $('search-results').innerHTML = '';
        renderMeeting();
        toast(tr("Invitation envoyée dans l’application."));
      }));
    } catch (e) {
      toast(e.message, true);
    }
  }, 300);
};
$('inputs').onsubmit = e => {
  e.preventDefault();
  act(e.submitter, async () => {
    if ($('lat').value.trim()==='' || $('lon').value.trim()==='' || !Number.isFinite(Number($('lat').value)) || !Number.isFinite(Number($('lon').value))) throw Error(tr("Choisissez votre point de départ sur la carte ou utilisez votre position."));
    const modes = [$('walk').checked ? 'walk' : null, $('transit').checked ? 'transit' : null].filter(Boolean);
    if (!modes.length) throw Error(tr("Choisissez au moins un mode de transport."));
    S.current = await api(`/meetings/${S.current.meeting.id}/inputs`, {
      method: 'PUT',
      body: {
        lat: Number($('lat').value),
        lon: Number($('lon').value),
        available_from: $('from').value,
        available_until: $('until').value,
        modes,
        boarding_margin_minutes:Number($('boarding-margin').value),
        attendance_from:$('attendance-from').value || null,
        attendance_until:$('attendance-until').value || null
      }
    });
    S.draft?.remove();
    S.draft = null;
    renderMeeting();
    toast(tr("Votre trajet est enregistré."));
  });
};
$('locate').onclick = () => act($('locate'), async () => {
  const p = await locateOnce();
  $('lat').value = p.coords.latitude.toFixed(6);
  $('lon').value = p.coords.longitude.toFixed(6);
  markDraft(p.coords.latitude, p.coords.longitude);
});
function locateOnce() {
  return new Promise((ok, no) => {
    if (!navigator.geolocation) return no(Error(tr("La géolocalisation n’est pas disponible.")));
    navigator.geolocation.getCurrentPosition(ok, e => no(Error(e.code === 1 ? tr("Autorisez la localisation ou sélectionnez un point manuellement.") : tr("Position indisponible. Sélectionnez un point sur la carte."))), {
      enableHighAccuracy: true,
      timeout: 18000,
      maximumAge: 15000
    });
  });
}
function renderCalculationState() {
  const id=S.current?.meeting.id;
  const busy=Boolean(id && S.calculating?.id===id);
  const error=S.calculationError?.id===id ? S.calculationError.message : '';
  const elapsed=busy ? Math.floor((Date.now()-S.calculating.started)/1000) : 0;
  $('compute').disabled=busy;
  $('compute').textContent=busy ? ui('Calculating…','Calcul en cours…') : ui('Calculate ↗','Calculer ↗');
  $('calculation-status').hidden=!busy && !error;
  $('calculation-status').textContent=busy ? ui(`Calculating journeys · ${elapsed}s. Walking routes and timetables can take time. Results will appear here automatically.`,`Calcul des trajets · ${elapsed}s. Les chemins piétons et les horaires peuvent prendre du temps. Les résultats apparaîtront ici automatiquement.`) : error;
  $('calculation-status').setAttribute('aria-busy',String(busy));
}
async function calculateMeeting(refine = false) {
  const id=S.current?.meeting.id, userId=S.user?.id;
  if(!id)return;
  if(S.calculating){toast(ui('Another calculation is still running. Please wait.','Un calcul est déjà en cours. Veuillez patienter.'));return;}
  S.detailEpoch=(S.detailEpoch || 0)+1;
  S.calculating={id,started:Date.now()};S.calculationError=null;
  renderCalculationState();
  const timer=setInterval(()=>{if(S.current?.meeting.id===id)renderCalculationState();},1000);
  try {
    const d=await api(`/meetings/${id}/proposals${refine===true?'?refine=true':''}`,{method:'POST'});
    S.detailEpoch=(S.detailEpoch || 0)+1;
    if(S.user?.id===userId && S.current?.meeting.id===id) {
      S.current=d;S.selected=d.proposals?.[0]?.id || null;
      renderMeeting();
      toast(d.proposals?.length ? tr("Propositions calculées.") : d.data_status?.planning_incomplete ? ui('Search incomplete: some walking routes could not be verified.','Recherche incomplète : certains trajets à pied n’ont pas pu être vérifiés.') : tr("Aucun lieu ne satisfait les contraintes."));
    }
  } catch(e) {
    if(S.user?.id===userId)S.calculationError={id,message:ui('Calculation did not finish: ','Le calcul n’a pas abouti : ')+e.message};
    if(S.current?.meeting.id===id)toast(e.message,true);
  } finally {
    clearInterval(timer);S.calculating=null;
    S.detailEpoch=(S.detailEpoch || 0)+1;
    if(S.current?.meeting.id===id)renderCalculationState();
  }
}
$('compute').onclick=calculateMeeting;
$('verify-walks').onclick=()=>calculateMeeting(true);
$('edit-meeting').onclick=()=>{
  const m=S.current.meeting;if(!owner() || S.calculating?.id===m.id)return;
  S.editingMeeting=m.id;setMeetingFormLabels(true);
  $('title').value=m.title;$('date').value=m.date;$('duration').value=m.duration_minutes;$('objective').value=m.objective;
  $('meeting-place-preference').disabled=true;
  $('create-dialog').showModal();
};
$('delete-meeting').onclick=()=>act($('delete-meeting'),async()=>{
  const id=S.current.meeting.id;
  if(!confirm(ui('Permanently delete this meeting, its invitations, proposals and group chat? This cannot be undone.','Supprimer définitivement cette rencontre, ses invitations, propositions et messages ? Cette action est irréversible.')))return;
  S.detailEpoch=(S.detailEpoch || 0)+1;
  await stopSharing();await api('/meetings/'+id,{method:'DELETE'});
  await home();await S.notifications?.refresh();
});
function renderProposals() {
  const proposals = S.current.proposals || [];
  $('proposals').innerHTML = proposals.map(p => "<article class=\"proposal " + (p.id === S.selected ? 'selected' : '') + "\"><span class=\"mini\">" + (p.rank ? ui('RECOMMENDED','RECOMMANDE') : tr("PROPOSITION")) + " · " + esc(time(p.start)) + "</span><h3>" + esc(p.venue?.name || p.venue_name || tr("Lieu de rencontre")) + "</h3><p>" + esc(time(p.start)) + " – " + esc(time(p.end)) + "" + (p.latest_start ? tr(" · début possible jusqu’à ") + esc(time(p.latest_start)) : '') + "</p><p class=\"muted\">" + esc(p.score?.total_travel_minutes ?? '—') + tr(" min cumulées · ") + esc(p.score?.max_travel_minutes ?? '—') + tr(" min pour le trajet le plus long</p>") + (p.conditional ? tr("<p class=\"notice warning\">Salle proposée sous réserve de disponibilité et de réservation externe.</p>") : '') + "<p class=\"fine\">" + esc(p.availability_note || '') + "</p><div class=\"buttons\"><button class=\"secondary\" data-route=\"" + esc(p.id) + tr("\">Voir les trajets</button>") + (S.current.meeting.status === 'proposal' ? "<button class=\"primary\" data-vote=\"" + esc(p.id) + tr("\" data-accept=\"true\">Approuver</button><button class=\"secondary\" data-vote=\"") + esc(p.id) + tr("\" data-accept=\"false\">Refuser</button>") : '') + "</div><p class=\"fine\">" + (S.current.approvals || []).filter(x => x.proposal_id === p.id && x.accepted).length + tr(" approbation(s)</p></article>")).join('') || tr("<p class=\"muted\">Les propositions apparaîtront une fois les invitations traitées et les trajets de chacun renseignés.</p>");
  if(proposals.length && S.current.selection_evidence?.candidate_count){
    const count=S.current.selection_evidence.candidate_count;
    const reason=S.current.meeting.objective==='min_total' ? ui('Lowest total computed journey time','Durée cumulée calculée minimale') : ui('Earliest feasible meeting; total journey time breaks ties','Rencontre possible au plus tôt ; durée cumulée en cas d’égalité');
    $('proposals').innerHTML=`<p class="fine">${esc(reason)} · ${esc(count)} ${esc(ui('enabled places considered','lieux actifs examinés'))}</p>`+$('proposals').innerHTML;
  }
  if (proposals.length && S.current.data_status?.planning_incomplete) $('proposals').innerHTML = `<p class="notice warning">${ui('Some walking links remain estimates. The search is incomplete; these proposals are conditional on verifying those links.','Certains trajets à pied restent estimés. La recherche est incomplète ; ces propositions nécessitent leur vérification.')}</p>` + $('proposals').innerHTML;
  $('proposals').querySelectorAll('[data-route]').forEach(b => b.onclick = () => {
    if (S.current.meeting.selected_proposal_id && b.dataset.route !== S.current.meeting.selected_proposal_id) {
      toast(tr("La carte affiche le lieu confirmé par le groupe."));
      return;
    }
    S.selected = b.dataset.route;
    renderProposals();
    renderRoutes(true);
  });
  $('proposals').querySelectorAll('[data-vote]').forEach(b => b.onclick = () => act(b, async () => {
    S.current = await api(`/meetings/${S.current.meeting.id}/decision`, {
      method: 'POST',
      body: {
        proposal_id: b.dataset.vote,
        accept: b.dataset.accept === 'true'
      }
    });
    renderMeeting();
    if (live()) await refreshLive();
    toast(live() ? tr("Rencontre confirmée par le groupe.") : tr("Votre réponse est enregistrée."));
  }));
  const rejections = S.current.rejections || [];
  $('rejections').hidden = !rejections.length;
  if (!proposals.length && rejections.length) {
    $('rejections').open = true;
    $('proposals').innerHTML = `<p class="notice warning">${ui('No place currently fits the group. See each reason below; adjust your availability or starting point, or add another place.','Aucun lieu ne convient au groupe. Consultez les raisons ci-dessous ; adaptez vos horaires ou votre point de départ, ou ajoutez un lieu.')}</p>`;
  }
  if (!proposals.length && S.current.data_status?.planning_incomplete) $('proposals').innerHTML = `<p class="notice warning">${ui('Search incomplete. This does not prove that no meeting is possible. Some pedestrian routes could not be verified; try again or review the available places below.','Recherche incomplète. Cela ne prouve pas qu’aucune rencontre n’est possible. Certains trajets à pied n’ont pas pu être vérifiés ; réessayez ou consultez les lieux ci-dessous.')}</p>`;
  $('rejection-list').innerHTML = rejections.map(r => `<div class="rejection"><strong>${esc(r.venue_name || r.venue_id || tr("Lieu"))}</strong><br>${esc(r.reason || r.reasons?.join(' '))}</div>`).join('');
}
function suppliedGeometry(leg) {
  if(leg.indoor)return (leg.geometry || []).length>=2;
  if(leg.mode==='walk' && Number(leg.distance_m)<3)return true;
  return ['osm_foot_route', 'gtfs_shape', 'sncf_rail_corridor'].includes(leg.geometry_kind);
}
function geometryNote(leg) {
  if(leg.indoor)return ui('Indoor instructions from the supplied building graph.','Instructions intérieures issues du graphe du bâtiment fourni.');
  if(leg.mode==='walk' && Number(leg.distance_m)<3)return tr("Aucun déplacement à pied nécessaire ici.");
  if (leg.geometry_kind === 'osm_foot_route') return tr("Chemin piéton calculé sur le réseau OpenStreetMap.");
  if (leg.geometry_kind === 'sncf_rail_corridor') return tr("Corridor ferroviaire SNCF : infrastructure réelle, tracé du service non certifié.");
  if (leg.geometry_kind === 'gtfs_shape') return tr("Tracé fourni par les données de transport.");
  return tr("Géométrie non disponible : seuls les points de départ et d’arrivée sont affichés.");
}
function routePopup(it, leg) {
  return `<strong>${esc(it.name || 'Participant')}</strong><br>${esc(modeLabel(leg.mode))} ${esc(leg.route_name || '')}${leg.headsign ? ' · ' + esc(leg.headsign) : ''}<br>${esc(leg.from_name)} → ${esc(leg.to_name)}<br>${esc(time(leg.departure))} → ${esc(time(leg.arrival))}<br><small>${esc(geometryNote(leg))}</small>`;
}
function routeLineBadge(leg, participantColor) {
  return `<span class="map-line-badge" style="--route-color:${participantColor}"><span>${esc(modeLabel(leg.mode))}</span><b>${esc(leg.route_name || '')}</b></span>`;
}
function plannedOrigin(itinerary) {
  const leg=itinerary?.legs?.[0];
  const point=leg?.routing_endpoints?.[0] || leg?.geometry?.[0];
  return Array.isArray(point) && point.length>=2 && point.slice(0,2).every(Number.isFinite) ? point.slice(0,2) : null;
}
function renderRoutes(forceFit = false) {
  for (const l of S.layers) l.remove();
  S.layers = [];
  const p = chosen();
  $('routes-panel').hidden = !p;
  $('map-legend').textContent = p ? tr("Couleur = participant · lignes continues = géométrie fournie · arrêts = montée / descente") : tr("Cliquez pour choisir votre point de départ");
  const bounds = [];
  if (ensureMap()) {
    const layer = L.layerGroup().addTo(S.map);
    S.layers.push(layer);
    if (p) {
      for (const it of p.itineraries || []) {
        const stops = new Set();
        let badgeCount = 0;
        for (const leg of it.legs || []) {
          const geom = (leg.geometry || []).filter(x => Array.isArray(x) && x.length >= 2 && x.every(Number.isFinite));
          if (!geom.length) continue;
          const participantColor = color(it.user_id), popup = routePopup(it, leg);
          const weight = leg.mode === 'walk' ? 3 : leg.mode === 'train' ? 6 : 5;
          if (suppliedGeometry(leg) && geom.length > 1) {
            // Unknown / straight-line geometry is never restyled as a real path.
            L.polyline(geom, {color:'#fff', weight:weight+4, opacity:.94, interactive:false, lineCap:'round', lineJoin:'round'}).addTo(layer);
            L.polyline(geom, {color:participantColor, weight, opacity:.95, lineCap:'round', lineJoin:'round'}).bindPopup(popup).addTo(layer);
            bounds.push(...geom);
            if (leg.mode !== 'walk' && badgeCount < 5) {
              const midpoint = geom[Math.floor(geom.length/2)];
              L.marker(midpoint, {icon:L.divIcon({className:'map-line-label', html:routeLineBadge(leg, participantColor), iconSize:[90,25], iconAnchor:[45,12]}), keyboard:true, title:modeLabel(leg.mode)+' '+(leg.route_name||'')}).bindPopup(popup).addTo(layer);
              badgeCount++;
            }
          } else {
            // Preserve known endpoints while omitting a misleading straight connector.
            bounds.push(geom[0], geom[geom.length-1]);
          }
          if (leg.mode !== 'walk' || !suppliedGeometry(leg)) {
            const endpoints = [[geom[0],leg.from_name,leg.departure], [geom[geom.length-1],leg.to_name,leg.arrival]];
            for (const [point,name,clock] of endpoints) {
              const key=point.join(','); if(stops.has(key))continue; stops.add(key);
              L.circleMarker(point,{radius:5,color:participantColor,weight:2,fillColor:'#fff',fillOpacity:1}).bindPopup(`<strong>${esc(name)}</strong><br>${esc(modeLabel(leg.mode))} ${esc(leg.route_name||'')} · ${esc(time(clock))}<br><small>${esc(geometryNote(leg))}</small>`).addTo(layer);
            }
          }
        }
      }
      if (Number.isFinite(p.venue?.lat) && Number.isFinite(p.venue?.lon)) {
        L.marker([p.venue.lat,p.venue.lon],{title:p.venue.name,zIndexOffset:700}).bindPopup('<strong>'+esc(ui('Meeting place','Lieu de rencontre'))+'</strong><br>'+esc(p.venue.name)).bindTooltip(esc(p.venue.name),{direction:'top'}).addTo(layer);
        bounds.push([p.venue.lat,p.venue.lon]);
      }
    } else {
      for (const v of S.venues) if (Number.isFinite(v.lat) && Number.isFinite(v.lon)) {
        L.circleMarker([v.lat,v.lon],{radius:6,color:'#bd8336',fillOpacity:.7}).bindPopup(esc(v.name)).addTo(layer);
        bounds.push([v.lat,v.lon]);
      }
    }
    for (const m of S.current.members || []) if (m.input) {
      const itinerary=p?.itineraries?.find(it=>it.user_id===m.user_id);
      const point=plannedOrigin(itinerary) || [m.input.lat,m.input.lon];
      const originLabel=ui('Planned departure','Départ prévu');
      personMarker(point,m).bindPopup('<strong>'+esc(m.name)+'</strong><br>'+originLabel+'<br>'+point.map(n=>n.toFixed(6)).join(', ')).bindTooltip(esc(m.name)+' · '+originLabel,{direction:'top'}).addTo(layer);
      bounds.push(point);
    }
    if(bounds.length && (forceFit || S.mapViewportMeeting!==S.current.meeting.id)) {
      S.map.fitBounds(bounds,{padding:[38,38],maxZoom:15});
      S.mapViewportMeeting=S.current.meeting.id;
    }
    $('show-all-routes').textContent=ui('Show all routes','Afficher tous les trajets');
    $('show-all-routes').onclick=()=>renderRoutes(true);
  }
  if(!p){$('routes').innerHTML='';return;}
  $('routes').innerHTML=(p.itineraries||[]).map(it=>{
    const legs=it.legs||[];
    const summary=legs.map(l=>`<span class="journey-mode ${esc(l.mode)}"><span>${esc(modeLabel(l.mode))}</span>${l.route_name?`<b>${esc(l.route_name)}</b>`:''}</span>`).join('<span class="journey-arrow">›</span>');
    const body=legs.map((l,index)=>{
      const previous=legs[index-1];
      const wait=previous?Math.round((Date.parse(l.departure)-Date.parse(previous.arrival))/60000):0;
      const waitText=wait>0?`<div class="journey-wait">${esc(tr("Attente / correspondance"))} · ${wait} min</div>`:'';
      return waitText+`<div class="leg route-timeline-leg" style="--route-color:${color(it.user_id)}"><div class="leg-times"><strong>${esc(time(l.departure))}</strong><small>${esc(time(l.arrival))}</small></div><div class="leg-content"><span class="journey-mode ${esc(l.mode)}">${esc(modeLabel(l.mode))}${l.route_name?` <b>${esc(l.route_name)}</b>`:''}</span><strong>${esc(l.from_name)} → ${esc(l.to_name)}</strong>${l.headsign?`<span class="fine">${esc(tr("Direction"))} : ${esc(l.headsign)}</span>`:''}<span class="fine">${esc(l.duration_minutes??'—')} min${l.distance_unknown?'':` · ${esc(l.distance_m??'—')} m`}${l.instructions?`<br>${esc(l.instructions)}`:''}</span><small class="geometry-note ${suppliedGeometry(l)?'':'unresolved'}">${esc(geometryNote(l))}</small></div></div>`;
    }).join('');
    const hasMissing=legs.some(l=>!suppliedGeometry(l));
    const saved=S.current.members.find(m=>m.user_id===it.user_id)?.input;
    const origin=plannedOrigin(it);
    const originChanged=saved && origin && (Math.abs(saved.lat-origin[0])>0.0001 || Math.abs(saved.lon-origin[1])>0.0001);
    const staleNote=originChanged ? `<p class="notice warning">${esc(ui('This journey was calculated from a different starting point than the one currently saved. Save the correct departure point, then calculate again.','Ce trajet a été calculé depuis un autre point que le départ enregistré. Enregistrez le bon départ, puis relancez le calcul.'))}</p>` : '';
    return `<article class="route"><h3><span class="route-dot" style="background:${color(it.user_id)}"></span>${esc(it.name||'Participant')}${tr(" · arrivée ")}${esc(time(it.arrival))}</h3><p class="fine">${esc(ui('Leave at','Départ à'))} <strong>${esc(time(it.departure || it.legs?.[0]?.departure))}</strong> · ${esc(it.duration_minutes??'—')} min · ${esc(it.distance_m??'—')} m<br>${esc(ui('Meeting starts','Début de la rencontre'))} ${esc(time(p.start))}</p><div class="journey-summary">${summary}</div>${hasMissing?`<p class="notice warning">${esc(tr("Certaines portions n’ont pas de géométrie vérifiée et ne sont pas dessinées comme des chemins réels."))}</p>`:''}${staleNote}${body}</article>`;
  }).join('');
}
$('complete').onclick = () => act($('complete'), async () => {
  await stopSharing();
  S.current = await api(`/meetings/${S.current.meeting.id}/complete`, {
    method: 'POST'
  });
  S.positions?.remove();
  S.positions = null;
  $('messages').innerHTML = '';
  $('positions').innerHTML = '';
  renderMeeting();
  toast(tr("Rencontre terminée. Les positions partagées sont supprimées."));
});
$('export').onclick = () => act($('export'), async () => {
  const r = await fetch(`/api/meetings/${S.current.meeting.id}/od-matrix.csv`, {
    headers: {
      Authorization: 'Bearer ' + S.token
    }
  });
  if (!r.ok) throw Error(tr("Export indisponible."));
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = 'pointcommun-od.csv';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('chat-form').onsubmit = e => {
  e.preventDefault();
  act(e.submitter, async () => {
    const id = S.current.meeting.id;
    await api(`/meetings/${id}/chat`, {
      method: 'POST',
      body: {
        text: $('chat-text').value.trim()
      }
    });
    $('chat-text').value = '';
    await refreshLive();
  });
};
function sharingButtons() {
  const on = S.watch !== null;
  $('share').hidden = on;
  $('stop-share').hidden = !on;
  $('sharing-note').textContent = on ? tr("Partage actif pour ce groupe. La position s’arrête en quittant cette page.") : tr("Partage désactivé. Le navigateur doit rester actif.");
}
$('share').onclick = () => act($('share'), async () => {
  if (!live()) throw Error(tr("Confirmez la rencontre avant de partager."));
  if (!navigator.geolocation) throw Error(tr("Géolocalisation indisponible."));
  if (!window.isSecureContext) throw Error(tr("La localisation nécessite HTTPS (ou localhost)."));
  await stopSharing();
  const id = S.current.meeting.id;
  S.sharing = id;
  S.watch = navigator.geolocation.watchPosition(async p => {
    if (S.sharing !== id || S.current?.meeting.id !== id || document.hidden) return;
    try {
      const sentToken = S.token;
      await api(`/meetings/${id}/location`, {
        method: 'PUT',
        body: {
          lat: p.coords.latitude,
          lon: p.coords.longitude,
          accuracy: p.coords.accuracy
        }
      });
      if (S.sharing === id) await refreshLive();else if (sentToken) await fetch(`/api/meetings/${id}/location`, {
        method: 'DELETE',
        headers: {
          Authorization: 'Bearer ' + sentToken
        }
      });
    } catch (e) {
      await stopSharing();
      toast(e.message, true);
    }
  }, async e => {
    await stopSharing();
    toast(e.code === 1 ? tr("Permission de localisation refusée.") : tr("Position indisponible. Réessayez."), true);
  }, {
    enableHighAccuracy: true,
    timeout: 20000,
    maximumAge: 5000
  });
  sharingButtons();
});
$('stop-share').onclick = () => act($('stop-share'), stopSharing);
async function stopSharing() {
  const id = S.sharing;
  S.sharing = null;
  if (S.watch !== null) {
    navigator.geolocation?.clearWatch(S.watch);
    S.watch = null;
  }
  sharingButtons();
  if (id && S.token) try {
    await api(`/meetings/${id}/location`, {
      method: 'DELETE'
    });
  } catch {}
  if (id) {
    S.positions?.remove();
    S.positions = null;
    $('positions').innerHTML = '';
  }
}
function progressText(p) {
  if (!p) return '';
  const labels = {
    stale: tr("Position trop ancienne"),
    inaccurate: tr("Précision insuffisante"),
    off_route: tr("Hors de l’itinéraire prévu"),
    missed_connection: tr("Correspondance à vérifier"),
    not_on_trip_date: tr("Hors de la date du trajet"),
    not_started: tr("Trajet pas encore commencé"),
    no_itinerary: tr("Itinéraire indisponible"),
    waiting: tr("En attente"),
    arrived: tr("À proximité du lieu, salle non confirmée")
  };
  if (!p.estimated_arrival) return tr("Arrivée estimée indisponible · ") + (labels[p.status] || tr("Informations insuffisantes"));
  const n = Number(p.delay_minutes);
  return "" + (labels[p.status] ? labels[p.status] + ' · ' : '') + tr("Arrivée estimée ") + time(p.estimated_arrival) + "" + (Number.isFinite(n) ? n > 0 ? tr(" · retard estimé ") + Math.round(n) + ' min' : n < 0 ? tr(" · avance estimée ") + Math.round(-n) + ' min' : tr(" · à l’heure prévue") : '') + "";
}
async function refreshLive() {
  if (!live()) return;
  const id = S.current.meeting.id;
  const [messages, positions] = await Promise.all([api(`/meetings/${id}/chat`), api(`/meetings/${id}/locations`)]);
  if (S.current?.meeting.id !== id || !live()) return;
  const chat = $('messages'),
    nearEnd = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 60;
  const html = messages.map(m => `<div class="message ${m.user_id === S.user.id ? 'mine' : ''}"><small>${esc(m.name || tr("Membre"))} · ${esc(time(m.timestamp))}</small><p>${esc(m.text)}</p></div>`).join('') || tr("<p class=\"fine\">La discussion est ouverte. Dites au groupe quand vous partez.</p>");
  if (chat.innerHTML !== html) {
    chat.innerHTML = html;
    if (nearEnd) chat.scrollTop = chat.scrollHeight;
  }
  $('positions').innerHTML = positions.map(p => {
    const age = Math.max(0, Math.round((Date.now() - Date.parse(p.timestamp)) / 1000));
    return "<div class=\"position\"><strong style=\"color:" + color(p.user_id) + "\">● " + esc(p.name || tr("Membre")) + "</strong><span>" + (age > 90 ? tr("Position ancienne · ") : '') + tr("Dernier envoi ") + esc(time(p.timestamp)) + "" + (p.accuracy ? ' · ±' + Math.round(p.accuracy) + ' m' : '') + "</span><span>" + esc(progressText(p.progress)) + "</span></div>";
  }).join('') || tr("<p class=\"fine\">Aucun membre ne partage sa position.</p>");
  if (positions.some(p => p.progress)) $('positions').innerHTML += tr("<p class=\"fine\">Estimations à partir des positions et du trajet prévu, sans données de retard des véhicules.</p>");
  if (ensureMap()) {
    S.positions?.remove();
    S.positions = L.layerGroup().addTo(S.map);
    for (const p of positions) if (Number.isFinite(p.lat) && Number.isFinite(p.lon)) personMarker([p.lat, p.lon], p).bindTooltip(esc(p.name)+" · "+ui("Shared location","Position partagée"),{direction:"top"}).bindPopup("<strong>" + esc(p.name || tr("Membre")) + " · " + ui("Shared location","Position partagée") + tr("</strong><br>Dernier envoi ") + esc(time(p.timestamp)) + "<br>" + esc(progressText(p.progress)) + "").addTo(S.positions);
  }
}
document.addEventListener('visibilitychange', () => {
  if (document.hidden) stopSharing();
});
window.addEventListener('pointcommun:pause', stopSharing);
window.addEventListener('pagehide', () => {
  if (S.watch !== null) navigator.geolocation?.clearWatch(S.watch);
  if (S.sharing && S.token) fetch(`/api/meetings/${S.sharing}/location`, {
    method: 'DELETE',
    headers: {
      Authorization: 'Bearer ' + S.token
    },
    keepalive: true
  }).catch(() => {});
});
// Catalogue editor and participant photos share the same backend on web and Android.
const venueCategories = ['library','meeting_room','office','university','coworking','cafe','public_space','other'];
function categoryLabel(key) {
  const labels={library:['Library','Bibliothèque'],meeting_room:['Meeting room','Salle de réunion'],office:['Office','Bureau'],university:['Campus / university','Campus / université'],coworking:['Coworking','Coworking'],cafe:['Café','Café'],public_space:['Public space','Espace public'],other:['Other','Autre']};
  return labels[key] ? ui(...labels[key]) : key || ui('Unspecified','Non précisé');
}
function safeAvatar(value) { return typeof value==='string' && /^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(value) && value.length <= 550000 ? value : ''; }
function avatarHtml(person) {
  const image=safeAvatar(person.avatar);
  return image ? `<img src="${image}" alt="${esc(person.name || '')}" loading="lazy">` : esc(initials(person.name));
}
function personMarker(point,person) {
  const member=S.current?.members?.find(m=>m.user_id===person.user_id);
  const resolved={...member,...person,avatar:person.avatar || member?.avatar || (person.user_id===S.user?.id ? S.user.avatar : null)};
  return L.marker(point,{icon:L.divIcon({className:'person-map-marker',html:`<span class="map-person-photo" style="--person-color:${color(person.user_id)}">${avatarHtml(resolved)}</span>`,iconSize:[42,42],iconAnchor:[21,21]}),title:resolved.name || tr('Membre'),zIndexOffset:500});
}
function renderProfilePhoto() { $('avatar').innerHTML=avatarHtml(S.user); $('photo-preview').innerHTML=avatarHtml(S.user); }
function preferredVenueIds(preference, venues) {
  if(preference !== 'work')return [];
  const ids=venues.filter(v=>(v.quiet===true || ['meeting_room','coworking','office'].includes(v.category)) && v.discussion_allowed===true && v.permitted===true && v.active!==false).map(v=>v.id);
  if(!ids.length)throw Error(ui('No permitted work and discussion spaces are in the catalogue. Add one or choose all candidate places.','Aucun espace de travail autorisé pour les discussions dans le catalogue. Ajoutez-en un ou choisissez tous les lieux.'));
  if(ids.length>100)throw Error(ui('Too many matching places. Narrow the catalogue before creating this meeting.','Trop de lieux correspondants. Réduisez le catalogue avant de créer la rencontre.'));
  return ids;
}
const catalogueLabels={
  'meeting-place-preference-label':['Preferred places','Lieux préférés'],
  'add-venue':['＋ Add a place','＋ Ajouter un lieu'], 'quiet-filter-label':['Quiet places','Lieux calmes'],
  'venue-name-label':['Place name','Nom du lieu'], 'venue-city-label':['City','Ville'], 'venue-type-label':['Category','Catégorie'],
  'venue-address-label':['Address · building / floor / room','Adresse · bâtiment / étage / salle'],
  'venue-map-help':['Click the map to place the pin, then drag it to the entrance.','Cliquez sur la carte pour placer le repère, puis déplacez-le jusqu’à l’entrée.'],
  'venue-coordinates-label':['Advanced coordinates (optional)','Coordonnées avancées (facultatif)'],
  'venue-capacity-label':['Capacity (leave blank if unknown)','Capacité (vide si inconnue)'], 'venue-quiet-label':['Quiet place?','Lieu calme ?'],
  'venue-discussion-label':['Group discussion is allowed','Les discussions en groupe sont autorisées'],
  'venue-permitted-label':['I confirm the group is allowed to use this place','Je confirme que le groupe est autorisé à utiliser ce lieu'],
  'venue-booking-label':['External booking required','Réservation externe nécessaire'],
  'venue-hours-title':['Opening hours','Horaires d’ouverture'],
  'venue-hours-help':['Enter hours only when known. Blank days are unavailable for automatic planning. Use “+” for a lunch-break interval.','Renseignez les horaires connus. Les jours vides sont exclus du calcul automatique. Utilisez « + » pour une plage après la pause de midi.'],
  'venue-notes-label':['Access, availability and other notes','Accès, disponibilité et autres notes'],
  'venue-link-label':['Venue / booking website (optional)','Site du lieu / réservation (facultatif)'],
  'venue-conditional-note':['Saving a place does not book it. Proposals remain subject to availability confirmation.','Enregistrer un lieu ne le réserve pas. Les propositions restent sous réserve de disponibilité.'],
  'venue-save':['Save place','Enregistrer le lieu'],
  'profile-photo-title':['Your profile photo','Votre photo de profil'],
  'photo-help':['Optional. Your photo appears to other users and on the group map. Live movement is shown only while you share your location.','Facultatif. Votre photo apparaît aux autres utilisateurs et sur la carte du groupe. Le déplacement en direct apparaît uniquement pendant votre partage de position.'],
  'photo-upload-label':['Choose a photo','Choisir une photo'], 'photo-remove':['Remove photo','Supprimer la photo']
};
for(const [id,labels] of Object.entries(catalogueLabels))$(id).textContent=ui(...labels);
$('avatar').title=ui('Edit profile photo','Modifier la photo de profil');
$('avatar').setAttribute('aria-label',ui('Edit profile photo','Modifier la photo de profil'));
$('meeting-place-preference').innerHTML=`<option value="all">${ui('All candidate places','Tous les lieux candidats')}</option><option value="work">${ui('Work and discussion spaces','Espaces de travail et de discussion')}</option>`;
$('venue-search').placeholder=ui('Search places, buildings or cities…','Rechercher un lieu, bâtiment ou une ville…');
$('venue-category').innerHTML=`<option value="">${ui('All categories','Toutes les catégories')}</option>`+venueCategories.map(k=>`<option value="${k}">${esc(categoryLabel(k))}</option>`).join('');
$('venue-type').innerHTML=venueCategories.map(k=>`<option value="${k}">${esc(categoryLabel(k))}</option>`).join('');
$('venue-quiet-value').innerHTML=`<option value="">${ui('Unknown','Inconnu')}</option><option value="true">${ui('Yes','Oui')}</option><option value="false">${ui('No','Non')}</option>`;
$('venue-address').placeholder=ui('Building, floor and room, if known','Bâtiment, étage et salle, si connus');
['venue-search','venue-category','venue-quiet'].forEach(id=>$(id).addEventListener(id==='venue-search'?'input':'change',renderVenues));
let editingVenue=null,venueMap=null,venuePin=null;
const weekDays=['mon','tue','wed','thu','fri','sat','sun'];
function hourRow(day,range=['','']) {
  const row=document.createElement('div');row.className='hours-interval';
  row.innerHTML=`<input type="time" aria-label="${day} ${ui('opening','ouverture')}" value="${esc(range[0])}"><span>–</span><input type="time" aria-label="${day} ${ui('closing','fermeture')}" value="${esc(range[1])}"><button type="button" class="text-button" aria-label="${ui('Remove interval','Supprimer la plage')}">×</button>`;
  row.querySelector('button').onclick=()=>row.remove();
  return row;
}
function renderHours(hours={}) {
  $('venue-hours').innerHTML='';
  weekDays.forEach((day,index)=>{
    const block=document.createElement('div');block.className='hours-day';block.dataset.day=day;
    const label=new Date(2026,0,5+index).toLocaleDateString(PCi18n.locale,{weekday:'short'});
    block.innerHTML=`<div class="hours-day-title"><strong>${esc(label)}</strong><button type="button" class="secondary" aria-label="${ui('Add interval','Ajouter une plage')} ${esc(label)}">+</button></div><div class="hours-ranges"></div>`;
    for(const range of hours[day]?.length?hours[day]:[['','']])block.querySelector('.hours-ranges').append(hourRow(day,range));
    block.querySelector('button').onclick=()=>block.querySelector('.hours-ranges').append(hourRow(day));
    $('venue-hours').append(block);
  });
}
function placeVenuePin(lat,lon) {
  if(!Number.isFinite(lat)||!Number.isFinite(lon))return;
  $('venue-lat').value=lat.toFixed(6);$('venue-lon').value=lon.toFixed(6);
  $('venue-point-status').textContent=ui('Location selected. Drag the pin to adjust.','Lieu sélectionné. Déplacez le repère pour ajuster.');
  if(!venueMap)return;
  venuePin?.remove();venuePin=L.marker([lat,lon],{draggable:true,autoPan:true}).addTo(venueMap);
  venuePin.on('dragend',()=>{const p=venuePin.getLatLng();$('venue-lat').value=p.lat.toFixed(6);$('venue-lon').value=p.lng.toFixed(6);});
}
function openVenue(venue=null) {
  editingVenue=venue;
  $('venue-form').reset();$('venue-form-error').textContent='';
  $('venue-dialog-title').textContent=venue?ui('Edit meeting place','Modifier le lieu'):ui('Add a meeting place','Ajouter un lieu de rencontre');
  for(const field of ['name','city','address','capacity','lat','lon'])$('venue-'+field).value=venue?.[field]??'';
  $('venue-type').value=venue?.category || 'other';
  if(!$('venue-type').value)$('venue-type').value='other';
  $('venue-quiet-value').value=venue?.quiet==null?'':String(venue.quiet);
  $('venue-discussion').checked=venue?.discussion_allowed??true;
  $('venue-permitted').checked=venue?.permitted===true;
  $('venue-booking').checked=venue?.booking_required??false;
  $('venue-enabled').checked=venue?.active!==false;
  $('venue-notes').value=venue?.notes || venue?.opening_hours_note || '';
  $('venue-link').value=venue?.booking_url || venue?.source_url || '';
  renderHours(venue?.opening_hours);
  $('venue-point-status').textContent=ui('Select an entrance on the map before saving.','Sélectionnez une entrée sur la carte avant d’enregistrer.');
  $('venue-dialog').showModal();
  setTimeout(()=>{
    if(window.L){
      if(!venueMap){venueMap=L.map('venue-map').setView([47.4955,6.8038],15);tile(venueMap);venueMap.on('click',e=>placeVenuePin(e.latlng.lat,e.latlng.lng));}
      venueMap.invalidateSize();venuePin?.remove();venuePin=null;
      if(Number.isFinite(venue?.lat)&&Number.isFinite(venue?.lon)){placeVenuePin(venue.lat,venue.lon);venueMap.setView([venue.lat,venue.lon],16);}
      else venueMap.setView([47.4955,6.8038],15);
    }else $('venue-map').textContent=ui('Map unavailable. Use advanced coordinates.','Carte indisponible. Utilisez les coordonnées avancées.');
  },80);
}
async function reloadVenues(){S.venues=await api('/venues');renderVenues();overviewMap();}
$('add-venue').onclick=()=>openVenue();$('venue-close').onclick=()=>$('venue-dialog').close();
$('venue-form').onsubmit=e=>{
  e.preventDefault();
  return act(e.submitter,async()=>{
    $('venue-form-error').textContent='';
    if(!$('venue-lat').value.trim()||!$('venue-lon').value.trim())throw Error(ui('Choose the place on the map first.','Choisissez d’abord le lieu sur la carte.'));
    const opening_hours={};
    document.querySelectorAll('.hours-day').forEach(block=>{
      opening_hours[block.dataset.day]=[];
      block.querySelectorAll('.hours-interval').forEach(row=>{
        const [from,to]=row.querySelectorAll('input');
        if(!from.value&&!to.value)return;
        if(!from.value||!to.value||from.value>=to.value)throw Error(ui('Each opening interval needs a start before its end.','Chaque plage doit commencer avant sa fin.'));
        opening_hours[block.dataset.day].push([from.value,to.value]);
      });
    });
    const body={...(editingVenue||{}),name:$('venue-name').value.trim(),city:$('venue-city').value.trim(),address:$('venue-address').value.trim(),lat:Number($('venue-lat').value),lon:Number($('venue-lon').value),capacity:$('venue-capacity').value?Number($('venue-capacity').value):null,category:$('venue-type').value,quiet:$('venue-quiet-value').value===''?null:$('venue-quiet-value').value==='true',discussion_allowed:$('venue-discussion').checked,permitted:$('venue-permitted').checked,active:$('venue-enabled').checked,booking_required:$('venue-booking').checked,opening_hours,notes:$('venue-notes').value.trim(),opening_hours_note:$('venue-notes').value.trim(),booking_url:$('venue-link').value.trim(),availability_status:editingVenue?.availability_status || 'unconfirmed'};
    for(const key of ['can_edit','is_default','owner_id','id'])delete body[key];
    await api(editingVenue?'/venues/'+encodeURIComponent(editingVenue.id):'/venues',{method:editingVenue?'PUT':'POST',body});
    $('venue-dialog').close();await reloadVenues();toast(ui('Place saved. Recalculate meeting proposals to use changes.','Lieu enregistré. Recalculez les propositions pour utiliser les modifications.'));
  });
};
$('avatar').onclick=()=>{renderProfilePhoto();$('photo-error').textContent='';$('profile-dialog').showModal();};
$('profile-close').onclick=()=>$('profile-dialog').close();
async function savePhoto(avatar){
  const result=await api('/me/avatar',{method:'PUT',body:{avatar}});
  S.user=result.user || result;renderProfilePhoto();
  if(S.current){S.current=await api('/meetings/'+S.current.meeting.id);renderMeeting();if(live())await refreshLive();}
}
$('photo-input').onchange=async()=>{
  const file=$('photo-input').files?.[0];if(!file)return;
  try{
    if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>8*1024*1024)throw Error(ui('Choose a PNG, JPEG or WebP photo under 8 MB.','Choisissez une photo PNG, JPEG ou WebP de moins de 8 Mo.'));
    const url=URL.createObjectURL(file);
    try{
      const image=await new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(Error(ui('Cannot read this image.','Image illisible.')));img.src=url;});
      const canvas=document.createElement('canvas');canvas.width=canvas.height=192;
      const ctx=canvas.getContext('2d'),size=Math.min(image.width,image.height);
      ctx.drawImage(image,(image.width-size)/2,(image.height-size)/2,size,size,0,0,192,192);
      await savePhoto(canvas.toDataURL('image/jpeg',.86));toast(ui('Profile photo updated.','Photo mise à jour.'));
    }finally{URL.revokeObjectURL(url);}
  }catch(error){$('photo-error').textContent=error.message;}finally{$('photo-input').value='';}
};
$('photo-remove').onclick=()=>act($('photo-remove'),async()=>{await savePhoto(null);toast(ui('Photo removed.','Photo supprimée.'));});

if (S.token) enter().catch(() => logout(false));

// Switching locale reloads translated source constants and safely restores the
// active meeting and draft journey fields. User content is never translated.
document.querySelectorAll('[data-language-selector]').forEach(selector => {
  selector.addEventListener('change', async event => {
    if (event.target.value === PCi18n.language) return;
    const restore = {userId:S.user?.id, meetingId:S.current?.meeting.id, selected:S.selected};
    if (S.current && me()?.status === 'accepted') {
      restore.inputs = Object.fromEntries(['lat','lon','from','until','boarding-margin','attendance-from','attendance-until'].map(id => [id,$(id).value]));
      restore.inputs.walk = $('walk').checked; restore.inputs.transit = $('transit').checked;
    }
    sessionStorage.setItem('pc-language-restore', JSON.stringify(restore));
    await stopSharing();
    PCi18n.setLanguage(event.target.value);
    window.location.reload();
  });
});


function renderPersonalSchedule() {
  const container=$('personal-schedule');
  const item=(S.current.journey_schedule || []).find(x=>x.user_id===S.user.id);
  container.hidden=!item;
  if(!item)return;
  const names={departure_passed:ui('Scheduled departure has passed; update your journey status','L’heure de départ est passée ; actualisez votre statut'),scheduled:ui('Scheduled','Prévu'),awaiting_confirmation:ui('Awaiting group confirmation','Confirmation du groupe attendue'),ready_to_leave:ui('Departure time reached','Heure de départ atteinte'),travelling:ui('On my way','En route'),arrived:ui('Arrived','Arrivé')};
  const confirmed=['confirmed','travelling'].includes(S.current.meeting.status);
  if(item.state==='ready_to_leave'){
    const key=`departure-notified:${S.user.id}:${S.current.meeting.id}:${S.current.meeting.selected_proposal_id}`;
    if(!localStorage.getItem(key)){localStorage.setItem(key,'1');toast(ui('It is time for your departure. Your group keeps its own departure times.','Il est l’heure de votre départ. Les autres gardent leurs propres horaires.'));}
  }
  container.innerHTML=`<strong>${esc(ui('Your journey','Votre trajet'))}</strong><p>${esc(ui('Leave at','Départ à'))} <b>${esc(time(item.departure))}</b> · ${esc(ui('Arrive at','Arrivée à'))} ${esc(time(item.arrival))} · ${esc(ui('Meeting','Rencontre'))} ${esc(time(item.meeting_start))}</p><p>${esc(names[item.state] || item.state)}</p>${confirmed?`<div class="buttons"><button type="button" data-state="travelling" class="secondary">${esc(ui("I’m leaving","Je pars"))}</button><button type="button" data-state="arrived" class="secondary">${esc(ui("I’ve arrived","Je suis arrivé"))}</button></div>`:''}`;
  container.querySelectorAll('[data-state]').forEach(b=>b.onclick=()=>act(b,async()=>{S.current=await api(`/meetings/${S.current.meeting.id}/journey-state`,{method:'POST',body:{state:b.dataset.state}});renderMeeting();}));
}
$('departure-explanation').textContent=ui('Available from is your earliest possible departure. Your recommended leave-at time is calculated separately after choosing the meeting.','Disponible à partir de signifie votre départ possible le plus tôt. Votre heure de départ conseillée est calculée séparément pour la rencontre.');
$('venue-enabled-label').textContent=ui('Use this place in meeting calculations','Utiliser ce lieu dans les calculs');
$('boarding-label').textContent=ui('Boarding margin (minutes)','Marge avant embarquement (minutes)');
$('attendance-label').textContent=ui('Meeting attendance window (optional)','Disponibilité pour la rencontre (facultatif)');
$('verify-walks').textContent=ui('Verify walking routes (slower)','Vérifier les trajets à pied (plus lent)');
