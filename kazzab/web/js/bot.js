/*
 * كذّاب — the computer players.
 *
 * A bot decides from a view, the same object a phone receives, so it knows
 * exactly what a person in its seat would know: its own hand, what it really
 * put in the pile, and every claim said out loud. It never peeks.
 *
 * The same code plays for a human whose turn timer ran out or whose phone
 * dropped off, so a missing player cannot stall the table.
 */
(function (root, factory) {
  var E = (typeof module === 'object' && module.exports) ? require('./engine.js') : root.Kazzab.Engine;
  var api = factory(E);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Kazzab.Bot = api;
})(typeof self !== 'undefined' ? self : this, function (E) {
  'use strict';

  var NAMES = ['سالم', 'نورة', 'فهد', 'ليلى', 'ماجد', 'هند', 'زياد', 'ريم'];

  function clamp(x, lo, hi) { return x < lo ? lo : x > hi ? hi : x; }

  function groupByRank(hand) {
    var g = [];
    for (var r = 0; r < 13; r++) g.push([]);
    hand.forEach(function (c) { g[E.rankOf(c)].push(c); });
    return g;
  }

  function playOf(cards, rank) { return { type: 'play', cards: cards, rank: rank }; }

  /**
   * Cards to hide in a lie: the loneliest ranks first. A single 9 is the card
   * least likely ever to be played honestly, so it is the one worth risking.
   */
  function lieCards(groups, avoidRank, n, rng) {
    var pool = [];
    groups.forEach(function (g, r) {
      if (r === avoidRank) return;
      g.forEach(function (c) { pool.push({ c: c, w: g.length + rng() * 0.9 }); });
    });
    pool.sort(function (a, b) { return a.w - b.w; });
    return pool.slice(0, n).map(function (x) { return x.c; });
  }

  function chooseTurn(view, rng) {
    rng = rng || Math.random;
    var hand = view.hand;
    var max = view.settings.maxCards;
    var req = view.required;
    var groups = groupByRank(hand);

    // Going out: the whole hand is one honest play.
    if (hand.length <= max) {
      var r0 = E.rankOf(hand[0]);
      var same = hand.every(function (c) { return E.rankOf(c) === r0; });
      if (same && (req === null || req === r0)) return playOf(hand.slice(), r0);
    }

    var cards;
    if (req === null) {
      // Opening a round, or free claims: lead with the biggest honest group.
      var best = -1;
      groups.forEach(function (g, r) {
        if (!g.length) return;
        if (best < 0 || g.length > groups[best].length || (g.length === groups[best].length && rng() < 0.5)) best = r;
      });
      cards = groups[best].slice(0, max);
      // Now and then, slip one extra card in under cover of an honest lead.
      if (cards.length < max && hand.length > cards.length && rng() < 0.25) {
        cards = cards.concat(lieCards(groups, best, 1, rng));
      }
      return playOf(cards, best);
    }

    var have = groups[req];
    if (have.length) {
      cards = have.slice(0, max);
      if (cards.length < max && hand.length > cards.length && rng() < 0.2) {
        cards = cards.concat(lieCards(groups, req, 1, rng));
      }
      return playOf(cards, req);
    }

    // Nothing honest to play. A big pile makes a lie expensive; someone about
    // to go out makes standing still expensive.
    var nearWin = view.players.some(function (p, i) { return i !== view.me && p.count <= 2; });
    var lie = 0.35 + Math.min(0.3, hand.length * 0.02) - Math.min(0.25, view.pileCount * 0.015) + (nearWin ? 0.15 : 0);
    if (view.canPass && rng() > lie) return { type: 'pass' };
    var n = (max >= 2 && hand.length > 2 && rng() < 0.3) ? 2 : 1;
    return playOf(lieCards(groups, req, n, rng), req);
  }

  /** true to call "كذّاب!" on the last play. */
  function chooseChallenge(view, rng) {
    rng = rng || Math.random;
    var lp = view.lastPlay;
    if (!lp || lp.by === view.me) return false;
    var r = lp.rank;
    var inHand = view.hand.filter(function (c) { return E.rankOf(c) === r; }).length;
    var inPile = view.pileMine.filter(function (c) { return E.rankOf(c) === r; }).length;
    var known = inHand + inPile;
    // There are four of each rank. Counting the ones I can see is a certainty.
    if (known + lp.count > 4) return true;

    var claimed = 0;
    view.pileClaims.forEach(function (p) { if (p.by !== view.me && p.rank === r) claimed += p.count; });
    var p = 0.06 + inHand * 0.1 + (lp.count - 1) * 0.06;
    if (claimed + known > 4) p += 0.35;          // someone in this pile lied about it
    var left = view.players[lp.by].count;
    if (left === 0) p += 0.45;                   // they win unless someone calls
    else if (left <= 2) p += 0.1;
    p -= Math.min(0.15, view.pileCount * 0.008); // a big pile is a big price for being wrong
    return rng() < clamp(p, 0.02, 0.92);
  }

  return { NAMES: NAMES, chooseTurn: chooseTurn, chooseChallenge: chooseChallenge, groupByRank: groupByRank };
});
