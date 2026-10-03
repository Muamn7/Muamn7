/*
 * كذّاب — قواعد اللعبة.
 *
 * Pure rules: no DOM, no timers, no network. Only the host runs a copy, and
 * every other phone sees nothing but what viewFor() hands it. A client cannot
 * learn another player's hand by reading its own memory, because it was never
 * sent there.
 *
 * Every action mutates the state in place and returns null on success or a
 * short error code. The host is the only writer, so there is nothing to merge.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else (root.Kazzab = root.Kazzab || {}).Engine = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'];
  var SUITS = ['S', 'H', 'D', 'C'];
  var DECK_SIZE = 52;
  var MIN_PLAYERS = 3;
  var MAX_PLAYERS = 8;
  /** Rank 0 (ace) of suit 0 (spades): who holds it opens the game by default. */
  var ACE_OF_SPADES = 0;
  /** How many events a view carries. Enough to catch up after a short drop. */
  var EVENT_TAIL = 16;

  function rankOf(card) { return card % 13; }
  function suitOf(card) { return Math.floor(card / 13); }

  /*
   * House rules. Every value a room can hold is listed, so a setting arriving
   * over the network is either one of these or replaced by the default.
   *
   * rankMode decides what a player may claim:
   *   round    - the first play of a round names the rank and everyone after
   *              must claim the same rank or pass. When all the others pass,
   *              the pile is burned and the last player opens a new round.
   *   free     - any rank, every turn.
   *   sequence - A, 2, 3 ... K, A: each claim is the rank after the last one.
   */
  var DEFAULTS = {
    maxCards: 4,
    rankMode: 'round',
    starter: 'ace',
    challengeSeconds: 6,
    turnSeconds: 60
  };
  var CHOICES = {
    maxCards: [1, 2, 3, 4],
    rankMode: ['round', 'free', 'sequence'],
    starter: ['ace', 'random', 'host'],
    challengeSeconds: [4, 6, 10],
    turnSeconds: [30, 60, 0]
  };

  function normalizeSettings(s) {
    var out = {};
    Object.keys(DEFAULTS).forEach(function (k) {
      var v = s ? s[k] : undefined;
      out[k] = CHOICES[k].indexOf(v) >= 0 ? v : DEFAULTS[k];
    });
    return out;
  }

  function shuffle(arr, rng) {
    for (var i = arr.length - 1; i > 0; i--) {
      var j = Math.floor(rng() * (i + 1));
      var t = arr[i]; arr[i] = arr[j]; arr[j] = t;
    }
    return arr;
  }

  function sortHand(hand) {
    hand.sort(function (a, b) { return rankOf(a) - rankOf(b) || suitOf(a) - suitOf(b); });
    return hand;
  }

  function emit(state, ev) {
    ev.seq = ++state.seq;
    state.events.push(ev);
    if (state.events.length > EVENT_TAIL * 2) state.events.splice(0, state.events.length - EVENT_TAIL);
    return ev;
  }

  function next(state, seat) { return (seat + 1) % state.players.length; }

  /**
   * players: [{id, name}] in clockwise seat order. Cards are dealt one at a
   * time round the table until the deck runs out, so with 52 cards some
   * players hold one more than others - the deal starts at a random seat so
   * that extra card does not always land in the same place.
   */
  function newGame(players, settings, rng) {
    rng = rng || Math.random;
    if (!players || players.length < MIN_PLAYERS || players.length > MAX_PLAYERS) {
      throw new Error('players: need ' + MIN_PLAYERS + '-' + MAX_PLAYERS);
    }
    settings = normalizeSettings(settings);
    var deck = [];
    for (var c = 0; c < DECK_SIZE; c++) deck.push(c);
    shuffle(deck, rng);

    var ps = players.map(function (p) { return { id: p.id, name: p.name, hand: [] }; });
    var offset = Math.floor(rng() * ps.length);
    deck.forEach(function (card, i) { ps[(offset + i) % ps.length].hand.push(card); });
    ps.forEach(function (p) { sortHand(p.hand); });

    var starter = 0;
    if (settings.starter === 'ace') {
      ps.forEach(function (p, i) { if (p.hand.indexOf(ACE_OF_SPADES) >= 0) starter = i; });
    } else if (settings.starter === 'random') {
      starter = Math.floor(rng() * ps.length);
    }

    var state = {
      settings: settings,
      players: ps,
      turn: starter,
      starter: starter,
      phase: 'play',          // play | challenge | over
      pile: [],               // [{by, cards, rank, count}] since the pile was last cleared
      burned: 0,              // cards removed from the game by an all-pass round
      roundRank: null,        // rankMode 'round': the rank this round is on
      seqRank: 0,             // rankMode 'sequence': the rank the next play must claim
      lastPlay: null,         // {by, rank, count} of the most recent play on this pile
      challenge: null,        // {id, by, declined: [seat]} while a play can be called
      winner: null,
      seq: 0,
      events: []
    };
    emit(state, { type: 'start', starter: starter });
    return state;
  }

  function requiredRank(state) {
    var m = state.settings.rankMode;
    if (m === 'round') return state.roundRank;
    if (m === 'sequence') return state.seqRank;
    return null;
  }

  function validSeat(state, seat) {
    return typeof seat === 'number' && seat >= 0 && seat < state.players.length && seat === Math.floor(seat);
  }

  /** Passing only exists in a round that someone has already opened. */
  function canPass(state, seat) {
    return state.phase === 'play' && seat === state.turn &&
      state.settings.rankMode === 'round' && state.roundRank !== null;
  }

  function play(state, seat, cards, rank) {
    if (state.phase !== 'play') return 'phase';
    if (seat !== state.turn) return 'turn';
    if (!Array.isArray(cards) || cards.length < 1 || cards.length > state.settings.maxCards) return 'count';
    var hand = state.players[seat].hand;
    var seen = {};
    for (var i = 0; i < cards.length; i++) {
      var c = cards[i];
      if (typeof c !== 'number' || seen[c] || hand.indexOf(c) < 0) return 'cards';
      seen[c] = true;
    }
    if (typeof rank !== 'number' || rank < 0 || rank > 12 || rank !== Math.floor(rank)) return 'rank';
    var req = requiredRank(state);
    if (req !== null && rank !== req) return 'rank';

    cards.forEach(function (c) { hand.splice(hand.indexOf(c), 1); });
    state.pile.push({ by: seat, cards: cards.slice(), rank: rank, count: cards.length });
    if (state.settings.rankMode === 'round' && state.roundRank === null) state.roundRank = rank;
    if (state.settings.rankMode === 'sequence') state.seqRank = (rank + 1) % 13;
    state.lastPlay = { by: seat, rank: rank, count: cards.length };
    state.phase = 'challenge';
    var ev = emit(state, { type: 'play', by: seat, rank: rank, count: cards.length, left: hand.length });
    state.challenge = { id: ev.seq, by: seat, declined: [] };
    return null;
  }

  function finish(state, seat) {
    state.phase = 'over';
    state.winner = seat;
    state.challenge = null;
    emit(state, { type: 'win', by: seat });
  }

  /**
   * "كذّاب!" - turn over the last play. Whoever was wrong takes the whole pile:
   * the player if they lied, the caller if they did not. The winner of the
   * call opens the next round.
   */
  function call(state, seat) {
    if (state.phase !== 'challenge') return 'phase';
    if (!validSeat(state, seat) || seat === state.challenge.by) return 'seat';
    if (state.challenge.declined.indexOf(seat) >= 0) return 'declined';

    var top = state.pile[state.pile.length - 1];
    var truthful = top.cards.every(function (c) { return rankOf(c) === top.rank; });
    var loser = truthful ? seat : top.by;
    var taken = [];
    state.pile.forEach(function (p) { taken.push.apply(taken, p.cards); });
    var loserHand = state.players[loser].hand;
    loserHand.push.apply(loserHand, taken);
    sortHand(loserHand);

    state.pile = [];
    state.roundRank = null;
    state.lastPlay = null;
    state.challenge = null;
    emit(state, {
      type: 'reveal', caller: seat, by: top.by, cards: top.cards.slice(), rank: top.rank,
      count: top.count, truthful: truthful, loser: loser, taken: taken.length
    });

    // Telling the truth with your last card and being called on it still wins.
    if (truthful && state.players[top.by].hand.length === 0) { finish(state, top.by); return null; }
    state.turn = truthful ? top.by : seat;
    state.phase = 'play';
    return null;
  }

  /** The window closed with nobody calling. Going out is only final here. */
  function settle(state) {
    var by = state.challenge.by;
    state.challenge = null;
    if (state.players[by].hand.length === 0) { finish(state, by); return; }
    state.turn = next(state, by);
    state.phase = 'play';
  }

  /** "صدّقت" - this player will not call. When everyone has, play moves on. */
  function decline(state, seat) {
    if (state.phase !== 'challenge') return 'phase';
    if (!validSeat(state, seat) || seat === state.challenge.by) return 'seat';
    var d = state.challenge.declined;
    if (d.indexOf(seat) < 0) d.push(seat);
    if (d.length >= state.players.length - 1) settle(state);
    return null;
  }

  function closeChallenge(state) {
    if (state.phase !== 'challenge') return 'phase';
    settle(state);
    return null;
  }

  function pass(state, seat) {
    if (!canPass(state, seat)) return 'pass';
    emit(state, { type: 'pass', by: seat });
    state.turn = next(state, seat);
    // Round the table back to the last player with nobody playing on it: the
    // pile is burned and that player opens a new round with any rank.
    if (state.lastPlay && state.turn === state.lastPlay.by) {
      var n = 0;
      state.pile.forEach(function (p) { n += p.count; });
      state.burned += n;
      state.pile = [];
      state.roundRank = null;
      state.lastPlay = null;
      emit(state, { type: 'burn', count: n, starter: state.turn });
    }
    return null;
  }

  function pileCount(state) {
    var n = 0;
    state.pile.forEach(function (p) { n += p.count; });
    return n;
  }

  /**
   * Everything one seat is allowed to know. seat -1 is a spectator.
   * pileMine is the cards this seat itself put in the current pile: a player
   * remembers what they really played, and the bots reason from it.
   */
  function viewFor(state, seat) {
    var me = validSeat(state, seat) ? state.players[seat] : null;
    var mine = [];
    if (me) state.pile.forEach(function (p) { if (p.by === seat) mine.push.apply(mine, p.cards); });
    return {
      me: me ? seat : -1,
      phase: state.phase,
      turn: state.turn,
      starter: state.starter,
      winner: state.winner,
      settings: { maxCards: state.settings.maxCards, rankMode: state.settings.rankMode },
      players: state.players.map(function (p) { return { id: p.id, name: p.name, count: p.hand.length }; }),
      hand: me ? me.hand.slice() : [],
      pileCount: pileCount(state),
      pileClaims: state.pile.map(function (p) { return { by: p.by, rank: p.rank, count: p.count }; }),
      pileMine: mine,
      burned: state.burned,
      lastPlay: state.lastPlay ? { by: state.lastPlay.by, rank: state.lastPlay.rank, count: state.lastPlay.count } : null,
      roundRank: state.roundRank,
      required: requiredRank(state),
      canPass: me ? canPass(state, seat) : false,
      challenge: state.challenge
        ? { id: state.challenge.id, by: state.challenge.by, declined: state.challenge.declined.slice() }
        : null,
      seq: state.seq,
      events: state.events.slice(-EVENT_TAIL)
    };
  }

  /** Cards in hands + pile + burned. Always 52; the tests hold it to that. */
  function totalCards(state) {
    var n = state.burned + pileCount(state);
    state.players.forEach(function (p) { n += p.hand.length; });
    return n;
  }

  return {
    RANKS: RANKS, SUITS: SUITS, DECK_SIZE: DECK_SIZE,
    MIN_PLAYERS: MIN_PLAYERS, MAX_PLAYERS: MAX_PLAYERS, ACE_OF_SPADES: ACE_OF_SPADES,
    DEFAULTS: DEFAULTS, CHOICES: CHOICES,
    rankOf: rankOf, suitOf: suitOf, normalizeSettings: normalizeSettings,
    shuffle: shuffle, sortHand: sortHand,
    newGame: newGame, requiredRank: requiredRank, canPass: canPass,
    play: play, call: call, decline: decline, closeChallenge: closeChallenge, pass: pass,
    viewFor: viewFor, totalCards: totalCards
  };
});
