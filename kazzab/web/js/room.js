/*
 * كذّاب — the room, as the host runs it.
 *
 * The room owns the members, the house rules and the one copy of the game. It
 * turns intents ("play these cards", "كذّاب!") into engine calls and keeps
 * the clocks: the window in which a play can be called, the turn timer, and
 * the bots' thinking time. Every change sends each member a fresh snapshot
 * built for their seat.
 *
 * It knows nothing about the network. `send(key, msg)` is handed in, so the
 * same room serves a game with friends over PeerJS, a game against the
 * computer with no network at all, and the tests, which drive it with a fake
 * clock.
 */
(function (root, factory) {
  var node = typeof module === 'object' && module.exports;
  var E = node ? require('./engine.js') : root.Kazzab.Engine;
  var B = node ? require('./bot.js') : root.Kazzab.Bot;
  var api = factory(E, B);
  if (node) module.exports = api;
  else root.Kazzab.Room = api;
})(typeof self !== 'undefined' ? self : this, function (E, B) {
  'use strict';

  /** Bumped whenever a message changes shape. Mismatched phones are refused. */
  var PROTOCOL = 1;
  /** How long the reveal stays up before anyone can act again. */
  var REVEAL_MS = 2800;
  /** Dealing animation before the first turn's clock starts. */
  var DEAL_MS = 1200;
  /** A dropped player's turn is played for them after this grace period. */
  var ABSENT_MS = 2500;
  var REACT_GAP_MS = 1200;
  var AVATARS = ['🦊', '🐯', '🐼', '🦁', '🐸', '🐵', '🐙', '🦉', '🐺', '🐨', '🦄', '🐲', '🐧', '🐻', '🐰', '🐮'];
  var REACTIONS = ['😂', '🤥', '😏', '😱', '👀', '🔥', '🤫', '👏'];

  var realClock = {
    now: function () { return Date.now(); },
    setTimeout: function (fn, ms) { return setTimeout(fn, ms); },
    clearTimeout: function (h) { clearTimeout(h); }
  };

  function cleanName(s) {
    s = String(s == null ? '' : s).replace(/[\u0000-\u001f<>]/g, '').replace(/\s+/g, ' ').trim();
    return s.slice(0, 16);
  }
  function cleanAvatar(a) { return AVATARS.indexOf(a) >= 0 ? a : AVATARS[0]; }

  function Room(opts) {
    this.code = opts.code;
    this.hostKey = opts.hostKey;
    this.rng = opts.rng || Math.random;
    this.clock = opts.clock || realClock;
    this.transport = opts.send;
    this.members = [];
    this.settings = E.normalizeSettings(opts.settings);
    this.game = null;
    this.gameNo = 0;
    this.timers = {};
    this.deadline = null;
    this.chalClock = null;
    this.turnClock = null;
    this.holdUntil = 0;
    this.lastReact = {};
    this.closed = false;
    this.idSeq = 0;
    this.addMember(opts.hostKey, { name: opts.hostName, avatar: opts.hostAvatar });
  }

  Room.PROTOCOL = PROTOCOL;
  Room.REVEAL_MS = REVEAL_MS;
  Room.AVATARS = AVATARS;
  Room.REACTIONS = REACTIONS;
  Room.cleanName = cleanName;

  var P = Room.prototype;

  /*
   * Every member has two names. `key` is the secret its phone proves itself
   * with - knowing it is what gets a seat back after a drop - so it never
   * leaves the host. `id` is the public handle that snapshots, the game and
   * other phones use. Were keys public, anyone could claim another player's
   * seat and read their hand.
   */
  P.member = function (key) {
    for (var i = 0; i < this.members.length; i++) if (this.members[i].key === key) return this.members[i];
    return null;
  };

  P.memberById = function (id) {
    for (var i = 0; i < this.members.length; i++) if (this.members[i].id === id) return this.members[i];
    return null;
  };

  P.uniqueName = function (name, key) {
    var self = this, base = name, n = 2;
    function taken(x) { return self.members.some(function (m) { return m.key !== key && m.name === x; }); }
    while (taken(name)) name = base + ' ' + (n++);
    return name;
  };

  P.addMember = function (key, info, bot) {
    var m = {
      key: key,
      id: 'm' + (++this.idSeq),
      name: this.uniqueName(cleanName(info.name) || 'لاعب', key),
      avatar: cleanAvatar(info.avatar),
      bot: !!bot,
      connected: true,
      left: false
    };
    this.members.push(m);
    return m;
  };

  /**
   * A phone said hello. Returns an error code or null. A key already in the
   * room is the same phone coming back, mid-game included, and gets its seat
   * back. Does not broadcast: the caller wires the connection up first.
   */
  P.join = function (key, hello) {
    if (this.closed) return 'closed';
    if (!hello || hello.v !== PROTOCOL) return 'version';
    if (!key || key === this.hostKey) return 'key';
    var m = this.member(key);
    if (m && !m.bot) {
      m.connected = true;
      m.left = false;
      var name = cleanName(hello.name);
      if (name && !this.game) m.name = this.uniqueName(name, key);
      m.avatar = cleanAvatar(hello.avatar);
      return null;
    }
    if (this.game) return 'started';
    if (this.members.length >= E.MAX_PLAYERS) return 'full';
    this.addMember(key, hello);
    return null;
  };

  /** The connection dropped. In the lobby the seat is freed; in a game it is kept. */
  P.disconnect = function (key) {
    var m = this.member(key);
    if (!m || m.bot || key === this.hostKey) return;
    if (this.game) m.connected = false;
    else this.members.splice(this.members.indexOf(m), 1);
    this.update();
  };

  P.seatOf = function (key) {
    var m = this.member(key);
    if (!this.game || !m) return -1;
    var ps = this.game.players;
    for (var i = 0; i < ps.length; i++) if (ps[i].id === m.id) return i;
    return -1;
  };

  P.memberAt = function (seat) { return this.memberById(this.game.players[seat].id); };

  /** Seats whose decisions the room makes: bots, and people who are not there. */
  P.isAuto = function (seat) {
    var m = this.memberAt(seat);
    return !m || m.bot || !m.connected;
  };

  // ---------------------------------------------------------------- intents

  P.handle = function (key, msg) {
    if (this.closed || !msg || typeof msg !== 'object') return;
    var host = key === this.hostKey;
    switch (msg.t) {
      case 'play': return this.act(key, function (g, s) { return E.play(g, s, msg.cards, msg.rank); });
      case 'pass': return this.act(key, function (g, s) { return E.pass(g, s); });
      case 'call': return this.act(key, function (g, s) { return E.call(g, s); });
      case 'trust': return this.act(key, function (g, s) { return E.decline(g, s); });
      case 'react': return this.react(key, msg.e);
      case 'leave': return this.leave(key);
      case 'settings': if (host) this.setSettings(msg.settings); return;
      case 'addBot': if (host) this.addBot(); return;
      case 'kick': if (host) this.kick(msg.id); return;
      case 'start': if (host) this.start(); return;
      case 'lobby': if (host) this.toLobby(); return;
      case 'rematch': if (host) { this.toLobby(); this.start(); } return;
    }
  };

  P.act = function (key, fn) {
    var g = this.game;
    if (!g) return;
    var seat = this.seatOf(key);
    if (seat < 0) return;
    var err = this.apply(function () { return fn(g, seat); });
    if (err) this.transport(key, { t: 'error', code: err });
  };

  /** Every engine mutation goes through here, so a reveal always gets its pause. */
  P.apply = function (fn) {
    var g = this.game;
    var before = g.seq;
    var err = fn();
    if (err) return err;
    for (var i = 0; i < g.events.length; i++) {
      var ev = g.events[i];
      if (ev.seq > before && ev.type === 'reveal') this.holdUntil = this.clock.now() + REVEAL_MS;
    }
    this.update();
    return null;
  };

  P.react = function (key, e) {
    if (REACTIONS.indexOf(e) < 0) return;
    var now = this.clock.now();
    var prev = this.lastReact[key];
    if (prev !== undefined && now - prev < REACT_GAP_MS) return;
    this.lastReact[key] = now;
    var self = this;
    var from = this.member(key);
    if (!from) return;
    this.members.forEach(function (m) {
      if (!m.bot && m.connected) self.transport(m.key, { t: 'react', id: from.id, e: e });
    });
  };

  P.leave = function (key) {
    var m = this.member(key);
    if (!m || key === this.hostKey) return;
    if (this.game) { m.connected = false; m.left = true; this.update(); }
    else this.disconnect(key);
  };

  // ------------------------------------------------------------------ lobby

  P.setSettings = function (s) {
    if (this.game || !s) return;
    var merged = {};
    var cur = this.settings;
    Object.keys(cur).forEach(function (k) { merged[k] = k in s ? s[k] : cur[k]; });
    this.settings = E.normalizeSettings(merged);
    this.update();
  };

  P.addBot = function () {
    if (this.game || this.members.length >= E.MAX_PLAYERS) return;
    var used = {};
    this.members.forEach(function (m) { used[m.name] = true; used[m.avatar] = true; });
    var name = B.NAMES.filter(function (n) { return !used[n]; })[0] || 'كمبيوتر';
    var avatar = AVATARS.filter(function (a) { return !used[a]; })[0];
    var n = 1;
    while (this.member('bot-' + n)) n++;
    this.addMember('bot-' + n, { name: name, avatar: avatar }, true);
    this.update();
  };

  P.kick = function (id) {
    var m = this.memberById(id);
    if (!m || m.key === this.hostKey || this.game) return;
    this.members.splice(this.members.indexOf(m), 1);
    if (!m.bot) this.transport(m.key, { t: 'kicked' });
    this.update();
  };

  P.canStart = function () {
    return !this.game && this.members.length >= E.MIN_PLAYERS && this.members.length <= E.MAX_PLAYERS;
  };

  P.start = function () {
    if (!this.canStart()) return false;
    this.clearTimers();
    this.gameNo++;
    this.game = E.newGame(this.members.map(function (m) { return { id: m.id, name: m.name }; }), this.settings, this.rng);
    this.holdUntil = this.clock.now() + DEAL_MS;
    this.chalClock = this.turnClock = null;
    this.update();
    return true;
  };

  /** Back to the lobby. Anyone who left during the game gives up their seat. */
  P.toLobby = function () {
    if (!this.game) return;
    this.clearTimers();
    this.game = null;
    this.deadline = null;
    this.members = this.members.filter(function (m) { return m.bot || m.connected; });
    this.update();
  };

  P.close = function () {
    this.closed = true;
    this.clearTimers();
    var self = this;
    this.members.forEach(function (m) {
      if (!m.bot && m.key !== self.hostKey && m.connected) self.transport(m.key, { t: 'closed' });
    });
  };

  // ----------------------------------------------------------------- clocks

  P.clearTimers = function () {
    var c = this.clock;
    Object.keys(this.timers).forEach(function (k) { c.clearTimeout(this.timers[k]); }, this);
    this.timers = {};
  };

  /**
   * Works out which timers the current state needs, keeps the ones already
   * running, starts the missing ones and stops the rest. Keys carry the game
   * number and the event sequence, so a timer can only ever fire into the
   * moment it was made for.
   */
  P.schedule = function () {
    var g = this.game;
    var want = {};
    var now = this.clock.now();
    var self = this;
    var rng = this.rng;
    this.deadline = null;

    if (g && g.phase === 'challenge') {
      var id = g.challenge.id;
      var ms = g.settings.challengeSeconds * 1000;
      if (!this.chalClock || this.chalClock.id !== this.gameNo + ':' + id) {
        this.chalClock = { id: this.gameNo + ':' + id, at: now + ms };
      }
      var at = this.chalClock.at;
      this.deadline = { kind: 'challenge', at: at, total: ms };
      want['close:' + id] = { at: at, fn: function () { self.apply(function () { return E.closeChallenge(g); }); } };
      g.players.forEach(function (p, s) {
        if (s === g.challenge.by || g.challenge.declined.indexOf(s) >= 0) return;
        var m = self.memberAt(s);
        if (m && m.bot) {
          want['cb:' + id + ':' + s] = {
            at: now + 600 + rng() * ms * 0.55,
            fn: function () { self.botChallenge(g, s); }
          };
        } else if (!m || !m.connected) {
          want['ca:' + id + ':' + s] = { at: now + 300, fn: function () { self.apply(function () { return E.decline(g, s); }); } };
        }
      });
    } else if (g && g.phase === 'play') {
      var tid = g.seq + ':' + g.turn;
      var seat = g.turn;
      var start = Math.max(now, this.holdUntil);
      var m = this.memberAt(seat);
      if (m && m.bot) {
        want['bt:' + tid] = { at: start + 700 + rng() * 1300, fn: function () { self.autoTurn(g, seat, false); } };
      } else if (!m || !m.connected) {
        want['at:' + tid] = { at: start + ABSENT_MS, fn: function () { self.autoTurn(g, seat, true); } };
      } else if (g.settings.turnSeconds > 0) {
        var tms = g.settings.turnSeconds * 1000;
        if (!this.turnClock || this.turnClock.id !== this.gameNo + ':' + tid) {
          this.turnClock = { id: this.gameNo + ':' + tid, at: start + tms };
        }
        this.deadline = { kind: 'turn', at: this.turnClock.at, total: tms };
        want['tt:' + tid] = { at: this.turnClock.at, fn: function () { self.autoTurn(g, seat, true); } };
      }
    }

    var prefix = 'g' + this.gameNo + ':';
    var keys = {};
    Object.keys(want).forEach(function (k) { keys[prefix + k] = want[k]; });
    Object.keys(this.timers).forEach(function (k) {
      if (!(k in keys)) { self.clock.clearTimeout(self.timers[k]); delete self.timers[k]; }
    });
    Object.keys(keys).forEach(function (k) {
      if (k in self.timers) return;
      var w = keys[k];
      self.timers[k] = self.clock.setTimeout(function () {
        delete self.timers[k];
        if (self.closed || self.game !== g) return;
        w.fn();
      }, Math.max(0, w.at - now));
    });
  };

  P.botChallenge = function (g, seat) {
    if (g.phase !== 'challenge') return;
    var call = B.chooseChallenge(E.viewFor(g, seat), this.rng);
    this.apply(function () { return call ? E.call(g, seat) : E.decline(g, seat); });
  };

  /**
   * A turn the room plays: a bot's, or a person's whose clock ran out or who
   * dropped off. For a person it passes when it can - a timeout should not
   * tell a lie on their behalf.
   */
  P.autoTurn = function (g, seat, forPerson) {
    if (g.phase !== 'play' || g.turn !== seat) return;
    if (forPerson && E.canPass(g, seat)) { this.apply(function () { return E.pass(g, seat); }); return; }
    var v = E.viewFor(g, seat);
    var a = B.chooseTurn(v, this.rng);
    var err = this.apply(function () {
      return a.type === 'pass' ? E.pass(g, seat) : E.play(g, seat, a.cards, a.rank);
    });
    if (err) {
      // Never let a bad choice stall the table: play one card, claimed as whatever is required.
      var hand = g.players[seat].hand;
      var req = E.requiredRank(g);
      this.apply(function () { return E.play(g, seat, [hand[0]], req === null ? E.rankOf(hand[0]) : req); });
    }
  };

  // -------------------------------------------------------------- snapshots

  P.snapshot = function (key) {
    var now = this.clock.now();
    var g = this.game;
    var me = this.member(key);
    var host = this.member(this.hostKey);
    return {
      t: 'room',
      v: PROTOCOL,
      code: this.code,
      you: me ? me.id : null,
      host: host ? host.id : null,
      members: this.members.map(function (m) {
        return { id: m.id, name: m.name, avatar: m.avatar, bot: m.bot, connected: m.connected, left: m.left };
      }),
      settings: this.settings,
      game: g ? E.viewFor(g, this.seatOf(key)) : null,
      timer: this.deadline
        ? { kind: this.deadline.kind, left: Math.max(0, this.deadline.at - now), total: this.deadline.total }
        : null,
      hold: Math.max(0, this.holdUntil - now)
    };
  };

  P.update = function () {
    if (this.closed) return;
    this.schedule();
    var self = this;
    this.members.forEach(function (m) {
      if (!m.bot && m.connected) self.transport(m.key, self.snapshot(m.key));
    });
  };

  return Room;
});
