package com.muamn.ashen.combat;

/**
 * Attribute scaling grade, in the genre's usual letters.
 *
 * The multiplier is what actually feeds the damage formula; the letter exists so
 * the weapon menu can show something a player recognises.
 */
public enum Scaling {
    NONE("-", 0f),
    E("E", 0.25f),
    D("D", 0.45f),
    C("C", 0.70f),
    B("B", 1.00f),
    A("A", 1.35f),
    S("S", 1.80f);

    public final String letter;
    public final float multiplier;

    Scaling(String letter, float multiplier) {
        this.letter = letter;
        this.multiplier = multiplier;
    }
}
