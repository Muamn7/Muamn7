'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const E = require('../web/js/engine.js');

// Small deterministic generator so a failing game can be replayed exactly.
function rngFrom(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}
const players = (n) => Array.from({ length: n }, (_, i) => ({ id: 'p' + i, name: 'P' + i }));
const card = (rank, suit) => suit * 13 + rank;

/** A game with hands set by hand, for tests that need a known position. */
function rigged(hands, settings) {
  const g = E.newGame(players(hands.length), settings, rngFrom(1));
  g.players.forEach((p, i) => { p.hand = E.sortHand(hands[i].slice()); });
  g.turn = 0;
  return g;
}

test('deals the whole deck as evenly as it divides', () => {
  for (let n = E.MIN_PLAYERS; n <= E.MAX_PLAYERS; n++) {
    const g = E.newGame(players(n), {}, rngFrom(n));
    const counts = g.players.map((p) => p.hand.length);
    assert.equal(counts.reduce((a, b) => a + b), 52);
    assert.ok(Math.max(...counts) - Math.min(...counts) <= 1, `uneven deal for ${n}: ${counts}`);
    const all = new Set(g.players.flatMap((p) => p.hand));
    assert.equal(all.size, 52);
  }
});

test('refuses fewer than 3 or more than 8 players', () => {
  assert.throws(() => E.newGame(players(2), {}));
  assert.throws(() => E.newGame(players(9), {}));
});

test('the holder of the ace of spades opens by default', () => {
  for (let seed = 0; seed < 20; seed++) {
    const g = E.newGame(players(5), {}, rngFrom(seed));
    assert.ok(g.players[g.turn].hand.includes(E.ACE_OF_SPADES));
  }
});

test('settings from the network fall back to defaults when they are not a listed choice', () => {
  const s = E.normalizeSettings({ maxCards: 9, rankMode: 'chaos', starter: 'host', challengeSeconds: '6' });
  assert.equal(s.maxCards, E.DEFAULTS.maxCards);
  assert.equal(s.rankMode, E.DEFAULTS.rankMode);
  assert.equal(s.starter, 'host');
  assert.equal(s.challengeSeconds, E.DEFAULTS.challengeSeconds);
});

test('a play must be your turn, your cards, within the limit', () => {
  const g = rigged([[card(6, 0), card(6, 1), card(2, 0)], [card(3, 0)], [card(4, 0)]], { maxCards: 2 });
  assert.equal(E.play(g, 1, [card(3, 0)], 3), 'turn');
  assert.equal(E.play(g, 0, [], 6), 'count');
  assert.equal(E.play(g, 0, [card(6, 0), card(6, 1), card(2, 0)], 6), 'count');
  assert.equal(E.play(g, 0, [card(3, 0)], 3), 'cards');
  assert.equal(E.play(g, 0, [card(6, 0), card(6, 0)], 6), 'cards');
  assert.equal(E.play(g, 0, [card(6, 0)], 13), 'rank');
  assert.equal(E.play(g, 0, [card(6, 0)], '6'), 'rank');
  assert.equal(E.play(g, 0, [card(6, 0), card(6, 1)], 6), null);
  assert.equal(g.phase, 'challenge');
  assert.deepEqual(g.lastPlay, { by: 0, rank: 6, count: 2 });
  assert.equal(E.play(g, 1, [card(3, 0)], 6), 'phase');
});

test('calling a liar gives the liar the whole pile and the caller the next turn', () => {
  const g = rigged([[card(2, 0), card(9, 0)], [card(6, 0), card(6, 1)], [card(4, 0), card(5, 0)]], {});
  assert.equal(E.play(g, 0, [card(2, 0)], 6), null); // claims a 7, plays a 3
  E.decline(g, 1); E.decline(g, 2);
  assert.equal(g.turn, 1);
  assert.equal(E.play(g, 1, [card(6, 0)], 6), null); // honest
  assert.equal(E.closeChallenge(g), null);
  assert.equal(E.play(g, 2, [card(4, 0)], 6), null); // lies
  assert.equal(E.call(g, 0), null);
  const reveal = g.events.at(-1);
  assert.equal(reveal.type, 'reveal');
  assert.equal(reveal.truthful, false);
  assert.equal(reveal.loser, 2);
  assert.equal(reveal.taken, 3);
  assert.equal(g.players[2].hand.length, 4);
  assert.equal(g.pile.length, 0);
  assert.equal(g.turn, 0);
  assert.equal(g.roundRank, null);
  assert.equal(E.totalCards(g), 6); // only the six rigged cards exist
});

