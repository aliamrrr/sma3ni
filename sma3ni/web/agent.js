/* Agent console. All user/API data is rendered with textContent (transcripts are untrusted input). */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const KEY_STORE = 'sma3ni.agent.key';
  const QUEUES = [
    { id: 'todo', label: 'À traiter', q: { status: 'ROUTED' } },
    { id: 'review', label: 'À revoir', q: { status: 'ROUTED', needs_review: 'true' } },
    { id: 'doing', label: 'En cours', q: { status: 'IN_PROGRESS' } },
    { id: 'failed', label: 'Échecs', q: { status: 'FAILED' } },
    { id: 'done', label: 'Traitées', q: { status: 'RESOLVED' } },
    { id: 'all', label: 'Toutes', q: {} },
  ];
  const CATEGORIES = {
    etat_civil: 'État civil', urbanisme: 'Urbanisme', eau_electricite: 'Eau et électricité',
    proprete_voirie: 'Propreté et voirie', sante: 'Santé', protection_sociale: 'Protection sociale',
    identite: 'Identité', integrite: 'Intégrité', danger: 'Danger', autre: 'Non classée',
  };
  const STATUS = {
    RECEIVED: 'Reçue', TRANSCRIBING: 'Transcription', TRANSCRIBED: 'Transcrite', ROUTED: 'À traiter',
    IN_PROGRESS: 'En cours', RESOLVED: 'Traitée', REJECTED: 'Clôturée', FAILED: 'Échec',
  };
  const LANGS = {
    darija: 'Darija', hassaniya: 'Hassaniya', msa: 'Arabe standard', amazigh: 'Amazigh',
    arabic_other: 'Autre dialecte arabe', other: 'Autre langue', unknown: 'Inconnue',
  };
  const REASONS = {
    empty_transcript: 'Transcription vide', low_language_confidence: 'Langue incertaine',
    no_rule_matched: 'Aucune catégorie trouvée', ambiguous_category: 'Catégorie ambiguë',
  };
  const CHANNELS = { web: 'Site web', whatsapp: 'WhatsApp', call_center: 'Centre d’appel', kiosk: 'Borne', mobile: 'Application' };
  const ACTIONS = {
    ROUTED: [['IN_PROGRESS', 'Prendre en charge', true], ['RESOLVED', 'Marquer traitée'], ['REJECTED', 'Clôturer sans suite']],
    IN_PROGRESS: [['RESOLVED', 'Marquer traitée', true], ['REJECTED', 'Clôturer sans suite']],
    FAILED: [['IN_PROGRESS', 'Prendre en charge', true], ['REJECTED', 'Clôturer sans suite']],
  };

  let key = null;
  let me = null;
  let services = {};
  let queue = QUEUES[0];
  let items = [];
  let cursor = null;
  let selected = null;
  let audioUrl = null;
  let refreshTimer;

  // ── helpers ──
  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    });
    children.flat().forEach((c) => c != null && node.append(c));
    return node;
  }
  const rtf = new Intl.RelativeTimeFormat('fr', { numeric: 'auto' });
  function ago(iso) {
    const s = (new Date(iso) - Date.now()) / 1000;
    const units = [['day', 86400], ['hour', 3600], ['minute', 60]];
    for (const [u, n] of units) if (Math.abs(s) >= n) return rtf.format(Math.round(s / n), u);
    return 'à l’instant';
  }
  const dt = (iso) => new Date(iso).toLocaleString('fr-MA', { dateStyle: 'medium', timeStyle: 'short' });
  const svcName = (code) => (services[code] && services[code].name_fr) || code || '—';

  async function api(path, opts = {}) {
    const res = await fetch(path, { ...opts, headers: { ...(opts.headers || {}), Authorization: `Bearer ${key}` } });
    if (res.status === 401) { logout(); throw new Error('Session expirée'); }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(typeof body.detail === 'string' ? body.detail : `Erreur ${res.status}`);
    }
    return res;
  }

  // ── auth ──
  function readKey() { try { return sessionStorage.getItem(KEY_STORE); } catch { return null; } }
  function writeKey(v) { try { v ? sessionStorage.setItem(KEY_STORE, v) : sessionStorage.removeItem(KEY_STORE); } catch { /* ignore */ } }
  function logout() {
    writeKey(null); key = null; clearInterval(refreshTimer);
    $('console').hidden = true; $('login').hidden = false; $('key').value = ''; $('key').focus();
  }
  async function login(candidate) {
    key = candidate;
    const res = await fetch('/v1/me', { headers: { Authorization: `Bearer ${key}` } });
    if (!res.ok) throw new Error('Clé invalide ou révoquée.');
    me = await res.json();
    if (!me.scopes.includes('agent') && !me.scopes.includes('admin')) throw new Error('Cette clé n’a pas accès à l’espace agent.');
    writeKey(key);
    const list = await (await api('/v1/services')).json();
    services = Object.fromEntries(list.map((s) => [s.code, s]));
    $('who-name').textContent = me.name;
    $('who-service').textContent = me.service_code ? svcName(me.service_code) : 'Tous les services';
    $('login').hidden = true; $('console').hidden = false;
    renderQueues();
    await loadList(true);
    refreshTimer = setInterval(() => loadList(true, true), 15000);
  }
  $('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    $('login-error').textContent = '';
    try { await login($('key').value.trim()); } catch (err) { $('login-error').textContent = err.message; }
  });
  $('logout').addEventListener('click', logout);

  // ── list ──
  function renderQueues() {
    $('queues').replaceChildren(...QUEUES.map((q) => el('button', {
      type: 'button', text: q.label, 'aria-current': String(q.id === queue.id),
      onclick: () => { queue = q; renderQueues(); loadList(true); },
    })));
    $('list-title').textContent = queue.label;
  }
  async function loadList(fresh, silent = false) {
    const params = new URLSearchParams({ ...queue.q, limit: '50' });
    if (!fresh && cursor) params.set('before', cursor);
    try {
      const data = await (await api(`/v1/requests?${params}`)).json();
      items = fresh ? data.items : items.concat(data.items);
      cursor = data.next_before;
      renderList();
    } catch (err) {
      if (!silent) $('list-count').textContent = err.message;
    }
  }
  function renderList() {
    $('list-count').textContent = `${items.length}${cursor ? '+' : ''}`;
    $('list-empty').hidden = items.length > 0;
    $('more-row').hidden = !cursor;
    $('rows').replaceChildren(...items.map((it) => {
      const ex = it.transcript_excerpt
        ? el('div', { class: 'ex', lang: 'ar', text: it.transcript_excerpt })
        : el('div', { class: 'ex empty', text: STATUS[it.status] === 'Échec' ? 'Échec de l’analyse, à traiter manuellement' : 'Transcription en attente' });
      const cap = el('div', { class: 'cap' },
        el('span', { class: 't', text: CATEGORIES[it.category] || 'Non classée' }),
        el('span', { class: 's', text: '/' }),
        el('span', { class: 'g', text: svcName(it.service_code) }),
        it.lang_family ? el('span', { class: 'g', text: `· ${LANGS[it.lang_family] || it.lang_family}` }) : null,
        it.needs_review ? el('span', { class: 'flag', text: '· à revoir' }) : null);
      const row = el('li', { role: 'option', 'aria-selected': String(it.id === selected) },
        el('button', { type: 'button', class: 'row', 'aria-selected': String(it.id === selected), onclick: () => open(it.id) },
          el('div', { class: 'top' },
            el('span', { class: 'code-s' }, it.priority === 1 ? el('span', { class: 'prio', title: 'Prioritaire' }) : null, it.tracking_code),
            el('span', { class: 'mono', text: ago(it.created_at) })),
          ex, cap));
      return row;
    }));
  }
  $('more').addEventListener('click', () => loadList(false));

  // ── detail ──
  async function open(id) {
    selected = id;
    renderList();
    $('console').dataset.view = 'detail';
    $('d-error').textContent = '';
    if (audioUrl) { URL.revokeObjectURL(audioUrl); audioUrl = null; }
    try {
      const r = await (await api(`/v1/requests/${id}`)).json();
      renderDetail(r);
    } catch (err) {
      $('detail-empty').hidden = false; $('d').hidden = true; $('detail-empty').textContent = err.message;
    }
  }
  function cell(k, v) { return el('div', { class: 'cell' }, el('span', { class: 'label', text: k }), el('span', { text: v ?? '—' })); }
  function renderDetail(r) {
    $('detail-empty').hidden = true; $('d').hidden = false;
    $('d-code').textContent = r.tracking_code;
    $('d-status').textContent = STATUS[r.status] || r.status;
    $('d-status').dataset.s = r.status;
    $('d-title').textContent = CATEGORIES[r.category] || (r.status === 'FAILED' ? 'Analyse en échec' : 'Non classée');
    $('d-sub').replaceChildren(
      el('span', { class: 'label', text: svcName(r.service_code) }),
      r.priority === 1 ? el('span', { class: 'flag', text: 'Prioritaire' }) : null,
      el('span', { class: 'mono', text: `${dt(r.created_at)} · ${ago(r.created_at)}` }));

    const tr = $('d-transcript');
    tr.textContent = r.transcript || (r.failure_reason ? `Pas de transcription (${r.failure_reason}). Écoutez l’audio.` : 'Transcription en cours…');
    tr.className = r.transcript ? 'transcript' : 'transcript empty';

    const purged = !!r.audio_purged_at;
    $('d-listen').replaceChildren(purged
      ? el('span', { class: 'mono', text: `Audio supprimé le ${dt(r.audio_purged_at)} (conservation limitée)` })
      : el('button', { class: 'btn sm', type: 'button', text: 'Écouter l’audio', onclick: () => playAudio(r.id) }));

    const chips = [];
    if (r.needs_review) chips.push(el('span', { class: 'chip warn', text: 'À revoir' }));
    (r.review_reasons || []).forEach((code) => {
      const text = code.startsWith('language_not_supported_by_asr')
        ? `Langue non couverte : ${LANGS[code.split(':')[1]] || code.split(':')[1]}` : (REASONS[code] || code);
      chips.push(el('span', { class: 'chip', text }));
    });
    $('d-chips').replaceChildren(...chips);

    const conf = r.lang_confidence != null ? ` · ${Math.round(r.lang_confidence * 100)} %` : '';
    $('d-grid').replaceChildren(
      cell('Dialecte', r.lang_family ? `${LANGS[r.lang_family] || r.lang_family}${conf}` : null),
      cell('Canal', CHANNELS[r.channel] || r.channel),
      cell('Région', r.region),
      cell('Contact', r.contact),
      cell('Durée audio', r.audio_seconds ? `${Math.round(r.audio_seconds)} s` : null),
      cell('Mise à jour', ago(r.updated_at)));

    const buttons = (ACTIONS[r.status] || []).map(([to, label, primary]) => el('button', {
      class: `btn sm${primary ? ' primary' : ''}`, type: 'button', text: label, onclick: () => update(r.id, { status: to }),
    }));
    $('d-buttons').replaceChildren(...buttons);
    $('d-note').closest('.field').hidden = buttons.length === 0;

    const canMove = (me.service_code == null || me.service_code === 'triage' || me.scopes.includes('admin'))
      && !['RECEIVED', 'TRANSCRIBING', 'TRANSCRIBED'].includes(r.status);
    $('d-reassign').hidden = !canMove;
    if (canMove) {
      $('d-service').replaceChildren(...Object.values(services).map((s) => new Option(s.name_fr, s.code, false, s.code === r.service_code)));
      $('d-move').onclick = () => update(r.id, { service_code: $('d-service').value });
    }

    $('d-history').replaceChildren(...(r.history || []).slice().reverse().map((h) => el('li', {},
      el('span', { class: 'mono', text: dt(h.at) }),
      el('span', { text: `${h.from_status && h.from_status !== h.to_status ? `${STATUS[h.from_status] || h.from_status} → ` : ''}${STATUS[h.to_status] || h.to_status}${h.note ? ` · ${h.note}` : ''} (${h.actor.replace(/^key:/, '')})` }))));
  }
  async function playAudio(id) {
    try {
      const blob = await (await api(`/v1/requests/${id}/audio`)).blob();
      audioUrl = URL.createObjectURL(blob);
      const audio = el('audio', { controls: '', src: audioUrl });
      $('d-listen').replaceChildren(audio);
      audio.play().catch(() => {});
    } catch (err) { $('d-error').textContent = err.message; }
  }
  async function update(id, body) {
    $('d-error').textContent = '';
    const note = $('d-note').value.trim();
    if (note && body.status) body.note = note;
    try {
      await api(`/v1/requests/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      $('d-note').value = '';
      await Promise.all([open(id), loadList(true, true)]);
    } catch (err) { $('d-error').textContent = err.message; }
  }
  $('back').addEventListener('click', () => { $('console').dataset.view = 'list'; });

  document.addEventListener('keydown', (e) => {
    if ($('console').hidden || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const i = items.findIndex((it) => it.id === selected);
    const next = items[Math.min(items.length - 1, Math.max(0, i + (e.key === 'ArrowDown' ? 1 : -1)))];
    if (next) open(next.id);
  });

  const saved = readKey();
  if (saved) login(saved).catch(() => logout());
  else logout();
})();
