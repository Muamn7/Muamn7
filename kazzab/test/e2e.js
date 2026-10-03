/*
 * End to end: three phones, one room code, a real WebRTC connection.
 *
 * Runs a local PeerJS broker and the game, opens three separate browser
 * profiles at phone size, and plays through the parts a unit test cannot
 * reach: creating a room, joining by code, starting, an honest play called
 * "كذّاب!", a lie called "كذّاب!", and a guest reloading mid-game and getting
 * the same seat back. Screenshots land in test/out/.
 *
 *   npm run e2e
 *   CHROME_PATH=/path/to/chrome npm run e2e    to use a particular browser
 */
'use strict';
const path = require('path');
const fs = require('fs');
const assert = require('assert/strict');
const { chromium } = require('playwright');
const { staticServer, startPeer } = require('../tools/serve.js');

const OUT = path.join(__dirname, 'out');
const PHONE = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: 'ar' };

function listen(server) {
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server.address().port)));
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const web = staticServer();
  const webPort = await listen(web);
  const peerPort = 19000 + Math.floor(Math.random() * 1000);
  const broker = await startPeer(peerPort, '127.0.0.1');
  const base = `http://127.0.0.1:${webPort}/?peer=127.0.0.1:${peerPort}&ice=none`;

  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || undefined,
    // Headless Chromium hides local addresses behind mDNS names it then cannot
    // resolve; on one machine that is the difference between connecting and not.
    args: ['--disable-features=WebRtcHideLocalIpsWithMdns', '--autoplay-policy=no-user-gesture-required']
  });

  const phones = [];
  async function phone(label) {
    const ctx = await browser.newContext(PHONE);
    const page = await ctx.newPage();
    page.on('pageerror', (e) => { console.error(`[${label}] page error:`, e.message); process.exitCode = 1; });
    page.on('console', (m) => { if (m.type() === 'error') console.error(`[${label}]`, m.text()); });
    const p = { label, ctx, page };
    phones.push(p);
    return p;
  }
  // A beat first, so an overlay is photographed after its entrance, not halfway through.
  const shot = async (p, name) => {
    await new Promise((r) => setTimeout(r, 450));
    await p.page.screenshot({ path: path.join(OUT, name + '.png') });
  };
  const game = (p) => p.page.evaluate(() => window.KazzabApp.app.snap && window.KazzabApp.app.snap.game);
  const step = (msg) => console.log('•', msg);

  try {
    const host = await phone('host');
    await host.page.goto(base);
    await shot(host, '01-home');
    await host.page.fill('#name', 'مؤمن');
    await host.page.click('#btn-create');
    await host.page.waitForSelector('#lobby.active');
    await host.page.waitForFunction(() => /^\d{6}$/.test(document.getElementById('lobby-code').textContent));
    const code = await host.page.textContent('#lobby-code');
    step('room created: ' + code);

    const guests = [];
    for (const name of ['سارة', 'خالد']) {
      const g = await phone(name);
      await g.page.goto(base);
      await g.page.fill('#name', name);
      await g.page.fill('#code', code);
      await g.page.click('#btn-join');
      await g.page.waitForSelector('#lobby.active', { timeout: 30000 });
      guests.push(g);
      step(name + ' joined');
    }
    await host.page.waitForFunction(() => document.querySelectorAll('#members li').length === 3);
    await shot(host, '02-lobby-host');
    await shot(guests[0], '03-lobby-guest');
    assert.equal(await guests[0].page.isVisible('#btn-start'), false, 'guests cannot start');

    // A wrong code is turned away with a message, not a spinner forever.
    const lost = await phone('lost');
    await lost.page.goto(base);
    await lost.page.fill('#name', 'ضائع');
    await lost.page.fill('#code', code === '999999' ? '888888' : '999999');
    await lost.page.click('#btn-join');
    await lost.page.waitForSelector('#home.active', { timeout: 30000 });
    await lost.page.waitForSelector('#toast.show');
    assert.match(await lost.page.textContent('#toast'), /لا توجد غرفة/);
    step('a wrong code says so');
    await lost.ctx.close();
    phones.splice(phones.indexOf(lost), 1);

    await host.page.click('#btn-start');
    for (const p of phones) await p.page.waitForSelector('#game.active');
    step('game started on all three phones');

    const all = phones;
    async function whoseTurn() {
      for (const p of all) {
        const g = await game(p);
        if (g && g.phase === 'play' && g.turn === g.me) return p;
      }
      return null;
    }
    async function waitTurn() {
      for (let i = 0; i < 100; i++) {
        const p = await whoseTurn();
        if (p) return p;
        await new Promise((r) => setTimeout(r, 100));
      }
      throw new Error('nobody got a turn');
    }

    /** Plays `n` cards; if lie, claims a rank none of them are. Returns the claimed rank. */
    async function playFrom(p, lie) {
      await p.page.waitForFunction(() => Date.now() >= window.KazzabApp.app.holdEnds);
      const g = await game(p);
      let first = g.hand[0];
      if (g.required !== null) {
        const match = g.hand.find((c) => c % 13 === g.required);
        if (match !== undefined) first = match;
        else if (g.canPass) { await p.page.click('#btn-pass'); return null; }
        else lie = true;
      }
      // Tap the corner, as a thumb would: in a big hand the next card covers
      // the middle of this one, and only its top corner with the index shows.
      const card = p.page.locator(`#hand .card[data-id="${first}"]`);
      const box = await card.boundingBox();
      await card.click({ position: { x: box.width - 8, y: 10 } });
      let rank = g.required !== null ? g.required : first % 13;
      if (lie && g.required === null) {
        rank = (rank + 5) % 13;
        await p.page.click(`#ranks [data-rank="${rank}"]`);
        const dbg = await p.page.evaluate(() => { const a = window.KazzabApp.app; return { sel: [...a.sel], rank: a.rank, manual: a.rankManual, req: a.snap.game.required, chips: document.querySelectorAll('#ranks [data-rank]').length, pressed: document.querySelector('#ranks [aria-pressed=true]')?.textContent }; });
        assert.match(await p.page.textContent('#btn-play'), /اكذب/, JSON.stringify({ first, rank, dbg }));
      } else if (!lie) {
        assert.match(await p.page.textContent('#btn-play'), /ضعها/);
      }
      await p.page.click('#btn-play');
      return rank;
    }

    async function callFrom(p) {
      await p.page.waitForSelector('#act-challenge.on');
      // The button throbs, so it never reads as 'stable' to Playwright.
      await p.page.click('#btn-call', { force: true });
    }

    // An honest play, called: the caller takes the pile.
    let player = await waitTurn();
    step(player.label + ' plays honestly');
    await playFrom(player, false);
    const caller = all.find((p) => p !== player);
    await caller.page.waitForSelector('#act-challenge.on');
    await shot(caller, '04-call-window');
    const before = (await game(caller)).hand.length;
    await callFrom(caller);
    for (const p of all) await p.page.waitForSelector('#reveal:not([hidden])');
    assert.match(await caller.page.textContent('#reveal-verdict'), /صادق/);
    await shot(caller, '05-reveal-truth');
    await caller.page.waitForFunction((n) => window.KazzabApp.app.snap.game.hand.length === n + 1, before);
    step(caller.label + ' called it wrong and took the pile');

    // A lie, called: the liar takes the pile. The honest player leads next.
    await caller.page.waitForSelector('#reveal', { state: 'hidden', timeout: 10000 });
    player = await waitTurn();
    const liarBefore = (await game(player)).hand.length;
    step(player.label + ' lies');
    await playFrom(player, true);
    const caller2 = all.find((p) => p !== player);
    await callFrom(caller2);
    await player.page.waitForSelector('#reveal:not([hidden])');
    assert.match(await player.page.textContent('#reveal-verdict'), /كذّاب/);
    await shot(player, '06-reveal-lie');
    await player.page.waitForFunction((n) => window.KazzabApp.app.snap.game.hand.length === n, liarBefore);
    step(player.label + ' was caught and took the pile back');

    await player.page.waitForSelector('#reveal', { state: 'hidden', timeout: 10000 });
    const turnPhone = await waitTurn();
    await shot(turnPhone, '07-my-turn');

    // A guest reloads mid-game: same code, same seat, same hand.
    const g2 = guests[1];
    const g2key = await g2.page.evaluate(() => window.KazzabApp.myKey());
    await g2.page.reload();
    // The home screen offers the way back without typing the code again.
    await g2.page.waitForSelector('#btn-rejoin:not([hidden])');
    assert.match(await g2.page.textContent('#btn-rejoin'), new RegExp(code));
    await g2.page.click('#btn-rejoin');
    await g2.page.waitForSelector('#game.active', { timeout: 30000 });
    // Its turn may have been played for it while it was away, so compare with
    // the host's copy of that seat rather than with the hand before the reload.
    const seatHand = (k) => { const r = window.KazzabApp.app.room; return r.game.players[r.seatOf(k)].hand; };
    let same = false;
    for (let i = 0; i < 50 && !same; i++) {
      const [mine, hosts] = [(await game(g2)).hand, await host.page.evaluate(seatHand, g2key)];
      same = JSON.stringify(mine) === JSON.stringify(hosts);
      if (!same) await new Promise((r) => setTimeout(r, 100));
    }
    assert.ok(same, 'the rejoined phone shows its seat\'s hand');
    assert.equal(await host.page.evaluate((k) => window.KazzabApp.app.room.member(k).connected, g2key), true);
    step(g2.label + ' reloaded and got the same seat back');

    // Closing the room sends everyone home with a message.
    await host.page.click('#game-menu');
    await host.page.click('#menu-leave');
    for (const g of guests) {
      await g.page.waitForSelector('#home.active', { timeout: 15000 });
      assert.match(await g.page.textContent('#toast'), /أغلق المضيف/);
    }
    step('closing the room sent the guests home');

    // Against the computer, with no network at all.
    const solo = await phone('solo');
    await solo.page.goto(`http://127.0.0.1:${webPort}/`);
    await solo.page.fill('#name', 'مؤمن');
    await solo.page.selectOption('#solo-bots', '4');
    await solo.page.click('#btn-solo');
    await solo.page.waitForSelector('#game.active');
    await solo.page.waitForFunction(() => document.querySelectorAll('#seats .seat').length === 4);
    // Play along - our own turns and "صدّقت" in every window - until the bots have had a few goes.
    for (let i = 0; i < 400; i++) {
      const sg = await game(solo);
      if (sg.seq >= 6) break;
      if (sg.phase === 'play' && sg.turn === sg.me) await playFrom(solo, false);
      else if (await solo.page.isVisible('#act-challenge.on')) await solo.page.click('#btn-trust');
      await new Promise((r) => setTimeout(r, 100));
    }
    assert.ok((await game(solo)).seq >= 6, 'the bots never got going');
    await shot(solo, '08-solo');
    step('a game against four bots runs');

    // Rig a quick finish: free claims and a single card left, then play it.
    await solo.page.evaluate(() => {
      const r = window.KazzabApp.app.room;
      const me = r.seatOf(window.KazzabApp.myKey());
      r.game.settings.rankMode = 'free';
      r.game.players[me].hand = r.game.players[me].hand.slice(0, 1);
      r.update();
    });
    for (let i = 0; i < 600 && !(await solo.page.isVisible('#over')); i++) {
      const sg = await game(solo);
      if (sg.phase === 'play' && sg.turn === sg.me) {
        if (await solo.page.isVisible('#btn-play')) await playFrom(solo, false);
      } else if (await solo.page.isVisible('#act-challenge.on')) await solo.page.click('#btn-trust');
      await new Promise((r) => setTimeout(r, 100));
    }
    await solo.page.waitForSelector('#over:not([hidden])');
    assert.match(await solo.page.textContent('#over-title'), /فزت/);
    await shot(solo, '09-win');
    await solo.page.click('#btn-rematch');
    await solo.page.waitForSelector('#over', { state: 'hidden' });
    await solo.page.waitForFunction(() => window.KazzabApp.app.snap.game && window.KazzabApp.app.snap.game.hand.length > 5);
    step('winning shows the result, and a rematch deals again');

    console.log('\nall good — screenshots in ' + OUT);
  } finally {
    await browser.close();
    web.close();
    broker.close && broker.close();
  }
}

main().then(() => process.exit(process.exitCode || 0), (e) => { console.error(e); process.exit(1); });