test('calling an honest player costs the caller the pile, and the honest player leads', () => {
  const g = rigged([[card(6, 0), card(6, 1), card(9, 0)], [card(3, 0)], [card(4, 0)]], {});
  E.play(g, 0, [card(6, 0), card(6, 1)], 6);
  assert.equal(E.call(g, 2), null);
  const reveal = g.events.at(-1);
  assert.equal(reveal.truthful, true);
  assert.equal(reveal.loser, 2);
  assert.equal(g.players[2].hand.length, 3);
  assert.equal(g.turn, 0);
  assert.equal(g.phase, 'play');
});

test('nobody may call their own play, or call after trusting it', () => {
  const g = rigged([[card(6, 0), card(9, 0)], [card(3, 0)], [card(4, 0)]], {});
  E.play(g, 0, [card(6, 0)], 6);
  assert.equal(E.call(g, 0), 'seat');
  E.decline(g, 1);
  assert.equal(E.call(g, 1), 'declined');
  assert.equal(E.call(g, 2), null);
});

test('going out wins once the window closes with nobody calling', () => {
  const g = rigged([[card(6, 0)], [card(3, 0)], [card(4, 0)]], {});
  E.play(g, 0, [card(6, 0)], 6);
  assert.equal(g.phase, 'challenge');
  E.closeChallenge(g);
  assert.equal(g.phase, 'over');
  assert.equal(g.winner, 0);
});

test('going out honestly still wins when someone calls it', () => {
  const g = rigged([[card(6, 0)], [card(3, 0)], [card(4, 0)]], {});
  E.play(g, 0, [card(6, 0)], 6);
  E.call(g, 1);
  assert.equal(g.phase, 'over');
  assert.equal(g.winner, 0);
});

test('a last card caught in a lie does not win', () => {
  const g = rigged([[card(2, 0)], [card(3, 0)], [card(4, 0)]], {});
  E.play(g, 0, [card(2, 0)], 6);
  E.call(g, 1);
  assert.equal(g.phase, 'play');
  assert.equal(g.winner, null);
  assert.equal(g.players[0].hand.length, 1);
  assert.equal(g.turn, 1);
});

test('round mode: the opening claim fixes the rank, others follow or pass', () => {
  const g = rigged([[card(6, 0), card(1, 0)], [card(3, 0), card(3, 1)], [card(4, 0), card(4, 1)]], { rankMode: 'round' });
  assert.equal(E.canPass(g, 0), false, 'cannot pass when opening a round');
  E.play(g, 0, [card(6, 0)], 6);
  E.closeChallenge(g);
  assert.equal(E.requiredRank(g), 6);
  assert.equal(E.play(g, 1, [card(3, 0)], 3), 'rank');
  assert.equal(E.pass(g, 1), null);
  assert.equal(g.turn, 2);
  assert.equal(E.pass(g, 2), null);
  // Everyone else passed: the pile burns and player 0 opens a new round.
  const burn = g.events.at(-1);
  assert.equal(burn.type, 'burn');
  assert.equal(burn.count, 1);
  assert.equal(g.turn, 0);
  assert.equal(g.pile.length, 0);
  assert.equal(g.burned, 1);
  assert.equal(E.requiredRank(g), null);
});

