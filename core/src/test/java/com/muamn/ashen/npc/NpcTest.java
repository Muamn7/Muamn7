package com.muamn.ashen.npc;

import com.badlogic.gdx.utils.Array;
import com.muamn.ashen.item.ItemDef;
import com.muamn.ashen.item.ItemLibrary;
import com.muamn.ashen.ui.BonfireMenu;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Guards the people and their stock.
 *
 * The check with real consequences is the last group: reinforcement above the
 * first tier is gated behind bosses on purpose, and a merchant quietly stocking
 * a lump would undo that gate without anything else in the build noticing.
 */
class NpcTest {

    private static NpcLibrary people;
    private static ItemLibrary items;

    @BeforeAll
    static void loadFromRepo() throws IOException {
        Path dir = Paths.get("").toAbsolutePath();
        while (dir != null && !Files.exists(dir.resolve("assets/data/npcs.json"))) {
            dir = dir.getParent();
        }
        assertNotNull(dir, "could not find assets/data/npcs.json");

        people = new NpcLibrary();
        people.parse(read(dir.resolve("assets/data/npcs.json")));
        items = new ItemLibrary();
        items.parse(read(dir.resolve("assets/data/items.json")));
    }

    private static String read(Path path) throws IOException {
        return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
    }

    @Test
    void idsAreUniqueAndEveryoneIsNamedInBothLanguages() {
        Set<String> ids = new HashSet<>();
        for (NpcDef npc : people.all()) {
            assertTrue(ids.add(npc.id), "duplicate npc id: " + npc.id);
            assertFalse(npc.nameEn.isEmpty(), npc.id + " has no English name");
            assertFalse(npc.nameAr.isEmpty(), npc.id + " has no Arabic name");
            assertFalse(npc.area.isEmpty(), npc.id + " stands nowhere");
        }
    }

    @Test
    void everyLineExistsInBothLanguages() {
        for (NpcDef npc : people.all()) {
            assertTrue(npc.lines.size > 0, npc.id + " has nothing to say");
            for (NpcDef.Line line : npc.lines) {
                assertFalse(line.en.trim().isEmpty(), npc.id + " has an empty English line");
                assertFalse(line.ar.trim().isEmpty(), npc.id + " has an empty Arabic line");
            }
        }
    }

    /**
     * A line longer than the box can hold gets wrapped, and a very long one
     * pushes the panel over the screen. Two lines of about eighty characters is
     * the practical ceiling on a phone.
     */
    @Test
    void linesFitInTheDialogueBox() {
        for (NpcDef npc : people.all()) {
            for (NpcDef.Line line : npc.lines) {
                assertTrue(line.en.length() <= 160,
                        npc.id + " has a " + line.en.length() + "-character line");
            }
        }
    }

    @Test
    void merchantsSellItemsThatExistAtPricesAboveZero() {
        for (NpcDef npc : people.all()) {
            for (NpcDef.Offer offer : npc.shop) {
                assertTrue(items.has(offer.itemId),
                        npc.id + " sells unknown item '" + offer.itemId + "'");
                assertTrue(offer.price > 0,
                        npc.id + " gives away " + offer.itemId);
            }
        }
    }

    @Test
    void aMerchantNeverStocksTheSameItemTwice() {
        for (NpcDef npc : people.all()) {
            Set<String> stocked = new HashSet<>();
            for (NpcDef.Offer offer : npc.shop) {
                assertTrue(stocked.add(offer.itemId),
                        npc.id + " lists " + offer.itemId + " twice");
            }
        }
    }

    /**
     * The upgrade path is gated behind bosses. Anything a merchant can sell is
     * effectively unlimited, so selling a higher tier would remove that gate.
     */
    @Test
    void noMerchantSellsAGatedReinforcementMaterial() {
        Set<String> gated = new HashSet<>();
        for (int level = 4; level <= 10; level++) {
            gated.add(BonfireMenu.reinforceMaterial(level));
        }
        for (NpcDef npc : people.all()) {
            for (NpcDef.Offer offer : npc.shop) {
                assertFalse(gated.contains(offer.itemId),
                        npc.id + " sells " + offer.itemId
                                + ", which the bosses are supposed to gate");
            }
        }
    }

    @Test
    void everythingSoldIsWorthMoreThanNothingAndLessThanALevel() {
        // A consumable that costs more than a level-up is a trap, not a choice.
        for (NpcDef npc : people.all()) {
            for (NpcDef.Offer offer : npc.shop) {
                ItemDef def = items.get(offer.itemId);
                assertTrue(offer.price <= 4000,
                        npc.id + " wants " + offer.price + " for " + def.id);
            }
        }
    }

    @Test
    void atLeastOneMerchantExistsAndSellsHealing() {
        boolean healing = false;
        for (NpcDef npc : people.all()) {
            for (NpcDef.Offer offer : npc.shop) {
                if (items.get(offer.itemId).effect == ItemDef.Effect.HEAL) healing = true;
            }
        }
        assertTrue(healing, "nowhere in the game can the player buy healing");
    }

    @Test
    void inAreaReturnsOnlyThatAreasPeople() {
        Array<NpcDef> out = new Array<>();
        people.inArea("ash_town", out);
        assertTrue(out.size > 0, "the hub should have people in it");
        for (NpcDef npc : out) assertEquals("ash_town", npc.area);

        people.inArea("nowhere_at_all", out);
        assertEquals(0, out.size);
    }

    // ---- conversation state ----------------------------------------------

    @Test
    void theLastLineRepeatsRatherThanWrapping() {
        NpcDef def = people.all().get(0);
        Npc npc = new Npc(def, new StillVisual());
        for (int i = 0; i < def.lines.size - 1; i++) {
            assertEquals(def.lines.get(i).en, npc.currentLine().en);
            assertFalse(npc.saidEverything(), "not finished at line " + i);
            assertTrue(npc.advance());
        }
        assertTrue(npc.saidEverything());
        assertFalse(npc.advance(), "the last line must not wrap back to the first");
        assertEquals(def.lines.peek().en, npc.currentLine().en);
    }

    @Test
    void talkRangeIsSymmetricAndBounded() {
        NpcDef def = people.all().get(0);
        Npc npc = new Npc(def, new StillVisual());
        assertTrue(npc.inRange(new com.badlogic.gdx.math.Vector3(def.x, 0.2f, def.z)));
        assertTrue(npc.inRange(new com.badlogic.gdx.math.Vector3(
                def.x + Npc.TALK_RANGE - 0.1f, 0.2f, def.z)));
        assertFalse(npc.inRange(new com.badlogic.gdx.math.Vector3(
                def.x + Npc.TALK_RANGE + 0.5f, 0.2f, def.z)));
    }

    /** A visual that does nothing, so the conversation logic can be tested headless. */
    private static class StillVisual implements com.muamn.ashen.entity.EnemyVisual {
        @Override public void update(float dt, Pose pose, float speed, float stateTime,
                                     com.muamn.ashen.combat.AttackDef attack, float attackT) {}
        @Override public void place(com.badlogic.gdx.math.Vector3 feet, float facingDeg) {}
        @Override public com.badlogic.gdx.graphics.g3d.ModelInstance instance() { return null; }
        @Override public void dispose() {}
    }
}
