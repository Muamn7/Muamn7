/*
 * كذّاب — sound, voice and vibration.
 *
 * Every sound is synthesised with WebAudio: there are no audio files to load
 * or to go missing. The claim is read out loud in Arabic - the game's rules
 * have the player announce it, so the phone announces it for them. Inside the
 * Android app the browser has no speech engine, so the app lends its own
 * through the KazzabAndroid bridge.
 */
(function (root) {
  'use strict';

  var ctx = null;
  var enabled = { sound: true, voice: true };
  var arabicVoice = null;

  function bridge() { return root.KazzabAndroid || null; }

  function audio() {
    if (!ctx) {
      var AC = root.AudioContext || root.webkitAudioContext;
      if (!AC) return null;
      try { ctx = new AC(); } catch (e) { return null; }
    }
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  /** Browsers only allow sound after a touch; call this from the first one. */
  function unlock() { audio(); }

  function tone(freq, start, dur, type, vol, slideTo) {
    var a = audio();
    if (!a || !enabled.sound) return;
    var t = a.currentTime + start;
    var o = a.createOscillator();
    var g = a.createGain();
    o.type = type || 'sine';
    o.frequency.setValueAtTime(freq, t);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol || 0.2, t + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(a.destination);
    o.start(t);
    o.stop(t + dur + 0.02);
  }

  function noise(start, dur, vol, cutoff) {
    var a = audio();
    if (!a || !enabled.sound) return;
    var len = Math.floor(a.sampleRate * dur);
    var buf = a.createBuffer(1, len, a.sampleRate);
    var d = buf.getChannelData(0);
    for (var i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
    var src = a.createBufferSource();
    src.buffer = buf;
    var f = a.createBiquadFilter();
    f.type = 'bandpass';
    f.frequency.value = cutoff || 2500;
    var g = a.createGain();
    g.gain.value = vol || 0.4;
    src.connect(f).connect(g).connect(a.destination);
    src.start(a.currentTime + start);
  }

  var sounds = {
    card: function () { noise(0, 0.07, 0.5, 3200); noise(0.05, 0.06, 0.3, 2400); },
    deal: function () { for (var i = 0; i < 8; i++) noise(i * 0.06, 0.05, 0.35, 2800 + i * 60); },
    turn: function () { tone(880, 0, 0.14, 'sine', 0.18); tone(1320, 0.12, 0.22, 'sine', 0.14); },
    pass: function () { tone(330, 0, 0.12, 'triangle', 0.12); },
    liar: function () { tone(520, 0, 0.5, 'sawtooth', 0.12, 140); tone(260, 0.05, 0.5, 'square', 0.06, 90); },
    truth: function () { tone(660, 0, 0.15, 'triangle', 0.18); tone(880, 0.12, 0.15, 'triangle', 0.18); tone(1320, 0.24, 0.3, 'triangle', 0.16); },
    call: function () { tone(220, 0, 0.18, 'square', 0.1); tone(196, 0.16, 0.25, 'square', 0.1); },
    burn: function () { noise(0, 0.5, 0.25, 900); },
    tick: function () { tone(1800, 0, 0.04, 'square', 0.05); },
    win: function () {
      [523, 659, 784, 1047].forEach(function (f, i) { tone(f, i * 0.13, 0.3, 'triangle', 0.2); });
      tone(1568, 0.55, 0.6, 'sine', 0.12);
    },
    react: function () { tone(1200, 0, 0.06, 'sine', 0.08); }
  };

  function play(name) { if (enabled.sound && sounds[name]) { try { sounds[name](); } catch (e) { /* no audio, no matter */ } } }

  function pickVoice() {
    if (!root.speechSynthesis) return;
    var vs = root.speechSynthesis.getVoices() || [];
    arabicVoice = vs.filter(function (v) { return /^ar(\b|-|_)/i.test(v.lang); })[0] || null;
  }
  if (root.speechSynthesis) {
    pickVoice();
    if ('onvoiceschanged' in root.speechSynthesis) root.speechSynthesis.onvoiceschanged = pickVoice;
  }

  function canSpeak() {
    var b = bridge();
    if (b && b.canSpeak) { try { return !!b.canSpeak(); } catch (e) { return false; } }
    return !!arabicVoice;
  }

  /** Read Arabic text aloud. Silent when there is no Arabic voice rather than mangled by an English one. */
  function speak(text) {
    if (!enabled.voice || !text) return;
    var b = bridge();
    if (b && b.speak) { try { b.speak(text); } catch (e) { /* no speech */ } return; }
    if (!root.speechSynthesis || !arabicVoice) return;
    try {
      root.speechSynthesis.cancel();
      var u = new root.SpeechSynthesisUtterance(text);
      u.voice = arabicVoice;
      u.lang = arabicVoice.lang;
      u.rate = 1.05;
      root.speechSynthesis.speak(u);
    } catch (e) { /* no speech */ }
  }

  function vibrate(ms) {
    var b = bridge();
    if (b && b.vibrate) {
      // The bridge takes one duration; a pattern becomes its total.
      var total = Array.isArray(ms) ? ms.reduce(function (a, x) { return a + x; }, 0) : ms;
      try { b.vibrate(total); } catch (e) { /* none */ }
      return;
    }
    if (root.navigator && root.navigator.vibrate) { try { root.navigator.vibrate(ms); } catch (e) { /* none */ } }
  }

  function set(kind, on) { enabled[kind] = !!on; if (kind === 'voice' && !on && root.speechSynthesis) root.speechSynthesis.cancel(); }
  function get(kind) { return enabled[kind]; }

  root.Kazzab = root.Kazzab || {};
  root.Kazzab.Audio = { unlock: unlock, play: play, speak: speak, canSpeak: canSpeak, vibrate: vibrate, set: set, get: get };
})(typeof self !== 'undefined' ? self : this);
