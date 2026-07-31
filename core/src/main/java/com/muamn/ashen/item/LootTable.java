package com.muamn.ashen.item;

import com.badlogic.gdx.utils.Array;

import java.util.Random;

/**
 * What an enemy drops, and the roll that decides it.
 *
 * Each entry is rolled independently, so an enemy can drop nothing, one thing or
 * everything on its table. That is what a Souls game does, and it is also the
 * only version that stays readable when a designer adds a fourth row.
 *
 * The roll takes its {@link Random} as an argument and touches nothing else, so
 * a seeded run is reproducible and the drop rates can be unit tested by rolling
 * a table ten thousand times instead of by playing the game.
 */
public class LootTable {

    /** One row: this item, this often, this many. */
    public static class Entry {
        public final String itemId;
        /** 0..1. */
        public final float chance;
        public final int min, max;

        public Entry(String itemId, float chance, int min, int max) {
            this.itemId = itemId;
            this.chance = chance;
            this.min = Math.max(1, min);
            this.max = Math.max(this.min, max);
        }
    }

    /** One rolled result. */
    public static class Drop {
        public final String itemId;
        public final int count;

        public Drop(String itemId, int count) {
            this.itemId = itemId;
            this.count = count;
        }
    }

    public final Array<Entry> entries = new Array<>();

    public LootTable add(String itemId, float chance, int min, int max) {
        entries.add(new Entry(itemId, chance, min, max));
        return this;
    }

    public boolean isEmpty() {
        return entries.size == 0;
    }

    /** Rolls every row. Appends to {@code out} and returns it. */
    public Array<Drop> roll(Random random, Array<Drop> out) {
        for (Entry entry : entries) {
            if (random.nextFloat() >= entry.chance) continue;
            int count = entry.min + (entry.max > entry.min
                    ? random.nextInt(entry.max - entry.min + 1) : 0);
            out.add(new Drop(entry.itemId, count));
        }
        return out;
    }
}
