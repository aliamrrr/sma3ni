/* Citizen page: record or upload a voice note, send it, track it. No framework, no build. */
(() => {
  'use strict';

  const MAX_SECONDS = 180;
  const MAX_BYTES = 10 * 1024 * 1024;
  const BARS = 48;
  const $ = (id) => document.getElementById(id);

  // ── i18n (French / Darija) ──────────────────────────────────────────────
  const T = {
    fr: {
      nav_send: 'Envoyer', nav_track: 'Suivre', nav_agent: 'Espace agent',
      hero: 'Dites-le en darija.<br>On le transmet au <em>bon service</em>.',
      lede: "Une note vocale suffit : pas de formulaire, pas de file d'attente. Vous recevez un code pour suivre votre demande.",
      s1: 'Votre message', s2: 'Pour vous recontacter', optional: '(optionnel)', s3: 'Consentement', s4: 'Suivre une demande',
      hint_idle: 'Appuyez et parlez, 3 minutes maximum', hint_rec: "Enregistrement… appuyez pour arrêter",
      hint_ready: 'Écoutez avant d’envoyer', hint_file: 'Fichier prêt',
      retake: 'Recommencer', upload: 'ou importer un fichier audio',
      phone: 'Téléphone', region: 'Région', choose: 'Choisir…',
      consent: "J'accepte que ma note vocale soit transcrite et transmise au service concerné. L'audio est supprimé après 7 jours, mon numéro est chiffré.",
      submit: 'Envoyer la demande', sending: 'Envoi…',
      sent_label: 'Demande envoyée', sent_title: "C'est envoyé.", copy: 'Copier', copied: 'Copié',
      keep_code: 'Gardez ce code : il permet de suivre votre demande ci-dessous.', again: 'Nouvelle demande',
      code_label: 'Code de suivi', track_btn: 'Suivre', recent: 'Vos demandes récentes',
      service_label: 'Service en charge', updated_label: 'Mise à jour',
      steps: ['Reçue', 'Analyse', 'Transmise', 'En traitement', 'Terminée'],
      m1k: 'Langues', m1v: 'Darija, hassaniya, arabe, avec du français',
      m2k: 'Délai', m2v: 'Analyse en quelques minutes',
      m3k: 'Vos données', m3v: 'Audio supprimé après 7 jours, numéro chiffré',
      footer: "Ce n'est pas un service d'urgence. Urgences : <strong>15 · 19 · 150</strong>",
      e_mic: 'Micro inaccessible. Autorisez-le dans le navigateur, ou importez un fichier.',
      e_short: 'Message trop court, parlez au moins une seconde.', e_size: 'Fichier trop lourd (10 Mo maximum).',
      e_format: 'Format audio non reconnu.', e_rate: 'Trop de demandes depuis cette connexion. Réessayez dans un moment.',
      e_generic: 'Une erreur est survenue. Réessayez.', e_code: 'Code incomplet. Format : SM-XXXXX-XXXXX',
      e_notfound: 'Aucune demande avec ce code.', e_consent: 'Cochez la case de consentement pour envoyer.',
      lang_other: 'العربية', locale: 'fr-MA',
    },
    ar: {
      nav_send: 'صيفط', nav_track: 'تبع', nav_agent: 'فضاء الموظف',
      hero: 'هضر بالدارجة.<br>و حنا نوصلوها <em>للمصلحة المعنية</em>.',
      lede: 'غير ميساج صوتي: بلا استمارة، بلا صف. غادي توصلك رمز باش تتبع الطلب ديالك.',
      s1: 'الميساج ديالك', s2: 'باش نتواصلو معاك', optional: '(اختياري)', s3: 'الموافقة', s4: 'تبع شي طلب',
      hint_idle: 'ضغط و هضر، 3 دقايق على الأكثر', hint_rec: 'كنسجلو… ضغط باش توقف',
      hint_ready: 'سمع قبل ما تصيفط', hint_file: 'الملف واجد',
      retake: 'عاود من الأول', upload: 'ولا زيد ملف صوتي',
      phone: 'التيليفون', region: 'الجهة', choose: 'ختار…',
      consent: 'كنقبل يتكتب الميساج الصوتي ديالي و يتصيفط للمصلحة المعنية. الأوديو كيتمسح من بعد 7 أيام، و الرقم ديالي مشفر.',
      submit: 'صيفط الطلب', sending: 'كنصيفطو…',
      sent_label: 'الطلب تصيفط', sent_title: 'تصيفط.', copy: 'نسخ', copied: 'تنسخ',
      keep_code: 'حتافظ على هاد الرمز، بيه تقدر تتبع الطلب ديالك هنا لتحت.', again: 'طلب جديد',
      code_label: 'رمز التتبع', track_btn: 'تبع', recent: 'الطلبات ديالك الأخيرة',
      service_label: 'المصلحة المكلفة', updated_label: 'آخر تحديث',
      steps: ['توصلنا بيه', 'كنحللوه', 'تصيفط', 'كيتعالج', 'سالا'],
      m1k: 'اللغات', m1v: 'الدارجة، الحسانية، العربية، و شوية ديال الفرنسية',
      m2k: 'المدة', m2v: 'التحليل فشي دقايق',
      m3k: 'المعطيات ديالك', m3v: 'الأوديو كيتمسح من بعد 7 أيام، و الرقم مشفر',
      footer: 'هادي ماشي خدمة ديال الطوارئ. الطوارئ: <strong>15 · 19 · 150</strong>',
      e_mic: 'الميكرو ما خدامش. سمح ليه فالمتصفح، ولا زيد ملف صوتي.',
      e_short: 'الميساج قصير بزاف، هضر على الأقل ثانية.', e_size: 'الملف كبير بزاف (10 ميغا على الأكثر).',
      e_format: 'هاد النوع ديال الأوديو ما معروفش.', e_rate: 'بزاف ديال الطلبات من هاد الكونيكسيون. عاود من بعد شوية.',
      e_generic: 'وقع شي مشكل. عاود جرب.', e_code: 'الرمز ناقص. الشكل: SM-XXXXX-XXXXX',
      e_notfound: 'ما كاين حتى طلب بهاد الرمز.', e_consent: 'خاصك توافق باش تصيفط.',
      lang_other: 'Français', locale: 'ar-MA',
    },
  };
  const REGIONS = [
    ['Tanger-Tétouan-Al Hoceïma', 'طنجة تطوان الحسيمة'], ["L'Oriental", 'الشرق'], ['Fès-Meknès', 'فاس مكناس'],
    ['Rabat-Salé-Kénitra', 'الرباط سلا القنيطرة'], ['Béni Mellal-Khénifra', 'بني ملال خنيفرة'],
    ['Casablanca-Settat', 'الدار البيضاء سطات'], ['Marrakech-Safi', 'مراكش آسفي'], ['Drâa-Tafilalet', 'درعة تافيلالت'],
    ['Souss-Massa', 'سوس ماسة'], ['Guelmim-Oued Noun', 'كلميم واد نون'],
    ['Laâyoune-Sakia El Hamra', 'العيون الساقية الحمراء'], ['Dakhla-Oued Ed-Dahab', 'الداخلة وادي الذهب'],
  ];

  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  };
  let lang = store.get('sma3ni.lang', 'fr') === 'ar' ? 'ar' : 'fr';
  const t = (k) => T[lang][k];

  function applyLang() {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
    document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
    // Only our own static strings go through innerHTML (never user or API data).
    document.querySelectorAll('[data-i18n-html]').forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
    $('lang').textContent = t('lang_other');
    $('lang').lang = lang === 'ar' ? 'fr' : 'ar';
    const region = $('region');
    const current = region.value;
    region.replaceChildren(new Option(t('choose'), ''));
    REGIONS.forEach(([fr, ar]) => region.add(new Option(lang === 'ar' ? ar : fr, fr)));
    region.value = current;
    setHint();
    renderTimeline(lastStage);
    renderRecent();
    if (lastTrack) renderTrack(lastTrack);
  }
  $('lang').addEventListener('click', () => { lang = lang === 'ar' ? 'fr' : 'ar'; store.set('sma3ni.lang', lang); applyLang(); });

  // ── Recorder ────────────────────────────────────────────────────────────
  const recBtn = $('rec');
  const levels = $('levels');
  for (let i = 0; i < BARS; i++) levels.appendChild(document.createElement('i'));
  const bars = [...levels.children];
  let state = 'idle'; // idle | recording | ready
  let source = 'none'; // record | file
  let recorder, stream, chunks, started, tick, raf, audioCtx, analyser, audioBlob, objectUrl, idemKey;
  const history = new Array(BARS).fill(0);

  const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  function setHint() {
    const key = state === 'recording' ? 'hint_rec' : state === 'ready' ? (source === 'file' ? 'hint_file' : 'hint_ready') : 'hint_idle';
    $('rec-hint').textContent = t(key);
  }
  function setState(next) {
    state = next;
    recBtn.dataset.state = next;
    $('ico-mic').hidden = next === 'recording';
    $('ico-stop').hidden = next !== 'recording';
    recBtn.setAttribute('aria-label', next === 'recording' ? 'Stop' : 'Enregistrer');
    levels.classList.toggle('live', next === 'recording');
    $('preview').hidden = next !== 'ready';
    setHint();
    updateSubmit();
  }
  function drawLevels() {
    const buf = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(buf);
    let sum = 0;
    for (const v of buf) { const x = (v - 128) / 128; sum += x * x; }
    history.push(Math.min(1, Math.sqrt(sum / buf.length) * 4));
    history.shift();
    bars.forEach((b, i) => { b.style.height = `${Math.max(2, history[i] * 36)}px`; });
    const elapsed = (performance.now() - started) / 1000;
    $('rec-time').textContent = fmt(elapsed);
    if (elapsed >= MAX_SECONDS) stopRecording();
    else raf = requestAnimationFrame(drawLevels);
  }
  async function startRecording() {
    $('send-error').textContent = '';
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      $('send-error').textContent = t('e_mic');
      return;
    }
    const types = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'];
    const mimeType = types.find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m));
    recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    chunks = [];
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
      const seconds = (performance.now() - started) / 1000;
      if (seconds < 1 || blob.size < 1024) { reset(); $('send-error').textContent = t('e_short'); return; }
      useAudio(blob, 'record');
    };
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    audioCtx.createMediaStreamSource(stream).connect(analyser);
    started = performance.now();
    recorder.start(250);
    setState('recording');
    raf = requestAnimationFrame(drawLevels);
  }
  function stopRecording() {
    cancelAnimationFrame(raf);
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    stream && stream.getTracks().forEach((tr) => tr.stop());
    audioCtx && audioCtx.close();
  }
  function useAudio(blob, from) {
    if (blob.size > MAX_BYTES) { $('send-error').textContent = t('e_size'); return; }
    audioBlob = blob;
    source = from;
    idemKey = crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random();
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(blob);
    $('player').src = objectUrl;
    setState('ready');
  }
  function reset() {
    audioBlob = null; source = 'none';
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
    $('player').removeAttribute('src');
    history.fill(0);
    bars.forEach((b) => { b.style.height = '2px'; });
    $('rec-time').textContent = '00:00';
    $('file').value = '';
    setState('idle');
  }
  recBtn.addEventListener('click', () => {
    if (state === 'recording') stopRecording();
    else { reset(); startRecording(); }
  });
  $('retake').addEventListener('click', () => { reset(); });
  $('file').addEventListener('change', (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    $('send-error').textContent = '';
    $('rec-time').textContent = '';
    useAudio(f, 'file');
  });

  // ── Send ────────────────────────────────────────────────────────────────
  const consent = $('consent');
  function updateSubmit() { $('submit').disabled = !(state === 'ready' && audioBlob); }
  consent.addEventListener('change', () => { if (consent.checked) $('send-error').textContent = ''; });

  const extFor = (type) => (type.includes('ogg') ? 'ogg' : type.includes('mp4') || type.includes('m4a') ? 'm4a'
    : type.includes('mpeg') ? 'mp3' : type.includes('wav') ? 'wav' : 'webm');

  $('send-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!audioBlob) return;
    if (!consent.checked) { $('send-error').textContent = t('e_consent'); consent.focus(); return; }
    const btn = $('submit');
    btn.disabled = true;
    btn.firstElementChild.textContent = t('sending');
    $('send-error').textContent = '';
    const body = new FormData();
    body.append('audio', audioBlob, audioBlob.name || `note.${extFor(audioBlob.type || '')}`);
    body.append('consent', 'true');
    if ($('contact').value.trim()) body.append('contact', $('contact').value.trim());
    if ($('region').value) body.append('region', $('region').value);
    try {
      const res = await fetch('/v1/public/requests', { method: 'POST', body, headers: { 'Idempotency-Key': idemKey } });
      if (!res.ok) {
        const map = { 413: 'e_size', 415: 'e_format', 429: 'e_rate' };
        throw new Error(t(map[res.status] || 'e_generic'));
      }
      const data = await res.json();
      remember(data.tracking_code);
      $('sent-code').textContent = data.tracking_code;
      $('send-form').hidden = true;
      $('sent').hidden = false;
      $('sent').scrollIntoView({ behavior: 'smooth', block: 'start' });
      $('track-code').value = data.tracking_code;
      track(data.tracking_code);
    } catch (err) {
      $('send-error').textContent = err.message || t('e_generic');
    } finally {
      btn.firstElementChild.textContent = t('submit');
      updateSubmit();
    }
  });
  $('copy').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText($('sent-code').textContent);
      $('copy').textContent = t('copied');
      setTimeout(() => { $('copy').textContent = t('copy'); }, 1600);
    } catch { /* clipboard blocked: the code stays visible */ }
  });
  $('again').addEventListener('click', () => {
    reset();
    consent.checked = false;
    $('sent').hidden = true;
    $('send-form').hidden = false;
    $('envoyer').scrollIntoView({ behavior: 'smooth' });
  });

  // ── Track ───────────────────────────────────────────────────────────────
  const STAGES = ['received', 'analysing', 'routed', 'in_progress', 'done'];
  const CODE_RE = /^SM-[2-9A-HJ-NP-Z]{5}-[2-9A-HJ-NP-Z]{5}$/;
  let lastStage = null;
  let lastTrack = null;
  let poll;

  function renderTimeline(stage) {
    const idx = stage ? STAGES.indexOf(stage) : -1;
    $('timeline').replaceChildren(...t('steps').map((label, i) => {
      const li = document.createElement('li');
      li.textContent = label;
      if (i < idx || (stage === 'done' && i === idx)) li.className = 'done';
      else if (i === idx) li.className = 'current';
      return li;
    }));
  }
  function renderTrack(d) {
    lastStage = d.stage;
    renderTimeline(d.stage);
    $('tr-code').textContent = d.tracking_code;
    $('tr-service').textContent = (lang === 'ar' ? d.service_ar : d.service) || '—';
    $('tr-updated').textContent = new Date(d.updated_at).toLocaleString(t('locale'), { dateStyle: 'medium', timeStyle: 'short' });
    $('track-result').hidden = false;
  }
  function normalizeCode(v) {
    const raw = v.toUpperCase().replace(/[^0-9A-Z]/g, '').replace(/^SM/, '').slice(0, 10);
    if (!raw) return '';
    return `SM-${raw.slice(0, 5)}${raw.length > 5 ? `-${raw.slice(5)}` : ''}`;
  }
  async function track(code) {
    clearTimeout(poll);
    $('track-error').textContent = '';
    if (!CODE_RE.test(code)) { $('track-error').textContent = t('e_code'); return; }
    try {
      const res = await fetch(`/v1/track/${encodeURIComponent(code)}`);
      if (res.status === 404) { $('track-result').hidden = true; $('track-error').textContent = t('e_notfound'); return; }
      if (!res.ok) throw new Error();
      lastTrack = await res.json();
      renderTrack(lastTrack);
      if (lastTrack.stage !== 'done') poll = setTimeout(() => track(code), 8000);
    } catch {
      $('track-error').textContent = t('e_generic');
    }
  }
  $('track-code').addEventListener('input', (e) => { e.target.value = normalizeCode(e.target.value); });
  $('track-form').addEventListener('submit', (e) => { e.preventDefault(); track($('track-code').value); });

  // Recent codes stay on this device only (convenience, not a source of truth).
  function remember(code) {
    const list = [code, ...store.get('sma3ni.codes', []).filter((c) => c !== code)].slice(0, 5);
    store.set('sma3ni.codes', list);
    renderRecent();
  }
  function renderRecent() {
    const codes = store.get('sma3ni.codes', []).filter((c) => CODE_RE.test(c));
    const ul = $('recent');
    ul.hidden = codes.length === 0;
    ul.replaceChildren(...codes.map((c) => {
      const li = document.createElement('li');
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'pill'; b.textContent = c;
      b.addEventListener('click', () => { $('track-code').value = c; track(c); });
      li.appendChild(b);
      return li;
    }));
    ul.setAttribute('aria-label', t('recent'));
  }

  // Active nav marker follows the section in view.
  const navLinks = [...document.querySelectorAll('.nav a[href^="#"]')];
  const io = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (en.isIntersecting) navLinks.forEach((a) => a.setAttribute('aria-current', String(a.hash === `#${en.target.id}`)));
    });
  }, { rootMargin: '-40% 0px -55% 0px' });
  ['envoyer', 'suivre'].forEach((id) => io.observe($(id)));

  applyLang();
  setState('idle');
  if (!window.MediaRecorder || !navigator.mediaDevices) { recBtn.disabled = true; $('rec-hint').textContent = t('e_mic'); }
})();
