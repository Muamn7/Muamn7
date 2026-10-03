/*
 * كذّاب — playing over the internet with a room code.
 *
 * There is no game server. The phone that creates the room is the host: it
 * registers the PeerJS id "kazzab-v1-<code>" with the free PeerJS broker, and
 * the code is all a friend needs to find it. The broker only introduces the
 * two phones; after that they talk directly over a WebRTC data channel, or
 * through PeerJS's TURN relay when two mobile networks will not let them.
 *
 * Everything is a star around the host. Clients send intents and receive
 * snapshots; they never hold the game.
 *
 * For testing, ?peer=host:port points everything at a local PeerJS server and
 * ?ice=none drops the public STUN/TURN servers.
 */
(function (root) {
  'use strict';

  var PREFIX = 'kazzab-v1-';
  var PING_MS = 4000;
  /** A client that has said nothing for this long is gone, even if WebRTC has not noticed. */
  var SILENT_MS = 25000;
  var DIAL_TIMEOUT_MS = 15000;
  /** How long a client keeps trying to get back to a host it lost. */
  var RECONNECT_FOR_MS = 90000;

  function randomDigits(n) {
    var s = '';
    var buf = new Uint32Array(n);
    (root.crypto || root.msCrypto).getRandomValues(buf);
    for (var i = 0; i < n; i++) s += String(buf[i] % 10);
    return s;
  }

  /** Six digits: quick to read out loud and typed on any keyboard, Arabic ones included. */
  function randomCode() {
    var c = randomDigits(6);
    return c[0] === '0' ? '1' + c.slice(1) : c;
  }

  /** Accepts Arabic-Indic and Persian digits as well as 0-9, and ignores everything else. */
  function normalizeCode(s) {
    return String(s || '')
      .replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 0x0660); })
      .replace(/[۰-۹]/g, function (d) { return String(d.charCodeAt(0) - 0x06f0); })
      .replace(/\D/g, '')
      .slice(0, 6);
  }

  function peerOptions() {
    var q = new URLSearchParams(root.location ? root.location.search : '');
    var opts = { debug: 1 };
    var custom = q.get('peer');
    if (custom) {
      var parts = custom.split(':');
      opts.host = parts[0];
      opts.port = Number(parts[1] || 9000);
      opts.path = q.get('peerPath') || '/';
      opts.secure = q.get('peerSecure') === '1';
    }
    if (q.get('ice') === 'none') opts.config = { iceServers: [] };
    return opts;
  }

  function hasWebRTC() {
    return typeof root.RTCPeerConnection === 'function' && typeof root.Peer === 'function';
  }

  // ------------------------------------------------------------------- host

  /**
   * opts.onOpen(code), opts.onFail(err), opts.onStatus(text).
   * After onOpen, attach a room with setRoom(): every connection is handed to it.
   */
  function NetHost(opts) {
    this.opts = opts;
    this.peer = null;
    this.code = null;
    this.room = null;
    this.conns = {};
    this.seen = {};
    this.closed = false;
    this.sweeper = null;
  }

  NetHost.prototype.open = function () {
    var self = this;
    var attempts = 0;
    function attempt() {
      var code = randomCode();
      var peer = new root.Peer(PREFIX + code, peerOptions());
      var opened = false;
      peer.on('open', function () {
        // 'open' fires again after every reconnect to the broker.
        if (opened) { if (self.opts.onStatus) self.opts.onStatus('ok'); return; }
        opened = true;
        self.peer = peer;
        self.code = code;
        self.sweeper = setInterval(function () { self.sweep(); }, 5000);
        self.opts.onOpen(code);
      });
      peer.on('error', function (err) {
        if (!opened) {
          peer.destroy();
          if (err.type === 'unavailable-id' && ++attempts < 5) return attempt();
          return self.opts.onFail(err);
        }
        // An error on one connection must not end the room; the broker going
        // away is handled by 'disconnected' below.
        if (self.opts.onStatus) self.opts.onStatus('error', err.type);
      });
      peer.on('connection', function (conn) { self.accept(conn); });
      // Lost the broker (a phone screen turning off will do it). Connections
      // already made keep working; reconnecting keeps the code findable.
      peer.on('disconnected', function () {
        if (self.closed || peer.destroyed) return;
        if (self.opts.onStatus) self.opts.onStatus('broker-lost');
        setTimeout(function () {
          if (!self.closed && !peer.destroyed && peer.disconnected) {
            try { peer.reconnect(); } catch (e) { /* tried again on the next drop */ }
          }
        }, 1500);
      });
    }
    attempt();
  };

  NetHost.prototype.setRoom = function (room) { this.room = room; };

  NetHost.prototype.accept = function (conn) {
    var self = this;
    var key = null;
    conn.on('data', function (msg) {
      if (self.closed || !msg || typeof msg !== 'object') return;
      if (key) self.seen[key] = Date.now();
      if (msg.t === 'ping') { conn.send({ t: 'pong' }); return; }
      if (msg.t === 'hello') {
        var k = String(msg.key || '').slice(0, 40);
        var old = self.conns[k];
        self.conns[k] = conn;
        var err = self.room.join(k, msg);
        if (err) {
          if (old) self.conns[k] = old; else delete self.conns[k];
          conn.send({ t: 'error', code: err });
          setTimeout(function () { conn.close(); }, 800);
          return;
        }
        // The same phone on a fresh connection replaces its old one.
        if (old && old !== conn) { try { old.close(); } catch (e) { /* already gone */ } }
        key = k;
        self.seen[k] = Date.now();
        self.room.update();
        return;
      }
      if (key && self.conns[key] === conn) self.room.handle(key, msg);
    });
    function gone() {
      if (key && self.conns[key] === conn) {
        delete self.conns[key];
        if (!self.closed) self.room.disconnect(key);
      }
    }
    conn.on('close', gone);
    conn.on('error', gone);
  };

  /** Drops connections that have gone quiet: a killed app does not always close its channel. */
  NetHost.prototype.sweep = function () {
    var now = Date.now();
    var self = this;
    Object.keys(this.conns).forEach(function (k) {
      if (now - (self.seen[k] || 0) > SILENT_MS) {
        var c = self.conns[k];
        delete self.conns[k];
        try { c.close(); } catch (e) { /* already gone */ }
        self.room.disconnect(k);
      }
    });
  };

  NetHost.prototype.send = function (key, msg) {
    var c = this.conns[key];
    if (c && c.open) {
      try { c.send(msg); } catch (e) { /* the close handler will clean up */ }
    }
  };

  NetHost.prototype.close = function () {
    if (this.closed) return;
    if (this.room) this.room.close();
    this.closed = true;
    clearInterval(this.sweeper);
    var peer = this.peer;
    // Give the "room closed" message a moment to leave before tearing down.
    setTimeout(function () { if (peer) peer.destroy(); }, 400);
  };

  // ----------------------------------------------------------------- client

  /**
   * opts: {code, hello, onMessage(msg), onStatus(state, detail)}
   * states: connecting, connected, reconnecting, failed
   * failure details: notfound, lost, unsupported, network
   */
  function NetClient(opts) {
    this.opts = opts;
    this.peer = null;
    this.conn = null;
    this.closed = false;
    this.everConnected = false;
    this.lostAt = 0;
    this.lastPong = 0;
    this.pinger = null;
    this.retryTimer = null;
    this.dials = 0;
  }

  NetClient.prototype.status = function (s, detail) {
    if (!this.closed && this.opts.onStatus) this.opts.onStatus(s, detail);
  };

  NetClient.prototype.connect = function () {
    var self = this;
    this.status('connecting');
    var peer = new root.Peer('kz-' + randomDigits(12), peerOptions());
    this.peer = peer;
    peer.on('open', function () { if (!self.conn) self.dial(); });
    peer.on('error', function (err) {
      if (self.closed) return;
      if (err.type === 'peer-unavailable') {
        // No such room - or, after we were in it, the host is gone or reloading.
        if (!self.everConnected) return self.fail('notfound');
        return self.retry();
      }
      if (err.type === 'browser-incompatible') return self.fail('unsupported');
      if (!self.everConnected && (err.type === 'network' || err.type === 'server-error' || err.type === 'socket-error')) {
        if (++self.dials > 3) return self.fail('network');
      }
      self.retry();
    });
    peer.on('disconnected', function () {
      if (self.closed || peer.destroyed) return;
      setTimeout(function () {
        if (!self.closed && !peer.destroyed && peer.disconnected) {
          try { peer.reconnect(); } catch (e) { /* retried on the next drop */ }
        }
      }, 1500);
    });
    this.pinger = setInterval(function () { self.ping(); }, PING_MS);
  };

  NetClient.prototype.dial = function () {
    var self = this;
    if (this.closed || !this.peer || this.peer.destroyed) return;
    if (this.peer.disconnected) { this.retry(); return; }
    var conn = this.peer.connect(PREFIX + this.opts.code, { reliable: true, serialization: 'json' });
    var timer = setTimeout(function () {
      if (!conn.open) { try { conn.close(); } catch (e) { /* never opened */ } self.lost(conn); }
    }, DIAL_TIMEOUT_MS);
    conn.on('open', function () {
      clearTimeout(timer);
      if (self.closed) { conn.close(); return; }
      self.conn = conn;
      self.everConnected = true;
      self.lostAt = 0;
      self.dials = 0;
      self.lastPong = Date.now();
      conn.send(self.opts.hello());
      self.status('connected');
    });
    conn.on('data', function (msg) {
      if (!msg || typeof msg !== 'object') return;
      self.lastPong = Date.now();
      if (msg.t === 'pong') return;
      if (msg.t === 'closed' || msg.t === 'kicked') { self.close(); }
      self.opts.onMessage(msg);
    });
    conn.on('close', function () { clearTimeout(timer); self.lost(conn); });
    conn.on('error', function () { clearTimeout(timer); self.lost(conn); });
  };

  NetClient.prototype.lost = function (conn) {
    if (this.closed) return;
    if (conn && this.conn && this.conn !== conn) return;
    this.conn = null;
    this.retry();
  };

  NetClient.prototype.retry = function () {
    var self = this;
    if (this.closed || this.retryTimer) return;
    if (!this.lostAt) this.lostAt = Date.now();
    if (Date.now() - this.lostAt > RECONNECT_FOR_MS) return this.fail(this.everConnected ? 'lost' : 'network');
    this.status(this.everConnected ? 'reconnecting' : 'connecting');
    this.retryTimer = setTimeout(function () {
      self.retryTimer = null;
      if (!self.conn) self.dial();
    }, 2000);
  };

  NetClient.prototype.ping = function () {
    if (!this.conn || !this.conn.open) return;
    if (Date.now() - this.lastPong > 15000) {
      var c = this.conn;
      try { c.close(); } catch (e) { /* already closed */ }
      this.lost(c);
      return;
    }
    try { this.conn.send({ t: 'ping' }); } catch (e) { /* close handler follows */ }
  };

  NetClient.prototype.send = function (msg) {
    if (this.conn && this.conn.open) {
      try { this.conn.send(msg); return true; } catch (e) { return false; }
    }
    return false;
  };

  NetClient.prototype.fail = function (why) {
    this.status('failed', why);
    this.close();
  };

  NetClient.prototype.close = function () {
    if (this.closed) return;
    this.closed = true;
    clearInterval(this.pinger);
    clearTimeout(this.retryTimer);
    var peer = this.peer;
    var conn = this.conn;
    this.conn = null;
    setTimeout(function () {
      try { if (conn) conn.close(); } catch (e) { /* already closed */ }
      if (peer) peer.destroy();
    }, 300);
  };

  root.Kazzab = root.Kazzab || {};
  root.Kazzab.Net = {
    PREFIX: PREFIX,
    NetHost: NetHost,
    NetClient: NetClient,
    randomCode: randomCode,
    normalizeCode: normalizeCode,
    hasWebRTC: hasWebRTC
  };
})(typeof self !== 'undefined' ? self : this);
