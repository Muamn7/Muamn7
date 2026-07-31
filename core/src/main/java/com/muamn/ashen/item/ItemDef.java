package com.muamn.ashen.item;

/**
 * An item archetype, loaded from {@code assets/data/items.json}.
 *
 * Items carry one effect and one number. That is deliberate: a consumable whose
 * behaviour needs a paragraph is a mechanic, not an item, and it belongs in the
 * code that owns the mechanic. Everything here can be balanced by editing JSON.
 */
public class ItemDef {

    public enum Kind {
        /** Used from the quick slot; consumed on use. */
        CONSUMABLE,
        /** Spent at a bonfire to reinforce a weapon. Never used directly. */
        MATERIAL
    }

    public enum Effect {
        /** Restores {@code power} health. */
        HEAL,
        /** Restores {@code power} stamina at once. */
        STAMINA,
        /** Adds {@code power} flat damage to the weapon for {@code duration} seconds. */
        BUFF,
        /** Grants {@code power} souls. */
        SOULS,
        /** Raises the Estus flask by {@code power} charges, permanently. */
        FLASK,
        /** Returns the player to the last bonfire they rested at. */
        HOMEWARD,
        /** Does nothing on its own. Materials use this. */
        NONE
    }

    public String id = "item";
    public String nameAr = "عنصر";
    public String nameEn = "Item";
    /** One line, shown in the inventory. */
    public String descAr = "";
    public String descEn = "";

    public Kind kind = Kind.CONSUMABLE;
    public Effect effect = Effect.NONE;

    /** What the effect is worth. Health, stamina, souls or flask charges. */
    public float power;
    /** Seconds, for {@link Effect#BUFF}. */
    public float duration;

    /** How many can be held. Souls-in-a-jar stack high; a flask ember does not. */
    public int maxStack = 99;

    /**
     * Colour of the pickup that drops on the ground, as RRGGBBAA. Items read
     * far better on a dark floor as a coloured glow than as a tiny model.
     */
    public String glow = "d8b45cff";

    public boolean consumable() {
        return kind == Kind.CONSUMABLE;
    }

    @Override
    public String toString() {
        return id + " (" + kind + "/" + effect + " " + Math.round(power) + ")";
    }
}
