package com.muamn.ashen.item;

import com.badlogic.gdx.utils.Array;
import com.muamn.ashen.entity.EnemyDef;
import com.muamn.ashen.entity.EnemyLibrary;
import com.muamn.ashen.ui.BonfireMenu;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.Random;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Guards the shipped item table, the drop tables that reference it, and the
 * inventory that holds the results.
 *
 * The check that matters most is the last one: reinforcement is gated behind
 * materials, so if the bosses stop dropping a tier the upgrade path silently
 * dead-ends and nothing in the game says so.
 */
class ItemsTest {

    private static ItemLibrary items;
    private static EnemyLibrary bestiary;

    @BeforeAll
    static void loadFromRepo() throws IOException {
        Path dir = Paths.get("").toAbsolutePath();
        while (dir != null && !Files.exists(dir.resolve("assets/data/items.json"))) {
            dir = dir.getParent();
        }
        assertNotNull(dir, "could not find assets/data/items.json");

        items = new ItemLibrary();
        items.parse(read(dir.resolve("assets/data/items.json")));

        bestiary = new EnemyLibrary();
        bestiary.parse(read(dir.resolve("assets/data/enemies.json")),
                       read(dir.resolve("assets/data/bosses.json")));
    }

    private static String read(Path path) throws IOException {
        return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
    }

    private static Array<EnemyDef> everything() {
        Array<EnemyDef> all = new Array<>();
        all.addAll(bestiary.all());
        all.addAll(bestiary.allBosses());
        return all;
    }

    // ---- the table --------------------------------------------------------

    @Test
    void idsAreUniqueAndNamed() {
        Set<String> ids = new HashSet<>();
        for (ItemDef def : items.all()) {
            assertTrue(ids.add(def.id), "duplicate item id: " + def.id);
            assertFalse(def.nameEn.isEmpty(), def.id + " has no English name");
            assertFalse(def.nameAr.isEmpty(), def.id + " has no Arabic name");
            assertTrue(def.maxStack > 0, def.id + " cannot be held at all");
        }
    }

    @Test
    void everyConsumableActuallyDoesSomething() {
        for (ItemDef def : items.all()) {
            if (!def.consumable()) continue;
            assertFalse(def.effect == ItemDef.Effect.NONE,
                    def.id + " is a consumable with no effect");
            assertTrue(def.power > 0f, def.id + " has no magnitude");
            if (def.effect == ItemDef.Effect.BUFF) {
                assertTrue(def.duration > 0f, def.id + " is a buff that expires instantly");
            }
        }
    }

    @Test
    void materialsAreNotUsableFromTheQuickSlot() {
        for (ItemDef def : items.all()) {
            if (def.kind != ItemDef.Kind.MATERIAL) continue;
            assertEquals(ItemDef.Effect.NONE, def.effect,
                    def.id + " is a material with a use effect, which the quick slot cannot spend");
        }
    }

    @Test
    void glowColoursParse() {
        for (ItemDef def : items.all()) {
            assertEquals(8, def.glow.length(), def.id + " glow must be RRGGBBAA");
            com.badlogic.gdx.graphics.Color.valueOf(def.glow);
        }
    }

    // ---- drop tables ------------------------------------------------------

    @Test
    void everyDropNamesAnItemThatExists() {
        for (EnemyDef def : everything()) {
            for (LootTable.Entry entry : def.loot.entries) {
                assertTrue(items.has(entry.itemId),
                        def.id + " drops unknown item '" + entry.itemId + "'");
                assertTrue(entry.chance > 0f && entry.chance <= 1f,
                        def.id + " drops " + entry.itemId + " at an impossible rate");
                assertTrue(entry.min >= 1 && entry.max >= entry.min,
                        def.id + " drops a nonsense count of " + entry.itemId);
            }
        }
    }

    @Test
    void aDropNeverExceedsWhatCanBeHeld() {
        for (EnemyDef def : everything()) {
            for (LootTable.Entry entry : def.loot.entries) {
                assertTrue(entry.max <= items.get(entry.itemId).maxStack,
                        def.id + " can drop more " + entry.itemId + " than the stack allows");
            }
        }
    }

