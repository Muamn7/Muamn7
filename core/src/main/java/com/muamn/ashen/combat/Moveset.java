package com.muamn.ashen.combat;

/** The attacks a weapon class can perform. */
public class Moveset {

    /** Light chain. Pressing again during recovery advances to the next entry. */
    public final AttackDef[] light;
    /** Heavy chain. Usually one entry. */
    public final AttackDef[] heavy;
    public final AttackDef running;
    public final AttackDef rolling;

    public Moveset(AttackDef[] light, AttackDef[] heavy, AttackDef running, AttackDef rolling) {
        this.light = light;
        this.heavy = heavy;
        this.running = running;
        this.rolling = rolling;
    }

    /** Wraps past the end of the chain, so holding attack keeps swinging. */
    public AttackDef light(int index) {
        return light[Math.floorMod(index, light.length)];
    }

    public AttackDef heavy(int index) {
        return heavy[Math.floorMod(index, heavy.length)];
    }

    public int lightChainLength() {
        return light.length;
    }
}
