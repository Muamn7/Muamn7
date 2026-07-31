package com.muamn.ashen.npc;

import com.badlogic.gdx.utils.Array;

import com.muamn.ashen.entity.BodyDef;

/**
 * Someone still standing, loaded from {@code assets/data/npcs.json}.
 *
 * NPCs reuse the enemy body description rather than getting a rig of their own.
 * A merchant and a hollow soldier are the same silhouette wearing different
 * materials, and the difference that matters is not how they are built - it is
 * that one of them talks.
 */
public class NpcDef {

    /** One spoken line, in both languages. */
    public static class Line {
        public final String ar;
        public final String en;

        public Line(String ar, String en) {
            this.ar = ar;
            this.en = en;
        }
    }

    /** One row of a merchant's stock. */
    public static class Offer {
        public final String itemId;
        public final long price;

        public Offer(String itemId, long price) {
            this.itemId = itemId;
            this.price = price;
        }
    }

    public String id = "npc";
    public String nameAr = "";
    public String nameEn = "";

    /** Area id from {@code Areas}, and where they stand in it. */
    public String area = "";
    public float x, z, facing;

    public BodyDef body = new BodyDef();

    /**
     * What they say, in order. The last line repeats once it is reached, which
     * is how a Souls NPC behaves after you have heard everything they have.
     */
    public final Array<Line> lines = new Array<>();

    /** What they sell. Empty for anyone who is not a merchant. */
    public final Array<Offer> shop = new Array<>();

    public boolean isMerchant() {
        return shop.size > 0;
    }

    @Override
    public String toString() {
        return id + " (" + area + ", " + lines.size + " lines, " + shop.size + " offers)";
    }
}