    @Test
    void bossDropsAreGuaranteed() {
        for (EnemyDef def : bestiary.allBosses()) {
            assertFalse(def.loot.isEmpty(), def.id + " drops nothing");
            for (LootTable.Entry entry : def.loot.entries) {
                assertEquals(1f, entry.chance, 1e-6f,
                        def.id + " is fought once, so its drops cannot be a roll");
            }
        }
    }

    /**
     * The reinforcement path has to be finishable. Every material tier the
     * bonfire asks for must be obtainable, and the total the bosses hand out
     * must cover taking one weapon all the way to +10.
     */
    @Test
    void theUpgradePathIsReachable() {
        for (int level = 1; level <= 10; level++) {
            String material = BonfireMenu.reinforceMaterial(level);
            assertTrue(items.has(material),
                    "+" + level + " needs unknown material '" + material + "'");

            boolean dropped = false;
            for (EnemyDef def : everything()) {
                for (LootTable.Entry entry : def.loot.entries) {
                    if (entry.itemId.equals(material)) dropped = true;
                }
            }
            assertTrue(dropped, "nothing in the game drops " + material
                    + ", so no weapon can reach +" + level);
        }
    }

    @Test
    void guaranteedBossDropsCoverOneWeaponToTenPlus() {
        // Only the boss drops count: they are the ones that cannot be missed.
        java.util.Map<String, Integer> guaranteed = new java.util.HashMap<>();
        for (EnemyDef def : bestiary.allBosses()) {
            for (LootTable.Entry entry : def.loot.entries) {
                guaranteed.merge(entry.itemId, entry.min, Integer::sum);
            }
        }
        java.util.Map<String, Integer> needed = new java.util.HashMap<>();
        for (int level = 1; level <= 10; level++) {
            needed.merge(BonfireMenu.reinforceMaterial(level),
                    BonfireMenu.reinforceMaterialCount(level), Integer::sum);
        }
        for (java.util.Map.Entry<String, Integer> e : needed.entrySet()) {
            int have = guaranteed.getOrDefault(e.getKey(), 0);
            // Shards come from ordinary enemies, which are farmable; the tiers the
            // bosses gate are the ones that must add up.
            if (e.getKey().equals("ember_shard")) continue;
            assertTrue(have >= e.getValue(),
                    "bosses guarantee " + have + "x " + e.getKey()
                            + " but +10 needs " + e.getValue());
        }
    }

    @Test
    void reinforceCountsRestartAtEachTier() {
        assertEquals("ember_shard", BonfireMenu.reinforceMaterial(1));
        assertEquals("ember_lump", BonfireMenu.reinforceMaterial(4));
        assertEquals("ember_core", BonfireMenu.reinforceMaterial(7));
        assertEquals("ember_heart", BonfireMenu.reinforceMaterial(10));

        assertEquals(1, BonfireMenu.reinforceMaterialCount(1));
        assertEquals(3, BonfireMenu.reinforceMaterialCount(3));
        assertEquals(1, BonfireMenu.reinforceMaterialCount(4));
        assertEquals(1, BonfireMenu.reinforceMaterialCount(10));
    }

    // ---- rolling ----------------------------------------------------------

    @Test
    void aCertainDropAlwaysLandsAndAnImpossibleOneNever() {
        LootTable table = new LootTable()
                .add("always", 1f, 2, 2)
                .add("never", 0f, 1, 1);
        Random random = new Random(7);
        for (int i = 0; i < 200; i++) {
            Array<LootTable.Drop> out = table.roll(random, new Array<>());
            assertEquals(1, out.size);
            assertEquals("always", out.get(0).itemId);
            assertEquals(2, out.get(0).count);
        }
    }

    @Test
    void ratesComeOutRoughlyAsWritten() {
        LootTable table = new LootTable().add("thing", 0.25f, 1, 1);
        Random random = new Random(1234);
        int hits = 0;
        int trials = 20000;
        for (int i = 0; i < trials; i++) {
            hits += table.roll(random, new Array<>()).size;
        }
        float rate = hits / (float) trials;
        assertTrue(Math.abs(rate - 0.25f) < 0.02f, "drop rate came out at " + rate);
    }

