package com.muamn.ashen.item;

import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.ObjectIntMap;

/**
 * What the player is carrying: a count per item id.
 *
 * It serialises to a single string rather than to a map, because the save file
 * is a flat POJO read by a schema-less parser and a nested collection is the
 * thing most likely to break when the item table changes. A string round-trips
 * through any version of the file, and an id that no longer exists is dropped on
 * load rather than crashing the game.
 */
public class Inventory {

    private final ObjectIntMap<String> counts = new ObjectIntMap<>();
    /** Insertion order, so the quick-item ring is stable between sessions. */
    private final Array<String> order = new Array<>();

    /** @return how many were actually added, after the stack cap. */
    public int add(ItemDef def, int amount) {
        if (def == null || amount <= 0) return 0;
        int held = counts.get(def.id, 0);
        int room = Math.max(0, def.maxStack - held);
        int added = Math.min(amount, room);
        if (added <= 0) return 0;
        if (held == 0) order.add(def.id);
        counts.put(def.id, held + added);
        return added;
    }

    /** @return true if the whole amount was there and has been taken. */
    public boolean remove(String id, int amount) {
        if (amount <= 0) return true;
        int held = counts.get(id, 0);
        if (held < amount) return false;
        if (held == amount) {
            counts.remove(id, 0);
            order.removeValue(id, false);
        } else {
            counts.put(id, held - amount);
        }
        return true;
    }

    public int count(String id) {
        return counts.get(id, 0);
    }

    public boolean has(String id, int amount) {
        return counts.get(id, 0) >= amount;
    }

    public boolean isEmpty() {
        return order.size == 0;
    }

    /** Held item ids, in the order they were first picked up. */
    public Array<String> ids() {
        return order;
    }

    public void clear() {
        counts.clear();
        order.clear();
    }

    /** {@code id:count,id:count}. Empty string for an empty inventory. */
    public String encode() {
        StringBuilder sb = new StringBuilder();
        for (String id : order) {
            if (sb.length() > 0) sb.append(',');
            sb.append(id).append(':').append(counts.get(id, 0));
        }
        return sb.toString();
    }

    /**
     * Replaces the contents from {@link #encode}. Entries whose id is not in the
     * library, or whose count is unreadable, are skipped - a save from an older
     * build should lose one item, not fail to load.
     */
    public void decode(String encoded, ItemLibrary library) {
        clear();
        if (encoded == null || encoded.isEmpty()) return;
        for (String entry : encoded.split(",")) {
            int colon = entry.lastIndexOf(':');
            if (colon <= 0) continue;
            String id = entry.substring(0, colon).trim();
            if (!library.has(id)) continue;
            int amount;
            try {
                amount = Integer.parseInt(entry.substring(colon + 1).trim());
            } catch (NumberFormatException e) {
                continue;
            }
            add(library.get(id), amount);
        }
    }
}