test('free mode: any claim, no passing', () => {
  const g = rigged([[card(6, 0), card(1, 0)], [card(3, 0), card(3, 1)], [card(4, 0)]], { rankMode: 'free' });
  E.play(g, 0, [card(6, 0)], 6);
  E.closeChallenge(g);
  assert.equal(E.requiredRank(g), null);
  assert.equal(E.canPass(g, 1), false);
  assert.equal(E.play(g, 1, [card(3, 0)], 11), null);
});

test('sequence mode: claims climb A, 2, 3 ... and wrap after the king', () => {
  const g = rigged([[card(0, 0), card(12, 1), card(5, 0)], [card(1, 0), card(5, 1)], [card(2, 0)]], { rankMode: 'sequence' });
  assert.equal(E.requiredRank(g), 0);
  E.play(g, 0, [card(0, 0)], 0); E.closeChallenge(g);
  assert.equal(E.requiredRank(g), 1);
  assert.equal(E.play(g, 1, [card(1, 0)], 4), 'rank');
  E.play(g, 1, [card(1, 0)], 1); E.closeChallenge(g);
  E.play(g, 2, [card(2, 0)], 2); E.call(g, 0); // honest: caller takes it, 2 has no cards and wins
  assert.equal(g.winner, 2);
  const g2 = rigged([[card(12, 0), card(3, 0)], [card(0, 1), card(5, 1)], [card(2, 0)]], { rankMode: 'sequence' });
  g2.seqRank = 12;
  E.play(g2, 0, [card(12, 0)], 12); E.closeChallenge(g2);
  assert.equal(E.requiredRank(g2), 0);
});

test('a view shows your hand and nobody else\'s', () => {
  const g = E.newGame(players(4), {}, rngFrom(7));
  const v = E.viewFor(g, 1);
  assert.deepEqual(v.hand, g.players[1].hand);
  assert.equal(v.players[0].hand, undefined);
  assert.equal(v.players[0].count, g.players[0].hand.length);
  const seat = g.turn;
  const c = g.players[seat].hand[0];
  E.play(g, seat, [c], (E.rankOf(c) + 1) % 13);
  const other = E.viewFor(g, (seat + 1) % 4);
  const json = JSON.stringify(other);
  assert.ok(!('cards' in other.pileClaims[0]), 'claims never carry the real cards');
  assert.deepEqual(other.pileMine, []);
  assert.deepEqual(E.viewFor(g, seat).pileMine, [c]);
  assert.ok(json.length < 4000);
  const spectator = E.viewFor(g, -1);
  assert.deepEqual(spectator.hand, []);
});

test('random games always end, and never lose or invent a card', () => {
  const modes = ['round', 'free', 'sequence'];
  for (let seed = 1; seed <= 300; seed++) {
    const rng = rngFrom(seed);
    const n = 3 + (seed % 6);
    const g = E.newGame(players(n), { rankMode: modes[seed % 3], maxCards: 1 + (seed % 4) }, rng);
    let steps = 0;
    while (g.phase !== 'over' && steps++ < 20000) {
      if (g.phase === 'play') {
        const hand = g.players[g.turn].hand;
        if (E.canPass(g, g.turn) && rng() < 0.3) { assert.equal(E.pass(g, g.turn), null); continue; }
        const k = 1 + Math.floor(rng() * Math.min(g.settings.maxCards, hand.length));
        const req = E.requiredRank(g);
        const cards = hand.slice(0, k);
        const rank = req === null ? E.rankOf(cards[0]) : req;
        assert.equal(E.play(g, g.turn, cards, rank), null);
      } else {
        const others = g.players.map((_, i) => i).filter((i) => i !== g.challenge.by);
        const r = rng();
        if (r < 0.15) E.call(g, others[Math.floor(rng() * others.length)]);
        else if (r < 0.5) E.closeChallenge(g);
        else others.forEach((i) => { if (g.phase === 'challenge') E.decline(g, i); });
      }
      assert.equal(E.totalCards(g), 52, `seed ${seed}`);
    }
    assert.equal(g.phase, 'over', `seed ${seed} did not finish`);
    assert.equal(g.players[g.winner].hand.length, 0);
  }
});