    @Test
    void rowsRollIndependently() {
        LootTable table = new LootTable()
                .add("a", 0.5f, 1, 1)
                .add("b", 0.5f, 1, 1);
        Random random = new Random(99);
        boolean sawBoth = false, sawNeither = false, sawOne = false;
        for (int i = 0; i < 500; i++) {
            int size = table.roll(random, new Array<>()).size;
            if (size == 2) sawBoth = true;
            if (size == 0) sawNeither = true;
            if (size == 1) sawOne = true;
        }
        assertTrue(sawBoth && sawNeither && sawOne,
                "a table with two rows should produce all three outcomes");
    }

    @Test
    void countsStayInsideTheDeclaredRange() {
        LootTable table = new LootTable().add("thing", 1f, 2, 5);
        Random random = new Random(5);
        for (int i = 0; i < 500; i++) {
            int count = table.roll(random, new Array<>()).get(0).count;
            assertTrue(count >= 2 && count <= 5, "rolled " + count);
        }
    }

    // ---- inventory --------------------------------------------------------

    @Test
    void addingAndRemovingTracksTheCount() {
        Inventory inventory = new Inventory();
        ItemDef bread = items.get("charred_bread");
        assertEquals(3, inventory.add(bread, 3));
        assertEquals(3, inventory.count("charred_bread"));
        assertTrue(inventory.remove("charred_bread", 2));
        assertEquals(1, inventory.count("charred_bread"));
        assertFalse(inventory.remove("charred_bread", 2), "cannot take more than is held");
        assertEquals(1, inventory.count("charred_bread"));
        assertTrue(inventory.remove("charred_bread", 1));
        assertTrue(inventory.isEmpty());
    }

    @Test
    void theStackCapIsRespectedAndTheOverflowReported() {
        Inventory inventory = new Inventory();
        ItemDef bone = items.get("homeward_bone");
        assertEquals(bone.maxStack, inventory.add(bone, bone.maxStack + 5),
                "add must report what it actually took, not what it was offered");
        assertEquals(0, inventory.add(bone, 1), "a full stack takes nothing more");
        assertEquals(bone.maxStack, inventory.count("homeward_bone"));
    }

    @Test
    void anEmptiedStackLeavesTheOrdering() {
        Inventory inventory = new Inventory();
        inventory.add(items.get("charred_bread"), 1);
        inventory.add(items.get("dried_root"), 1);
        assertEquals(2, inventory.ids().size);
        inventory.remove("charred_bread", 1);
        assertEquals(1, inventory.ids().size);
        assertEquals("dried_root", inventory.ids().get(0));
    }

    @Test
    void encodingRoundTrips() {
        Inventory inventory = new Inventory();
        inventory.add(items.get("charred_bread"), 4);
        inventory.add(items.get("ember_shard"), 2);
        inventory.add(items.get("homeward_bone"), 1);

        Inventory restored = new Inventory();
        restored.decode(inventory.encode(), items);

        assertEquals(inventory.encode(), restored.encode());
        assertEquals(4, restored.count("charred_bread"));
        assertEquals(2, restored.count("ember_shard"));
        assertEquals(1, restored.count("homeward_bone"));
    }

    @Test
    void anEmptyInventoryRoundTrips() {
        Inventory inventory = new Inventory();
        assertEquals("", inventory.encode());
        inventory.decode("", items);
        assertTrue(inventory.isEmpty());
        inventory.decode(null, items);
        assertTrue(inventory.isEmpty());
    }

    /**
     * A save written by an older build can name an item that has since been
     * renamed or removed. That must cost the player one item, not the save.
     */
    @Test
    void decodingSurvivesJunk() {
        Inventory inventory = new Inventory();
        inventory.decode("charred_bread:2,item_that_was_deleted:9,ember_shard:notanumber,"
                + "broken,:5,ember_shard:3", items);
        assertEquals(2, inventory.count("charred_bread"));
        assertEquals(3, inventory.count("ember_shard"));
        assertEquals(2, inventory.ids().size);
    }
}
