/*
 * كذّاب — the screens.
 *
 * Every screen is drawn from the latest room snapshot, whoever sent it: the
 * room running on this phone (host, or a game against the computer) or the
 * host's phone over the network. The only state kept here is what is local
 * by nature - which cards are selected, which rank is about to be claimed,
 * and which events have already been animated.
 */
(function () {
  'use strict';

  const K = window.Kazzab;
  const E = K.Engine, Room = K.Room, Net = K.Net, A = K.Audio;
  const VERSION = '0.1.0';
  const $ = (id) => document.getElementById(id);

  // ------------------------------------------------------------ Arabic text

  const RANK_WORD = ['آس', 'اثنين', 'ثلاثة', 'أربعة', 'خمسة', 'ستة', 'سبعة', 'ثمانية', 'تسعة', 'عشرة', 'ولد', 'بنت', 'شايب'];
  const COUNT_WORD = ['', 'ورقة واحدة', 'ورقتين', 'ثلاث أوراق', 'أربع أوراق'];
  const SUIT_SYM = ['♠', '♥', '♦', '♣'];
  const FACE_WORD = { 10: 'ولد', 11: 'بنت', 12: 'شايب' };
  const claimText = (count, rank) => COUNT_WORD[count] + ' ' + RANK_WORD[rank];
  const cardsWord = (n) => n === 1 ? 'ورقة واحدة' : n === 2 ? 'ورقتين' : (n >= 3 && n <= 10) ? n + ' أوراق' : n + ' ورقة';
  const toArabicDigits = (s) => String(s).replace(/\d/g, (d) => '٠١٢٣٤٥٦٧٨٩'[d]);

  const SETTINGS_UI = [
    { key: 'rankMode', label: 'طريقة الإعلان', options: [['round', 'رتبة واحدة للجولة'], ['free', 'إعلان حر'], ['sequence', 'بالترتيب A→K']],
      desc: {
        round: 'أول لاعب يختار الرتبة، والبقية يعلنون نفسها أو يقولون باص. إذا قال الكل باص تُحرق الكومة.',
        free: 'كل لاعب يعلن أي رتبة يريدها في دوره.',
        sequence: 'الإعلانات بالترتيب: آس ثم ٢ ثم ٣… حتى الشايب ثم من جديد.'
      } },
    { key: 'maxCards', label: 'أقصى عدد أوراق في الدور', options: [[1, '١'], [2, '٢'], [3, '٣'], [4, '٤']] },
    { key: 'starter', label: 'من يبدأ', options: [['ace', 'صاحب آس ♠'], ['random', 'عشوائي'], ['host', 'المضيف']] },
    { key: 'challengeSeconds', label: 'مهلة «كذّاب!»', options: [[4, '٤ ث'], [6, '٦ ث'], [10, '١٠ ث']] },
    { key: 'turnSeconds', label: 'مهلة الدور', options: [[30, '٣٠ ث'], [60, '٦٠ ث'], [0, 'بلا مهلة']] }
  ];

  const ERRORS = {
    started: 'اللعبة بدأت في هذه الغرفة. انتظر الجولة القادمة.',
    full: 'الغرفة ممتلئة (٨ لاعبين).',
    version: 'نسختك من اللعبة تختلف عن نسخة المضيف. حدّث الصفحة أو التطبيق.',
    closed: 'الغرفة أُغلقت.',
    key: 'تعذّر الدخول إلى الغرفة.',
    notfound: 'لا توجد غرفة بهذا الكود. تأكد من الرقم.',
    lost: 'انقطع الاتصال بالمضيف.',
    network: 'تعذّر الاتصال. تأكد من الإنترنت وحاول مرة أخرى.',
    unsupported: 'هذا المتصفح لا يدعم اللعب عبر الإنترنت. جرّب Chrome أو Safari.',
    rank: 'لازم تعلن الرتبة المطلوبة.',
    count: 'عدد الأوراق غير مسموح.'
  };

  // ---------------------------------------------------------------- storage

  const store = {
    get(k, d) {
      try { const v = localStorage.getItem('kz.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; }
    },
    set(k, v) { try { localStorage.setItem('kz.' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } }
  };

  function randomKey() {
    const b = new Uint8Array(12);
    crypto.getRandomValues(b);
    return 'u' + Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  }
  /** Identifies this phone to a host, so a dropped connection gets its seat back. */
  let myKey = store.get('key', null);
  if (!myKey) { myKey = randomKey(); store.set('key', myKey); }

  // ------------------------------------------------------------------ state

  const app = {
    mode: null,          // host | client | solo
    room: null,
    net: null,
    snap: null,
    lastSeq: 0,
    sel: new Set(),
    rank: null,
    rankManual: false,
    timer: null,
    holdEnds: 0,
    handKey: '',
    pileShown: 0,
    claimSeq: 0,
    overSeq: 0,
    revealTimer: null,
    holdTimer: null,
    wake: null
  };

  // ---------------------------------------------------------------- helpers

  function show(id) {
    document.querySelectorAll('.screen').forEach((s) => s.classList.toggle('active', s.id === id));
    if (id === 'game') requestWake(); else releaseWake();
    if (id === 'lobby' || id === 'game') guardBack();
  }

  let toastTimer = null;
  function toast(text, ms) {
    const t = $('toast');
    t.textContent = text;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), ms || 2400);
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function cardEl(id) {
    const r = E.rankOf(id), s = E.suitOf(id);
    const el = document.createElement('div');
    el.className = 'card' + (s === 1 || s === 2 ? ' red' : '');
    el.dataset.id = id;
    const rk = E.RANKS[r], sy = SUIT_SYM[s];
    const ten = r === 9 ? ' ten' : '';
    const center = r >= 10
      ? `<span class="pip face">${rk}<em>${FACE_WORD[r]}</em></span>`
      : `<span class="pip">${sy}</span>`;
    el.innerHTML = `<span class="ix${ten}">${rk}<small>${sy}</small></span>${center}<span class="ix bl${ten}">${rk}<small>${sy}</small></span>`;
    return el;
  }

  function backEl() {
    const el = document.createElement('div');
    el.className = 'card back';
    return el;
  }

  function memberOf(s, id) { return s.members.find((m) => m.id === id) || null; }
  function seatName(s, seat) {
    if (seat === s.game.me) return 'أنت';
    return s.game.players[seat] ? s.game.players[seat].name : '؟';
  }
  function seatAvatar(s, seat) {
    const m = memberOf(s, s.game.players[seat].id);
    return m ? m.avatar : '🙂';
  }
  const isHost = () => !!app.snap && app.snap.host === app.snap.you;
  const holding = () => Date.now() < app.holdEnds;

  // ------------------------------------------------------------- messaging

  function send(msg) {
    if (app.mode === 'client') {
      if (!app.net || !app.net.send(msg)) toast('لا يوجد اتصال… لحظة');
    } else if (app.room) {
      app.room.handle(myKey, msg);
    }
  }

  /** The room on this phone talks to its own screen through here, one message at a time. */
  function hostSend(key, msg) {
    if (key === myKey) Promise.resolve().then(() => onMessage(msg));
    else if (app.net && app.mode === 'host') app.net.send(key, msg);
  }

  function onMessage(msg) {
    if (!app.mode) return;
    switch (msg.t) {
      case 'room': onSnapshot(msg); break;
      case 'react': onReact(msg.id, msg.e); break;
      case 'error':
        if (!app.snap) endSession(ERRORS[msg.code] || ERRORS.key);
        else if (ERRORS[msg.code]) toast(ERRORS[msg.code]);
        break;
      case 'kicked': endSession('أخرجك المضيف من الغرفة.'); break;
      case 'closed': endSession('أغلق المضيف الغرفة.'); break;
    }
  }

  // --------------------------------------------------------------- sessions

  function profile() {
    return { name: Room.cleanName($('name').value) || 'لاعب', avatar: store.get('avatar', Room.AVATARS[0]) };
  }

  function needName() {
    if (Room.cleanName($('name').value)) return false;
    toast('اكتب اسمك أولاً');
    $('name').focus();
    return true;
  }

  function startHost() {
    if (needName()) return;
    resetSession('host');
    $('conn-text').textContent = 'جارٍ إنشاء الغرفة…';
    show('connecting');
    const me = profile();
    const net = new Net.NetHost({
      onOpen(code) {
        if (app.net !== net) return;
        app.room = new Room({
          code, hostKey: myKey, hostName: me.name, hostAvatar: me.avatar,
          settings: store.get('settings', null), send: hostSend
        });
        net.setRoom(app.room);
        app.room.update();
      },
      onFail(err) {
        if (app.net !== net) return;
        endSession(err && err.type === 'browser-incompatible' ? ERRORS.unsupported : ERRORS.network);
      },
      onStatus(kind) {
        if (kind === 'broker-lost') setNet('warn');
        else if (kind === 'ok') setNet('ok');
      }
    });
    app.net = net;
    net.open();
  }

  function startClient(code) {
    if (needName()) return;
    code = Net.normalizeCode(code);
    if (code.length !== 6) { toast('الكود ٦ أرقام'); $('code').focus(); return; }
    resetSession('client');
    $('conn-text').textContent = 'جارٍ الدخول إلى الغرفة ' + code + '…';
    show('connecting');
    const me = profile();
    const net = new Net.NetClient({
      code,
      hello: () => ({ t: 'hello', v: Room.PROTOCOL, key: myKey, name: me.name, avatar: me.avatar }),
      onMessage: (m) => { if (app.net === net) onMessage(m); },
      onStatus(state, detail) {
        if (app.net !== net) return;
        if (state === 'connected') setNet('ok');
        else if (state === 'reconnecting') { setNet('warn'); toast('انقطع الاتصال… نحاول من جديد'); }
        else if (state === 'connecting' && !app.snap) $('conn-text').textContent = 'جارٍ الدخول إلى الغرفة ' + code + '…';
        else if (state === 'failed') endSession(ERRORS[detail] || ERRORS.network);
      }
    });
    app.net = net;
    net.connect();
  }

  function startSolo(bots) {
    resetSession('solo');
    const me = profile();
    app.room = new Room({
      code: '', hostKey: myKey, hostName: me.name, hostAvatar: me.avatar,
      settings: store.get('settings', null), send: hostSend
    });
    for (let i = 0; i < bots; i++) app.room.addBot();
    app.room.start();
  }

  function resetSession(mode) {
    app.mode = mode;
    app.snap = null;
    app.lastSeq = 0;
    app.sel.clear();
    app.rank = null;
    app.rankManual = false;
    app.handKey = '';
    app.pileShown = 0;
    app.claimSeq = 0;
    app.overSeq = 0;
    app.timer = null;
    document.body.classList.toggle('is-host', mode !== 'client');
    document.body.classList.toggle('solo', mode === 'solo');
    setNet('ok');
  }

  function endSession(message) {
    const mode = app.mode;
    store.set('lastRoom', null);
    refreshRejoin();
    if (mode === 'client' && app.net) { app.net.send({ t: 'leave' }); app.net.close(); }
    if (mode === 'host' && app.net) app.net.close();
    if (mode === 'solo' && app.room) app.room.close();
    app.mode = null;
    app.net = null;
    app.room = null;
    app.snap = null;
    ['reveal', 'over', 'menu', 'rules'].forEach((id) => { $(id).hidden = true; });
    show('home');
    if (message) toast(message, 4200);
  }

  function setNet(state) {
    ['lobby-net', 'game-net'].forEach((id) => {
      const d = $(id);
      d.className = 'net-dot' + (state === 'warn' ? ' warn' : state === 'bad' ? ' bad' : '');
    });
  }

  // -------------------------------------------------------------- snapshots

  function onSnapshot(s) {
    const prev = app.snap;
    app.snap = s;
    // If this page dies mid-game, the home screen offers the way back to the seat.
    if (app.mode === 'client') store.set('lastRoom', { code: s.code, at: Date.now() });
    const now = Date.now();
    document.body.classList.toggle('is-host', s.host === s.you);
    app.timer = s.timer ? { kind: s.timer.kind, endsAt: now + s.timer.left, total: s.timer.total } : null;
    app.holdEnds = now + (s.hold || 0);
    clearTimeout(app.holdTimer);
    if (s.hold > 0) app.holdTimer = setTimeout(() => { if (app.snap === s) renderGame(s); }, s.hold + 30);

    if (isHost() && app.mode === 'host') store.set('settings', s.settings);
    if (isHost() && app.mode === 'solo' && !s.game) store.set('settings', s.settings);

    if (!s.game) {
      $('over').hidden = true;
      $('reveal').hidden = true;
      app.lastSeq = 0;
      app.handKey = '';
      app.sel.clear();
      show('lobby');
      renderLobby(s);
      return;
    }

    const g = s.game;
    if (!prev) app.lastSeq = g.seq;            // joined mid-game: no replays
    else if (!prev.game || g.seq < app.lastSeq) app.lastSeq = 0;
    const fresh = g.events.filter((e) => e.seq > app.lastSeq);
    app.lastSeq = g.seq;

    // A selection only survives while those cards are still in the hand.
    for (const c of Array.from(app.sel)) if (!g.hand.includes(c)) app.sel.delete(c);
    if (g.required !== null) { app.rank = g.required; app.rankManual = false; }

    show('game');
    renderGame(s);

    const pg = prev && prev.game;
    const myTurn = g.phase === 'play' && g.turn === g.me;
    const wasMyTurn = pg && pg.phase === 'play' && pg.turn === pg.me;
    if (myTurn && !wasMyTurn) { A.play('turn'); A.vibrate(60); }

    // Only the newest reveal is worth showing; older ones were missed while away.
    let lastReveal = -1;
    fresh.forEach((e, i) => { if (e.type === 'reveal') lastReveal = i; });
    fresh.forEach((e, i) => effect(e, s, i === lastReveal));
  }

  function effect(e, s, latest) {
    const g = s.game;
    switch (e.type) {
      case 'start':
        A.play('deal');
        if (e.starter === g.me) toast('أنت تبدأ' + (g.settings.rankMode === 'round' ? ' وتختار الرتبة' : ''));
        else toast('يبدأ ' + seatName(s, e.starter) + (g.settings.rankMode === 'round' ? ' ويختار الرتبة' : ''));
        break;
      case 'play':
        A.play('card');
        A.speak(claimText(e.count, e.rank));
        bubble(e.by, claimText(e.count, e.rank));
        break;
      case 'pass':
        A.play('pass');
        bubble(e.by, 'باص');
        break;
      case 'burn':
        A.play('burn');
        toast('الكل قال باص 🔥 احترقت ' + cardsWord(e.count) + ' — ' +
          (e.starter === g.me ? 'أنت تبدأ جولة جديدة' : 'يبدأ ' + seatName(s, e.starter)));
        break;
      case 'reveal':
        if (latest && s.hold > 0) showReveal(e, s);
        break;
      case 'win':
        A.play('win');
        break;
    }
  }

  // ------------------------------------------------------------------ lobby

  function renderLobby(s) {
    const solo = app.mode === 'solo';
    $('code-card').hidden = solo;
    $('lobby-code').textContent = s.code;
    $('lobby-count').textContent = '(' + s.members.length + '/' + E.MAX_PLAYERS + ')';
    $('btn-add-bot').disabled = s.members.length >= E.MAX_PLAYERS;

    $('members').innerHTML = s.members.map((m) => {
      const tags = [];
      if (m.id === s.host) tags.push('<span class="tag host">👑 المضيف</span>');
      if (m.id === s.you) tags.push('<span class="tag you">أنت</span>');
      if (m.bot) tags.push('<span class="tag">🤖 كمبيوتر</span>');
      const kick = isHost() && m.id !== s.host ? `<button class="kick" data-kick="${esc(m.id)}" aria-label="إخراج">✕</button>` : '';
      return `<li><span class="av">${m.avatar}</span><span class="nm">${esc(m.name)}</span>${tags.join('')}${kick}</li>`;
    }).join('');

    const host = isHost();
    $('settings').innerHTML = SETTINGS_UI.map((u) => {
      const cur = s.settings[u.key];
      const btns = u.options.map(([v, label]) =>
        `<button data-set="${u.key}" data-val="${v}" aria-pressed="${v === cur}" ${host ? '' : 'disabled'}>${label}</button>`).join('');
      const desc = u.desc ? `<p class="desc">${u.desc[cur]}</p>` : '';
      return `<div class="setting"><span class="lbl">${u.label}</span><div class="seg">${btns}</div>${desc}</div>`;
    }).join('');

    const n = s.members.length;
    $('btn-start').disabled = n < E.MIN_PLAYERS;
    $('lobby-need').textContent = n < E.MIN_PLAYERS
      ? 'تحتاج ' + toArabicDigits(E.MIN_PLAYERS - n) + ' لاعب على الأقل — ادعُ أصدقاءك أو أضف كمبيوتر'
      : '';
  }

  function shareRoom() {
    const code = app.snap && app.snap.code;
    if (!code) return;
    const url = shareUrl(code);
    const text = 'تعال العب «كذّاب» معي 🃏\nكود الغرفة: ' + code + (url ? '\n' + url : '');
    if (window.KazzabAndroid && window.KazzabAndroid.share) { window.KazzabAndroid.share(text); return; }
    if (navigator.share) { navigator.share({ title: 'كذّاب', text }).catch(() => {}); return; }
    copyText(text, 'نُسخت الدعوة — الصقها في واتساب');
  }

  function shareUrl(code) {
    if (!/^https?:$/.test(location.protocol)) return '';
    if (location.hostname === 'appassets.androidplatform.net') return '';
    return location.origin + location.pathname + '?room=' + code;
  }

  function copyText(text, done) {
    const ok = () => toast(done || 'تم النسخ');
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(ok, () => legacyCopy(text) && ok());
    } else if (legacyCopy(text)) ok();
  }
  function legacyCopy(text) {
    const t = document.createElement('textarea');
    t.value = text;
    t.style.position = 'fixed';
    t.style.opacity = '0';
    document.body.appendChild(t);
    t.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    t.remove();
    return ok;
  }

  // ------------------------------------------------------------------- game

  function renderGame(s) {
    if (!s || !s.game) return;
    const g = s.game;
    $('game-title').textContent = app.mode === 'solo' ? 'ضد الكمبيوتر' : 'غرفة ' + s.code;
    renderSeats(s);
    renderTable(s);
    renderStatus(s);
    renderActions(s);
    renderHand(s);
    renderOver(s);
    $('me-line').innerHTML = g.me >= 0
      ? `${seatAvatar(s, g.me)} <b>${esc(g.players[g.me].name)}</b> — معك ${cardsWord(g.hand.length)}`
      : 'تتفرّج';
  }

  function seatOrder(g) {
    const n = g.players.length;
    const me = g.me >= 0 ? g.me : n - 1;
    const order = [];
    for (let i = 1; i <= n; i++) {
      const s = (me + i) % n;
      if (s !== g.me) order.push(s);
    }
    return order;
  }

  function renderSeats(s) {
    const g = s.game;
    const box = $('seats');
    const order = seatOrder(g);
    const sig = order.join(',') + '|' + g.players.map((p) => p.id).join(',');
    if (box.dataset.sig !== sig) {
      box.dataset.sig = sig;
      box.classList.toggle('many', order.length > 5);
      box.innerHTML = order.map((i) =>
        `<div class="seat" data-seat="${i}"><div class="av"><span class="emo"></span><span class="cnt"></span></div><span class="badge"></span><span class="nm"></span></div>`).join('');
    }
    order.forEach((i) => {
      const el = box.querySelector(`[data-seat="${i}"]`);
      const p = g.players[i];
      const m = memberOf(s, p.id);
      el.querySelector('.emo').textContent = m ? m.avatar : '🙂';
      el.querySelector('.nm').textContent = p.name;
      const cnt = el.querySelector('.cnt');
      cnt.textContent = p.count;
      cnt.classList.toggle('low', p.count <= 2);
      el.querySelector('.badge').textContent = m && m.bot ? '🤖' : m && !m.connected ? '📵' : m && m.id === s.host ? '👑' : '';
      const active = (g.phase === 'play' && g.turn === i) || (g.phase === 'challenge' && g.challenge.by === i);
      el.classList.toggle('turn', active);
      el.classList.toggle('away', !!(m && !m.bot && !m.connected));
      el.classList.toggle('trusted', g.phase === 'challenge' && g.challenge.declined.includes(i));
    });
  }

  function renderTable(s) {
    const g = s.game;
    const rb = $('round-badge');
    if (g.settings.rankMode === 'round' && g.roundRank !== null) {
      rb.innerHTML = `الجولة على <span class="rk">${E.RANKS[g.roundRank]}</span>`;
    } else if (g.settings.rankMode === 'sequence') {
      rb.innerHTML = `المطلوب <span class="rk">${E.RANKS[g.required]}</span>`;
    } else if (g.settings.rankMode === 'round') {
      rb.textContent = 'جولة جديدة';
    } else rb.textContent = '';

    const stack = $('pile-stack');
    const n = g.pileCount;
    const shown = Math.min(n, 6);
    $('pile').classList.toggle('empty', n === 0);
    if (n !== app.pileShown || stack.children.length !== shown) {
      const added = Math.max(0, n - app.pileShown);
      stack.innerHTML = '';
      for (let i = 0; i < shown; i++) {
        const b = backEl();
        const rot = ((i * 47) % 23) - 11;
        b.style.transform = `rotate(${rot}deg) translate(${((i * 13) % 9) - 4}px, ${-i * 1.5}px)`;
        b.style.setProperty('--r', rot + 'deg');
        if (i >= shown - Math.min(added, shown) && added > 0 && n > app.pileShown) b.classList.add('drop');
        stack.appendChild(b);
      }
      app.pileShown = n;
    }
    $('pile-count').textContent = n ? cardsWord(n) : 'الكومة فارغة';

    const claim = $('claim');
    const lp = g.lastPlay;
    if (lp) {
      const playEv = g.events.filter((e) => e.type === 'play').slice(-1)[0];
      const seq = playEv ? playEv.seq : 0;
      claim.innerHTML = `<span>${seatAvatar(s, lp.by)}</span><span class="who">${esc(seatName(s, lp.by))}:</span><span>«${claimText(lp.count, lp.rank)}»</span>`;
      if (seq !== app.claimSeq) {
        app.claimSeq = seq;
        claim.classList.remove('fresh');
        void claim.offsetWidth;
        claim.classList.add('fresh');
      }
    } else {
      claim.innerHTML = '';
    }
  }

  function renderStatus(s) {
    const g = s.game;
    const p = $('status-text');
    let text = '';
    let mine = false;
    if (g.phase === 'challenge') {
      const by = g.challenge.by;
      if (by === g.me) { text = 'هل سيكشفك أحد؟ 🤞'; mine = true; }
      else if (g.challenge.declined.includes(g.me)) text = 'صدّقته… ننتظر البقية';
      else { text = 'هل تصدّق ' + seatName(s, by) + '؟'; mine = true; }
    } else if (g.phase === 'play') {
      if (g.turn === g.me) {
        mine = true;
        if (holding()) text = 'استعد…';
        else if (g.required === null) text = 'دورك — اختر أوراقك وأعلن رتبتها';
        else if (g.canPass) text = 'دورك — أعلن ' + RANK_WORD[g.required] + ' أو قل باص';
        else text = 'دورك — لازم تعلن ' + RANK_WORD[g.required];
      } else {
        text = 'دور ' + seatName(s, g.turn) + '…';
      }
    }
    p.textContent = text;
    p.classList.toggle('mine', mine);
  }

  function renderActions(s) {
    const g = s.game;
    const canCall = g.phase === 'challenge' && g.me >= 0 && g.challenge.by !== g.me && !g.challenge.declined.includes(g.me);
    const myTurn = g.phase === 'play' && g.turn === g.me;
    $('act-challenge').classList.toggle('on', canCall);
    $('act-turn').classList.toggle('on', !canCall && myTurn);
    $('act-react').classList.toggle('on', !canCall && !myTurn);
    if (myTurn) renderTurnControls(s);
  }

  function renderTurnControls(s) {
    const g = s.game;
    const ranks = $('ranks');
    if (g.required !== null) {
      ranks.innerHTML = `<span class="locked">الرتبة المطلوبة:</span><button aria-pressed="true" disabled>${E.RANKS[g.required]}</button>`;
    } else {
      if (!app.rankManual) {
        const rs = new Set(Array.from(app.sel, (c) => E.rankOf(c)));
        app.rank = rs.size === 1 ? Array.from(rs)[0] : null;
      }
      ranks.innerHTML = E.RANKS.map((r, i) => `<button data-rank="${i}" aria-pressed="${app.rank === i}">${r}</button>`).join('');
    }
    $('btn-pass').hidden = !g.canPass;
    $('btn-pass').disabled = holding();
    const btn = $('btn-play');
    const n = app.sel.size;
    const rank = g.required !== null ? g.required : app.rank;
    if (!n) { btn.textContent = 'اختر أوراقك'; btn.disabled = true; return; }
    if (rank === null) { btn.textContent = 'اختر الرتبة التي ستعلنها'; btn.disabled = true; return; }
    const honest = Array.from(app.sel).every((c) => E.rankOf(c) === rank);
    btn.textContent = (honest ? 'ضعها: ' : '🤫 اكذب: ') + '«' + claimText(n, rank) + '»';
    btn.disabled = holding();
  }

  /** Lays the hand out in as many overlapping rows as it takes to keep every index readable. */
  function renderHand(s) {
    const g = s.game;
    const hand = $('hand');
    const key = g.hand.join(',');
    if (key !== app.handKey) {
      const before = new Set(app.handKey ? app.handKey.split(',').map(Number) : []);
      const firstDeal = !app.handKey;
      hand.innerHTML = '';
      g.hand.forEach((c) => {
        const el = cardEl(c);
        if (!firstDeal && !before.has(c)) el.classList.add('new');
        hand.appendChild(el);
      });
      app.handKey = key;
      layoutHand();
    }
    hand.querySelectorAll('.card').forEach((el) => el.classList.toggle('sel', app.sel.has(Number(el.dataset.id))));
    hand.classList.toggle('locked', g.phase === 'over');
  }

  function layoutHand() {
    const hand = $('hand');
    const cards = Array.from(hand.children);
    const n = cards.length;
    const W = Math.min(hand.parentElement.clientWidth - 8, 720);
    hand.style.width = W + 'px';
    if (!n) { hand.style.height = '40px'; return; }
    // Narrow phones limit the width of a card, short ones its height.
    const cw = Math.max(42, Math.min(78, W / 6.2, window.innerHeight * 0.085));
    const minStep = cw * 0.42;
    let rows = 1, perRow = n, step = 0;
    for (rows = 1; rows <= 4; rows++) {
      perRow = Math.ceil(n / rows);
      step = perRow > 1 ? (W - cw) / (perRow - 1) : 0;
      if (step >= minStep || rows === 4) break;
    }
    step = Math.min(step, cw * 1.06);
    const ch = cw * 1.4;
    const rowH = ch * (rows >= 3 ? 0.5 : 0.56);
    hand.style.setProperty('--cw', cw + 'px');
    hand.style.height = (ch + 18 + (rows - 1) * rowH) + 'px';
    const rowsUsed = Math.ceil(n / perRow);
    cards.forEach((el, i) => {
      const r = Math.floor(i / perRow), c = i % perRow;
      const inRow = r === rowsUsed - 1 ? n - r * perRow : perRow;
      const width = (inRow - 1) * step + cw;
      el.style.right = ((W - width) / 2 + c * step) + 'px';
      el.style.top = (14 + r * rowH) + 'px';
      el.style.zIndex = String(i + 1);
    });
  }

  function renderOver(s) {
    const g = s.game;
    const box = $('over');
    if (g.phase !== 'over') { box.hidden = true; return; }
    // A last card that was called: let the reveal finish before the result.
    // The hold timer renders again when it ends.
    if (holding()) return;
    if (app.overSeq === g.seq && !box.hidden) return;
    app.overSeq = g.seq;
    const w = g.winner;
    $('over-avatar').textContent = seatAvatar(s, w);
    $('over-title').textContent = w === g.me ? 'فزت! 🎉' : 'فاز ' + g.players[w].name + '!';
    const ranked = g.players.map((p, i) => ({ p, i })).sort((a, b) => a.p.count - b.p.count);
    $('standings').innerHTML = ranked.map(({ p, i }) =>
      `<li><b>${esc(i === g.me ? 'أنت' : p.name)}</b> — ${p.count ? cardsWord(p.count) : i === g.me ? 'خلّصت أوراقك' : 'خلّص أوراقه'}</li>`).join('');
    const conf = $('confetti');
    conf.innerHTML = '';
    const colors = ['#e9c46a', '#e63946', '#52b788', '#f4f1e8', '#4cc9f0'];
    for (let i = 0; i < 40; i++) {
      const c = document.createElement('i');
      c.style.left = (Math.random() * 100) + '%';
      c.style.background = colors[i % colors.length];
      c.style.animationDuration = (1.6 + Math.random() * 1.8) + 's';
      c.style.animationDelay = (Math.random() * 0.6) + 's';
      conf.appendChild(c);
    }
    $('reveal').hidden = true;
    box.hidden = false;
  }

  function showReveal(e, s) {
    const g = s.game;
    const v = $('reveal-verdict');
    v.textContent = e.truthful ? 'صادق! ✅' : 'كذّاب! 🤥';
    v.className = 'verdict ' + (e.truthful ? 'truth' : 'lie');
    const said = '«' + claimText(e.count, e.rank) + '»';
    $('reveal-claim').textContent =
      e.caller === g.me ? 'قلت «كذّاب!» على ' + seatName(s, e.by) + ' حين أعلن ' + said
        : e.by === g.me ? seatName(s, e.caller) + ' قال «كذّاب!» عليك حين أعلنت ' + said
          : seatName(s, e.caller) + ' قال «كذّاب!» على ' + seatName(s, e.by) + ' حين أعلن ' + said;
    const cards = $('reveal-cards');
    cards.innerHTML = '';
    e.cards.forEach((c, i) => {
      const el = cardEl(c);
      el.classList.add(E.rankOf(c) === e.rank ? 'right' : 'wrong');
      el.style.animationDelay = (i * 0.12) + 's';
      cards.appendChild(el);
    });
    const loser = e.loser === g.me ? 'أنت تسحب' : seatName(s, e.loser) + ' يسحب';
    $('reveal-result').textContent = loser + ' الكومة (' + cardsWord(e.taken) + ')' + (e.loser === g.me ? ' 😬' : '');
    $('reveal').hidden = false;
    A.play('call');
    setTimeout(() => A.play(e.truthful ? 'truth' : 'liar'), 260);
    A.vibrate(e.loser === g.me ? [80, 60, 160] : 70);
    A.speak(e.truthful ? 'طلع صادق' : 'طلع كذّاب');
    clearTimeout(app.revealTimer);
    app.revealTimer = setTimeout(() => { $('reveal').hidden = true; }, Math.max(1800, s.hold));
  }

  function bubble(seat, text, emoji) {
    const s = app.snap;
    if (!s || !s.game) return;
    let host;
    if (seat === s.game.me) host = document.querySelector('.me-line');
    else host = $('seats').querySelector(`[data-seat="${seat}"]`);
    if (!host) return;
    host.querySelectorAll('.bubble').forEach((b) => b.remove());
    const b = document.createElement('span');
    b.className = 'bubble' + (emoji ? ' emoji' : '');
    b.textContent = text;
    if (seat === s.game.me) { b.style.top = '-30px'; host.style.position = 'relative'; }
    host.appendChild(b);
    setTimeout(() => b.remove(), 3000);
  }

  function onReact(id, e) {
    const s = app.snap;
    if (!s) return;
    A.play('react');
    if (s.game) {
      const seat = s.game.players.findIndex((p) => p.id === id);
      if (seat >= 0) bubble(seat, e, true);
    } else {
      const m = memberOf(s, id);
      if (m) toast(m.avatar + ' ' + m.name + ' ' + e, 1500);
    }
  }

  // --------------------------------------------------------------- timer bar

  function tick() {
    const bar = $('timer-bar');
    const t = app.timer;
    if (t && app.snap && app.snap.game) {
      const left = Math.max(0, t.endsAt - Date.now());
      bar.style.width = (100 * left / t.total) + '%';
      bar.classList.toggle('challenge', t.kind === 'challenge');
    } else {
      bar.style.width = '0';
    }
    requestAnimationFrame(tick);
  }

  // --------------------------------------------------------------- wake lock

  async function requestWake() {
    try {
      if ('wakeLock' in navigator && !app.wake && document.visibilityState === 'visible') {
        app.wake = await navigator.wakeLock.request('screen');
        app.wake.addEventListener('release', () => { app.wake = null; });
      }
    } catch (e) { app.wake = null; }
  }
  function releaseWake() {
    if (app.wake) { app.wake.release().catch(() => {}); app.wake = null; }
  }

  /** The phone's back button opens the menu instead of dropping out of the room. */
  let backGuarded = false;
  function guardBack() {
    if (backGuarded) return;
    backGuarded = true;
    try { history.pushState({ kz: 1 }, ''); } catch (e) { backGuarded = false; }
  }

  // ------------------------------------------------------------------ input

  function wire() {
    // Avatars
    const avBox = $('avatars');
    const current = store.get('avatar', Room.AVATARS[Math.floor(Math.random() * 8)]);
    store.set('avatar', current);
    avBox.innerHTML = Room.AVATARS.slice(0, 12).map((a) =>
      `<button role="radio" aria-checked="${a === current}" data-av="${a}">${a}</button>`).join('');
    avBox.addEventListener('click', (ev) => {
      const b = ev.target.closest('[data-av]');
      if (!b) return;
      store.set('avatar', b.dataset.av);
      avBox.querySelectorAll('button').forEach((x) => x.setAttribute('aria-checked', String(x === b)));
    });

    const nameInput = $('name');
    nameInput.value = store.get('name', '');
    nameInput.addEventListener('input', () => store.set('name', nameInput.value));

    const codeInput = $('code');
    codeInput.addEventListener('input', () => { codeInput.value = Net.normalizeCode(codeInput.value); });
    codeInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') startClient(codeInput.value); });
    const q = new URLSearchParams(location.search);
    if (q.get('room')) codeInput.value = Net.normalizeCode(q.get('room'));

    $('btn-create').onclick = startHost;
    $('btn-rejoin').onclick = () => {
      const last = store.get('lastRoom', null);
      if (last) startClient(last.code);
    };
    refreshRejoin();
    $('btn-join').onclick = () => startClient(codeInput.value);
    $('btn-solo').onclick = () => { if (!needName()) startSolo(Number($('solo-bots').value)); };
    $('btn-rules').onclick = () => { $('rules').hidden = false; };
    $('rules-close').onclick = () => { $('rules').hidden = true; };
    $('btn-conn-cancel').onclick = () => endSession();

    if (!Net.hasWebRTC()) {
      $('btn-create').disabled = true;
      $('btn-join').disabled = true;
      $('foot').textContent = ERRORS.unsupported;
    } else {
      $('foot').textContent = 'الإصدار ' + VERSION + ' • الأجهزة تتصل ببعضها مباشرة، بلا خادم';
    }

    // Lobby
    $('lobby-leave').onclick = () => endSession();
    $('btn-share').onclick = shareRoom;
    $('btn-copy').onclick = () => app.snap && copyText(app.snap.code, 'نُسخ الكود ' + app.snap.code);
    $('btn-add-bot').onclick = () => send({ t: 'addBot' });
    $('btn-start').onclick = () => send({ t: 'start' });
    $('members').addEventListener('click', (ev) => {
      const b = ev.target.closest('[data-kick]');
      if (b) send({ t: 'kick', id: b.dataset.kick });
    });
    $('settings').addEventListener('click', (ev) => {
      const b = ev.target.closest('[data-set]');
      if (!b || !isHost()) return;
      const k = b.dataset.set;
      const raw = b.dataset.val;
      const val = /^\d+$/.test(raw) ? Number(raw) : raw;
      send({ t: 'settings', settings: { [k]: val } });
    });

    // Game
    $('hand').addEventListener('click', (ev) => {
      const el = ev.target.closest('.card');
      const s = app.snap;
      if (!el || !s || !s.game || s.game.phase === 'over') return;
      A.unlock();
      const id = Number(el.dataset.id);
      if (app.sel.has(id)) app.sel.delete(id);
      else {
        const max = s.game.settings.maxCards;
        if (app.sel.size >= max) { toast('الحد ' + toArabicDigits(max) + ' أوراق في الدور'); return; }
        app.sel.add(id);
      }
      el.classList.toggle('sel', app.sel.has(id));
      if (s.game.phase === 'play' && s.game.turn === s.game.me) renderTurnControls(s);
    });
    $('ranks').addEventListener('click', (ev) => {
      const b = ev.target.closest('[data-rank]');
      if (!b) return;
      app.rank = Number(b.dataset.rank);
      app.rankManual = true;
      renderTurnControls(app.snap);
    });
    $('btn-play').onclick = () => {
      const s = app.snap;
      if (!s || !s.game || holding()) return;
      const g = s.game;
      const rank = g.required !== null ? g.required : app.rank;
      if (!app.sel.size || rank === null) return;
      send({ t: 'play', cards: Array.from(app.sel), rank });
      app.sel.clear();
      app.rankManual = false;
      app.rank = null;
    };
    $('btn-pass').onclick = () => { if (!holding()) send({ t: 'pass' }); };
    $('btn-call').onclick = () => { A.unlock(); A.vibrate(40); send({ t: 'call' }); };
    $('btn-trust').onclick = () => send({ t: 'trust' });
    $('reveal').onclick = () => { $('reveal').hidden = true; };

    const react = $('act-react');
    react.innerHTML = Room.REACTIONS.map((e) => `<button data-e="${e}" aria-label="${e}">${e}</button>`).join('');
    react.addEventListener('click', (ev) => {
      const b = ev.target.closest('[data-e]');
      if (b) send({ t: 'react', e: b.dataset.e });
    });

    // Menu
    const soundOn = store.get('sound', true), voiceOn = store.get('voice', true);
    A.set('sound', soundOn); A.set('voice', voiceOn);
    $('opt-sound').checked = soundOn;
    $('opt-voice').checked = voiceOn;
    $('game-sound').textContent = soundOn ? '🔊' : '🔇';
    $('opt-sound').onchange = (e) => {
      A.set('sound', e.target.checked); store.set('sound', e.target.checked);
      $('game-sound').textContent = e.target.checked ? '🔊' : '🔇';
    };
    $('opt-voice').onchange = (e) => { A.set('voice', e.target.checked); store.set('voice', e.target.checked); };
    $('game-sound').onclick = () => { const on = !A.get('sound'); $('opt-sound').checked = on; $('opt-sound').onchange({ target: $('opt-sound') }); };
    $('game-menu').onclick = openMenu;
    $('menu-close').onclick = () => { $('menu').hidden = true; };
    $('menu-rules').onclick = () => { $('menu').hidden = true; $('rules').hidden = false; };
    $('menu-leave').onclick = () => endSession();
    $('menu-end').onclick = () => { $('menu').hidden = true; send({ t: 'lobby' }); };
    $('btn-rematch').onclick = () => send({ t: 'rematch' });
    $('btn-to-lobby').onclick = () => send({ t: 'lobby' });
    $('btn-over-leave').onclick = () => endSession();

    window.addEventListener('popstate', () => {
      backGuarded = false;
      if (!app.mode) return;
      if (!$('rules').hidden) $('rules').hidden = true;
      else if (!$('menu').hidden) $('menu').hidden = true;
      else openMenu();
      guardBack();
    });
    window.addEventListener('resize', () => { if (app.snap && app.snap.game) layoutHand(); });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && $('game').classList.contains('active')) requestWake();
    });
    // Tell the room we are going, rather than letting it find out by timeout.
    window.addEventListener('pagehide', () => {
      if (app.mode === 'client' && app.net) app.net.send({ t: 'leave' });
      if (app.mode === 'host' && app.net) app.net.close();
    });
    document.addEventListener('pointerdown', () => A.unlock(), { once: true });
  }

  /** A room left by accident (app killed, page reloaded) is offered back for a few hours. */
  function refreshRejoin() {
    const last = store.get('lastRoom', null);
    const b = $('btn-rejoin');
    const fresh = last && last.code && Date.now() - last.at < 3 * 3600 * 1000;
    b.hidden = !fresh || !Net.hasWebRTC();
    if (fresh) b.textContent = '↩︎ ارجع إلى الغرفة ' + last.code;
  }

  function openMenu() {
    const leave = $('menu-leave');
    leave.textContent = app.mode === 'host' ? 'إغلاق الغرفة (تنتهي للجميع)' : 'مغادرة اللعبة';
    $('menu-end').hidden = !(app.snap && app.snap.game && isHost());
    $('voice-hint').textContent = A.canSpeak() ? '' : 'لا يوجد صوت عربي على هذا الجهاز، فالإعلان يظهر مكتوباً فقط.';
    $('menu').hidden = false;
  }

  wire();
  requestAnimationFrame(tick);

  if ('serviceWorker' in navigator && location.protocol === 'https:' && !window.KazzabAndroid) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }

  // Exposed for the end-to-end test and for poking at from the console.
  window.KazzabApp = { app, myKey: () => myKey, version: VERSION };
})();
