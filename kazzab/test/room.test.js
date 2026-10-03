'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const E = require('../web/js/engine.js');
const Room = require('../web/js/room.js');

function rngFrom(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

/** A clock the test moves by hand, so a whole game runs in milliseconds. */
function fakeClock() {
  let now = 1000, id = 0;
  const pending = new Map();
  return {
    now: () => now,
    setTimeout(fn, ms) { pending.set(++id, { at: now + ms, fn }); return id; },
    clearTimeout(h) { pending.delete(h); },
    pending: () => pending.size,
    /** Fire the earliest timer. Returns false when nothing is waiting. */
    step() {
      let best = null;
      for (const [k, t] of pending) if (!best || t.at < best[1].at) best = [k, t];
      if (!best) return false;
      pending.delete(best[0]);
      now = Math.max(now, best[1].at);
      best[1].fn();
      return true;
    },
    advance(ms) {
      const until = now + ms;
      for (;;) {
        let best = null;
        for (const [k, t] of pending) if (t.at <= until && (!best || t.at < best[1].at)) best = [k, t];
        if (!best) break;
        pending.delete(best[0]);
        now = best[1].at;
        best[1].fn();
      }
      now = until;
    }
  };
}

function makeRoom(seed, settings, hostKey = 'host') {
  const clock = fakeClock();
  const inbox = {};
  const room = new Room({
    code: '123456', hostKey, hostName: 'المضيف',
    rng: rngFrom(seed), clock, settings,
    send: (key, msg) => { (inbox[key] = inbox[key] || []).push(msg); }
  });
  const last = (key) => (inbox[key] || []).filter((m) => m.t === 'room').at(-1);
  return { room, clock, inbox, last };
}

const hello = (name) => ({ t: 'hello', v: Room.PROTOCOL, name });
/** The secret key of whoever sits in a seat - what their phone would send as. */
const keyAt = (room, seat) => room.memberAt(seat).key;

test('people join until eight, then the room is full', () => {
  const { room } = makeRoom(1);
  for (let i = 1; i < 8; i++) assert.equal(room.join('k' + i, hello('لاعب')), null);
  assert.equal(room.join('k9', hello('x')), 'full');
  const names = room.members.map((m) => m.name);
  assert.equal(new Set(names).size, names.length, 'duplicate names get a number');
});

test('a phone on another protocol version is turned away', () => {
  const { room } = makeRoom(1);
  assert.equal(room.join('k1', { name: 'a', v: 999 }), 'version');
});

test('only the host can change the rules or start', () => {
  const { room } = makeRoom(1);
  room.join('k1', hello('a')); room.join('k2', hello('b'));
  room.handle('k1', { t: 'settings', settings: { maxCards: 2 } });
  room.handle('k1', { t: 'start' });
  assert.equal(room.settings.maxCards, 4);
  assert.equal(room.game, null);
  room.handle('host', { t: 'settings', settings: { maxCards: 2, rankMode: 'nonsense' } });
  assert.equal(room.settings.maxCards, 2);
  assert.equal(room.settings.rankMode, 'round');
  room.handle('host', { t: 'start' });
  assert.ok(room.game);
  assert.equal(room.join('k3', hello('late')), 'started');
});

test('a game cannot start with fewer than three', () => {
  const { room } = makeRoom(1);
  room.join('k1', hello('a'));
  assert.equal(room.start(), false);
  room.addBot();
  assert.equal(room.start(), true);
});

test('each snapshot carries only its own hand', () => {
  const { room, last } = makeRoom(2);
  room.join('k1', hello('a')); room.addBot();
  room.update();
  room.start();
  const mine = last('k1');
  const seat = room.seatOf('k1');
  assert.deepEqual(mine.game.hand, room.game.players[seat].hand);
  const text = JSON.stringify(mine);
  for (const [i, p] of room.game.players.entries()) {
    if (i === seat) continue;
    assert.ok(!text.includes(JSON.stringify(p.hand)), 'another hand leaked');
  }
});

test('bots play a whole game to a winner on their own', () => {
  for (let seed = 1; seed <= 60; seed++) {
    const modes = ['round', 'free', 'sequence'];
    const { room, clock } = makeRoom(seed, { rankMode: modes[seed % 3], maxCards: 1 + (seed % 4) });
    // The host steps away: with a 30s turn clock its turns are played for it too.
    room.settings.turnSeconds = 30;
    for (let i = 0; i < 2 + (seed % 6); i++) room.addBot();
    room.start();
    let steps = 0;
    while (room.game.phase !== 'over' && steps++ < 50000) {
      assert.ok(clock.step(), `seed ${seed}: the table stalled with no timer running`);
      assert.equal(E.totalCards(room.game), 52);
    }
    assert.equal(room.game.phase, 'over', `seed ${seed} never finished`);
    assert.equal(clock.pending(), 0, 'no timers left after the game');
  }
});

test('the call window closes on time and play moves on', () => {
  const { room, clock, last } = makeRoom(3, { challengeSeconds: 6 });
  room.join('k1', hello('a')); room.join('k2', hello('b'));
  room.start();
  clock.advance(2000);
  const g = room.game;
  const key = keyAt(room, g.turn);
  const seat = g.turn;
  room.handle(key, { t: 'play', cards: [g.players[seat].hand[0]], rank: E.rankOf(g.players[seat].hand[0]) });
  assert.equal(g.phase, 'challenge');
  const snap = last('k1');
  assert.equal(snap.timer.kind, 'challenge');
  assert.equal(snap.timer.left, 6000);
  clock.advance(5900);
  assert.equal(g.phase, 'challenge');
  clock.advance(200);
  assert.equal(g.phase, 'play');
  assert.equal(g.turn, (seat + 1) % 3);
});

test('when everyone trusts the play the window closes at once', () => {
  const { room, clock } = makeRoom(4);
  room.join('k1', hello('a')); room.join('k2', hello('b'));
  room.start();
  clock.advance(2000);
  const g = room.game;
  const seat = g.turn;
  const c = g.players[seat].hand[0];
  room.handle(keyAt(room, seat), { t: 'play', cards: [c], rank: E.rankOf(c) });
  g.players.forEach((_, i) => { if (i !== seat) room.handle(keyAt(room, i), { t: 'trust' }); });
  assert.equal(g.phase, 'play');
});

test('a reveal holds the table before the next turn clock starts', () => {
  const { room, clock, last } = makeRoom(5, { turnSeconds: 30 });
  room.join('k1', hello('a')); room.join('k2', hello('b'));
  room.start();
  clock.advance(2000);
  const g = room.game;
  const seat = g.turn;
  const c = g.players[seat].hand[0];
  room.handle(keyAt(room, seat), { t: 'play', cards: [c], rank: (E.rankOf(c) + 1) % 13 }); // a lie
  const caller = keyAt(room, (seat + 1) % 3);
  room.handle(caller, { t: 'call' });
  assert.equal(g.events.at(-1).type, 'reveal');
  const snap = last('k1');
  assert.equal(snap.hold, Room.REVEAL_MS);
  assert.equal(snap.timer.left, Room.REVEAL_MS + 30000);
});

test('a player who drops mid-game is played for, and gets the seat back', () => {
  const { room, clock, last } = makeRoom(6, { turnSeconds: 0 });
  room.join('k1', hello('a')); room.join('k2', hello('b'));
  room.start();
  room.disconnect('k1');
  assert.equal(room.member('k1').connected, false);
  let steps = 0;
  // With k1 away and nobody else acting, only k1's seat can move by itself.
  while (room.game.turn !== room.seatOf('k1') && steps++ < 10) {
    const g = room.game;
    if (g.phase === 'play') {
      const p = g.players[g.turn];
      room.handle(keyAt(room, g.turn), { t: 'play', cards: [p.hand[0]], rank: E.requiredRank(g) ?? E.rankOf(p.hand[0]) });
    } else {
      // The absent seat trusts automatically a moment later.
      room.handle('host', { t: 'trust' }); room.handle('k2', { t: 'trust' });
      clock.advance(400);
    }
  }
  const seq = room.game.seq;
  clock.advance(5000);
  assert.ok(room.game.seq > seq, 'the absent seat was played for');
  assert.equal(room.join('k1', hello('a')), null);
  room.update();
  assert.equal(room.member('k1').connected, true);
  assert.ok(last('k1').game.hand.length > 0);
});

test('leaving the lobby frees the seat; going back to the lobby drops absentees', () => {
  const { room } = makeRoom(7);
  room.join('k1', hello('a')); room.join('k2', hello('b'));
  room.disconnect('k2');
  assert.equal(room.member('k2'), null);
  room.join('k2', hello('b'));
  room.start();
  room.handle('k2', { t: 'leave' });
  room.handle('host', { t: 'lobby' });
  assert.equal(room.member('k2'), null);
  assert.equal(room.game, null);
});

test('reactions are limited to the list and to one every so often', () => {
  const { room, inbox, clock } = makeRoom(8);
  room.join('k1', hello('a'));
  const [a, b] = Room.REACTIONS;
  room.handle('k1', { t: 'react', e: a });
  room.handle('k1', { t: 'react', e: a });
  room.handle('k1', { t: 'react', e: '<script>' });
  clock.advance(2000);
  room.handle('k1', { t: 'react', e: b });
  const got = (inbox.host || []).filter((m) => m.t === 'react').map((m) => m.e);
  assert.deepEqual(got, [a, b]);
});

test('names are trimmed, stripped of markup and capped', () => {
  const { room } = makeRoom(9);
  room.join('k1', { v: Room.PROTOCOL, name: '  <b>محمد</b>\n   الطويل جدا جدا جدا ' });
  const m = room.member('k1');
  assert.ok(!/[<>\n]/.test(m.name));
  assert.ok(m.name.length <= 16);
});

test('no snapshot or reaction ever carries another phone\'s secret key', () => {
  const { room, inbox, clock } = makeRoom(10, {}, 'secret-host');
  room.join('secret-one', hello('a')); room.join('secret-two', hello('b'));
  room.start();
  clock.advance(1500);
  room.handle('secret-one', { t: 'react', e: Room.REACTIONS[0] });
  // A seat is claimed with its key, so a leaked key is a stolen hand.
  for (const [to, msgs] of Object.entries(inbox)) {
    const text = JSON.stringify(msgs);
    for (const k of ['secret-host', 'secret-one', 'secret-two']) {
      if (k !== to) assert.ok(!text.includes('"' + k + '"'), `${to} was sent ${k}`);
    }
  }
  const snap = inbox['secret-two'].filter((m) => m.t === 'room').at(-1);
  assert.equal(snap.you, room.member('secret-two').id);
  assert.equal(snap.host, room.member('secret-host').id);
});

test('the host kicks by public id', () => {
  const { room, inbox } = makeRoom(11);
  room.join('k1', hello('a'));
  room.handle('host', { t: 'kick', id: room.member('k1').id });
  assert.equal(room.member('k1'), null);
  assert.ok(inbox.k1.some((m) => m.t === 'kicked'));
});
