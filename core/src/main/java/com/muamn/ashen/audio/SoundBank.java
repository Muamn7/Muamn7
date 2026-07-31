package com.muamn.ashen.audio;

import com.badlogic.gdx.utils.ObjectMap;

import java.util.Random;

/**
 * Every sound in the game, as a recipe.
 *
 * Kept separate from playback so the whole bank can be rendered and inspected
 * without an audio device. {@link #render} returns raw sample buffers; turning
 * those into something the speaker hears is {@link Audio}'s problem.
 *
 * The seeds are fixed. A sound that comes out different on every launch is not
 * a sound, it is a bug that only some players hear.
 */
public final class SoundBank {

    // ---- ids --------------------------------------------------------------

    public static final String SWING_LIGHT = "swing_light";
    public static final String SWING_HEAVY = "swing_heavy";
    public static final String HIT_FLESH = "hit_flesh";
    public static final String HIT_BONE = "hit_bone";
    public static final String HIT_GUARD = "hit_guard";
    public static final String PARRY = "parry";
    public static final String CRITICAL = "critical";
    public static final String STAGGER = "stagger";

    public static final String FOOTSTEP = "footstep";
    public static final String ROLL = "roll";
    public static final String LAND = "land";

    public static final String HURT = "hurt";
    public static final String DEATH = "death";
    public static final String ENEMY_DEATH = "enemy_death";

    public static final String DRINK = "drink";
    public static final String PICKUP = "pickup";
    public static final String SOULS = "souls";
    public static final String LEVEL_UP = "level_up";
    public static final String REINFORCE = "reinforce";
    public static final String MENU_MOVE = "menu_move";
    public static final String MENU_DENY = "menu_deny";

    public static final String BONFIRE_REST = "bonfire_rest";
    public static final String FOG_GATE = "fog_gate";
    public static final String BOSS_ROAR = "boss_roar";
    public static final String AREA_CHANGE = "area_change";

    /** Looping beds, played by {@link Audio} as music rather than as effects. */
    public static final String MUSIC_BOSS = "music_boss";
    public static final String AMBIENCE_WIND = "ambience_wind";

    /** Everything the bank knows how to make, in render order. */
    public static final String[] ALL = {
            SWING_LIGHT, SWING_HEAVY, HIT_FLESH, HIT_BONE, HIT_GUARD, PARRY, CRITICAL, STAGGER,
            FOOTSTEP, ROLL, LAND,
            HURT, DEATH, ENEMY_DEATH,
            DRINK, PICKUP, SOULS, LEVEL_UP, REINFORCE, MENU_MOVE, MENU_DENY,
            BONFIRE_REST, FOG_GATE, BOSS_ROAR, AREA_CHANGE,
            MUSIC_BOSS, AMBIENCE_WIND,
    };

    /** True for the long buffers that are meant to be looped, not triggered. */
    public static boolean isLoop(String id) {
        return MUSIC_BOSS.equals(id) || AMBIENCE_WIND.equals(id);
    }

    private SoundBank() {}

    /** Renders one sound by id. */
    public static float[] render(String id) {
        switch (id) {
            case SWING_LIGHT:  return swing(0.26f, 900f, 5200f, 0.9f, 11);
            case SWING_HEAVY:  return swing(0.44f, 420f, 2600f, 1.4f, 12);
            case HIT_FLESH:    return hitFlesh();
            case HIT_BONE:     return hitBone();
            case HIT_GUARD:    return hitGuard();
            case PARRY:        return parry();
            case CRITICAL:     return critical();
            case STAGGER:      return stagger();
            case FOOTSTEP:     return footstep();
            case ROLL:         return roll();
            case LAND:         return land();
            case HURT:         return hurt();
            case DEATH:        return death();
            case ENEMY_DEATH:  return enemyDeath();
            case DRINK:        return drink();
            case PICKUP:       return pickup();
            case SOULS:        return souls();
            case LEVEL_UP:     return levelUp();
            case REINFORCE:    return reinforce();
            case MENU_MOVE:    return menuMove();
            case MENU_DENY:    return menuDeny();
            case BONFIRE_REST: return bonfireRest();
            case FOG_GATE:     return fogGate();
            case BOSS_ROAR:    return bossRoar();
            case AREA_CHANGE:  return areaChange();
            case MUSIC_BOSS:   return musicBoss();
            case AMBIENCE_WIND: return ambienceWind();
            default: throw new IllegalArgumentException("unknown sound: " + id);
        }
    }

    // ---- combat -----------------------------------------------------------

    /**
     * A blade through air: noise under a filter that opens as the swing
     * accelerates and closes as it passes. The sweep is the whole sound - static
     * filtered noise is a hiss, and a hiss is not a sword.
     */
    private static float[] swing(float seconds, float fromHz, float toHz, float body, int seed) {
        float[] out = Synth.buffer(seconds);
        Synth.noise(out, 1f, new Random(seed));
        Synth.sweepLowpass(out, fromHz, toHz);
        Synth.highpass(out, 260f);
        Synth.envelope(out, seconds * 0.34f, seconds * 0.66f, 1.8f);
        if (body > 1f) {
            // Heavy weapons get a low thump under the air, or they weigh nothing.
            float[] weight = Synth.buffer(seconds * 0.5f);
            Synth.sine(weight, 90f, 44f, 1f, 1.4f);
            Synth.envelope(weight, 0.01f, seconds * 0.44f, 2.2f);
            Synth.mix(out, weight, Synth.samples(seconds * 0.3f), 0.55f);
        }
        return finish(out, 0.75f);
    }

    /** Wet and dull: a low thud with a short noise slap on the front. */
    private static float[] hitFlesh() {
        float[] out = Synth.buffer(0.22f);
        Synth.noise(out, 0.7f, new Random(21));
        Synth.lowpass(out, 900f);
        Synth.envelope(out, 0.004f, 0.16f, 3.2f);

        float[] thud = Synth.buffer(0.18f);
        Synth.sine(thud, 190f, 62f, 1f, 1.6f);
        Synth.envelope(thud, 0.002f, 0.15f, 2.4f);
        Synth.mix(out, thud, 0, 0.9f);
        return finish(out, 0.85f);
    }

    /** Harder and brighter, with a crack on top. */
    private static float[] hitBone() {
        float[] out = Synth.buffer(0.24f);
        Synth.noise(out, 1f, new Random(22));
        Synth.bandish(out, 1400f, 5200f);
        Synth.envelope(out, 0.002f, 0.10f, 4f);

        float[] crack = Synth.buffer(0.20f);
        Synth.saw(crack, 420f, 140f, 1f, 2f);
        Synth.envelope(crack, 0.001f, 0.17f, 3f);
        Synth.mix(out, crack, 0, 0.6f);
        return finish(out, 0.85f);
    }

    /** Steel on a shield: a struck bar with a long ring and a wooden knock. */
    private static float[] hitGuard() {
        float[] out = Synth.buffer(0.60f);
        // Three inharmonic partials - a harmonic stack sounds like a bell, and a
        // shield is not a bell.
        Synth.tone(out, 620f, 0.5f);
        Synth.tone(out, 1490f, 0.32f);
        Synth.tone(out, 2630f, 0.20f);
        Synth.envelope(out, 0.001f, 0.55f, 2.6f);

        float[] knock = Synth.buffer(0.14f);
        Synth.noise(knock, 1f, new Random(23));
        Synth.lowpass(knock, 1600f);
        Synth.envelope(knock, 0.001f, 0.12f, 4f);
        Synth.mix(out, knock, 0, 0.8f);
        Synth.room(out, 0.22f, 0.12f);
        return finish(out, 0.8f);
    }

    /** The parry: bright, ringing, and unmistakable. It has to be heard. */
    private static float[] parry() {
        float[] out = Synth.buffer(0.85f);
        Synth.tone(out, 1180f, 0.5f);
        Synth.tone(out, 2340f, 0.36f);
        Synth.tone(out, 3910f, 0.24f);
        Synth.tone(out, 5270f, 0.12f);
        Synth.envelope(out, 0.0008f, 0.80f, 2.0f);

        float[] strike = Synth.buffer(0.06f);
        Synth.noise(strike, 1f, new Random(24));
        Synth.highpass(strike, 2200f);
        Synth.envelope(strike, 0.0005f, 0.05f, 5f);
        Synth.mix(out, strike, 0, 0.9f);
        Synth.room(out, 0.30f, 0.16f);
        return finish(out, 0.92f);
    }

    /** The riposte or backstab: a wet stab with a low swell of finality. */
    private static float[] critical() {
        float[] out = Synth.buffer(0.75f);
        float[] stab = Synth.buffer(0.30f);
        Synth.noise(stab, 1f, new Random(25));
        Synth.sweepLowpass(stab, 5000f, 700f);
        Synth.envelope(stab, 0.003f, 0.27f, 2.6f);
        Synth.mix(out, stab, 0, 1f);

        float[] swell = Synth.buffer(0.70f);
        Synth.sine(swell, 120f, 55f, 1f, 1.3f);
        Synth.tone(swell, 82f, 0.4f);
        Synth.envelope(swell, 0.02f, 0.66f, 1.6f);
        Synth.mix(out, swell, 0, 0.8f);
        Synth.saturate(out, 1.8f);
        Synth.room(out, 0.25f, 0.20f);
        return finish(out, 0.9f);
    }

    /** Poise breaking: armour rattling as the body loses its footing. */
    private static float[] stagger() {
        float[] out = Synth.buffer(0.40f);
        Random random = new Random(26);
        for (int i = 0; i < 5; i++) {
            float[] clank = Synth.buffer(0.12f);
            Synth.tone(clank, 700f + random.nextFloat() * 900f, 0.6f);
            Synth.noise(clank, 0.35f, random);
            Synth.highpass(clank, 900f);
            Synth.envelope(clank, 0.001f, 0.10f, 3.4f);
            Synth.mix(out, clank, Synth.samples(i * 0.055f), 0.7f);
        }
        return finish(out, 0.7f);
    }

    // ---- movement ---------------------------------------------------------

    /** A boot on stone: a click, then a short scrape. */
    private static float[] footstep() {
        float[] out = Synth.buffer(0.16f);
        Synth.noise(out, 1f, new Random(31));
        Synth.sweepLowpass(out, 2600f, 700f);
        Synth.envelope(out, 0.002f, 0.13f, 3.6f);

        float[] heel = Synth.buffer(0.07f);
        Synth.sine(heel, 150f, 80f, 1f, 1.5f);
        Synth.envelope(heel, 0.001f, 0.06f, 3f);
        Synth.mix(out, heel, 0, 0.7f);
        return finish(out, 0.42f);
    }

    /** Cloth and plate tumbling: a broad scrape with a thump at each end. */
    private static float[] roll() {
        float[] out = Synth.buffer(0.52f);
        Synth.noise(out, 1f, new Random(32));
        Synth.sweepLowpass(out, 1500f, 400f);
        Synth.envelope(out, 0.03f, 0.48f, 1.4f);

        float[] thump = Synth.buffer(0.12f);
        Synth.sine(thump, 130f, 62f, 1f, 1.6f);
        Synth.envelope(thump, 0.001f, 0.11f, 2.6f);
        Synth.mix(out, thump, 0, 0.8f);
        Synth.mix(out, thump, Synth.samples(0.34f), 0.6f);
        return finish(out, 0.6f);
    }

    /** Landing: heavier than a step, with the room answering. */
    private static float[] land() {
        float[] out = Synth.buffer(0.45f);
        Synth.sine(out, 160f, 48f, 0.9f, 1.7f);
        Synth.envelope(out, 0.002f, 0.26f, 2.4f);

        float[] grit = Synth.buffer(0.22f);
        Synth.noise(grit, 1f, new Random(33));
        Synth.lowpass(grit, 1800f);
        Synth.envelope(grit, 0.002f, 0.20f, 3f);
        Synth.mix(out, grit, 0, 0.55f);
        Synth.room(out, 0.20f, 0.18f);
        return finish(out, 0.72f);
    }

    // ---- flesh and death --------------------------------------------------

    private static float[] hurt() {
        float[] out = Synth.buffer(0.42f);
        Synth.saw(out, 240f, 165f, 0.7f, 1.4f);
        Synth.tone(out, 118f, 0.35f);
        Synth.lowpass(out, 2200f);
        Synth.noise(out, 0.10f, new Random(41));
        Synth.envelope(out, 0.015f, 0.40f, 1.9f);
        return finish(out, 0.68f);
    }

    /** The player dying: a long fall in pitch, then the room swallowing it. */
    private static float[] death() {
        float[] out = Synth.buffer(1.60f);
        Synth.saw(out, 210f, 48f, 0.6f, 1.8f);
        Synth.sine(out, 105f, 26f, 0.5f, 1.8f);
        Synth.lowpass(out, 1400f);
        Synth.envelope(out, 0.05f, 1.5f, 1.5f);
        Synth.room(out, 0.40f, 0.35f);
        return finish(out, 0.8f);
    }

    private static float[] enemyDeath() {
        float[] out = Synth.buffer(0.85f);
        Synth.saw(out, 300f, 70f, 0.6f, 1.7f);
        Synth.noise(out, 0.30f, new Random(42));
        Synth.lowpass(out, 1800f);
        Synth.envelope(out, 0.01f, 0.80f, 1.9f);

        // The body hitting the floor, a beat after the cry.
        float[] fall = Synth.buffer(0.30f);
        Synth.sine(fall, 140f, 52f, 1f, 1.6f);
        Synth.noise(fall, 0.35f, new Random(43));
        Synth.lowpass(fall, 900f);
        Synth.envelope(fall, 0.002f, 0.28f, 2.6f);
        Synth.mix(out, fall, Synth.samples(0.42f), 0.8f);
        return finish(out, 0.75f);
    }

    // ---- items and menus --------------------------------------------------

    private static float[] drink() {
        float[] out = Synth.buffer(0.70f);
        Random random = new Random(51);
        // Four gulps, each a short filtered noise burst with a rising pitch.
        for (int i = 0; i < 4; i++) {
            float[] gulp = Synth.buffer(0.13f);
            Synth.noise(gulp, 1f, random);
            Synth.sweepLowpass(gulp, 500f + i * 110f, 900f + i * 140f);
            Synth.envelope(gulp, 0.008f, 0.11f, 2.4f);
            Synth.mix(out, gulp, Synth.samples(i * 0.145f), 0.9f);
        }
        return finish(out, 0.55f);
    }

    private static float[] pickup() {
        float[] out = Synth.buffer(0.42f);
        Synth.tone(out, 1046f, 0.4f);   // C6
        Synth.tone(out, 1568f, 0.28f);  // G6
        Synth.envelope(out, 0.004f, 0.38f, 2.6f);
        Synth.room(out, 0.20f, 0.10f);
        return finish(out, 0.6f);
    }

    /** Souls arriving: a soft, cold shimmer rather than a coin sound. */
    private static float[] souls() {
        float[] out = Synth.buffer(0.55f);
        Synth.sine(out, 780f, 1170f, 0.35f, 0.7f);
        Synth.sine(out, 1170f, 1560f, 0.22f, 0.7f);
        Synth.envelope(out, 0.03f, 0.50f, 2f);
        Synth.room(out, 0.28f, 0.14f);
        return finish(out, 0.5f);
    }

    /** Levelling: a rising fifth, warm, with the room behind it. */
    private static float[] levelUp() {
        float[] out = Synth.buffer(1.30f);
        float[] low = Synth.buffer(1.20f);
        Synth.tone(low, 261f, 0.5f);
        Synth.tone(low, 392f, 0.4f);
        Synth.envelope(low, 0.06f, 1.1f, 1.6f);
        Synth.mix(out, low, 0, 1f);

        float[] high = Synth.buffer(0.95f);
        Synth.tone(high, 523f, 0.4f);
        Synth.tone(high, 784f, 0.3f);
        Synth.envelope(high, 0.05f, 0.9f, 1.7f);
        Synth.mix(out, high, Synth.samples(0.22f), 1f);
        Synth.room(out, 0.34f, 0.28f);
        return finish(out, 0.72f);
    }

    /** The hammer on the anvil: two strikes, metal and heavy. */
    private static float[] reinforce() {
        float[] out = Synth.buffer(0.95f);
        for (int i = 0; i < 2; i++) {
            float[] strike = Synth.buffer(0.55f);
            Synth.tone(strike, 540f + i * 70f, 0.5f);
            Synth.tone(strike, 1310f + i * 90f, 0.3f);
            Synth.noise(strike, 0.4f, new Random(52 + i));
            Synth.highpass(strike, 700f);
            Synth.envelope(strike, 0.001f, 0.5f, 2.8f);
            Synth.mix(out, strike, Synth.samples(i * 0.26f), 0.9f);
        }
        Synth.room(out, 0.26f, 0.18f);
        return finish(out, 0.75f);
    }

    private static float[] menuMove() {
        float[] out = Synth.buffer(0.09f);
        Synth.tone(out, 880f, 0.5f);
        Synth.noise(out, 0.20f, new Random(53));
        Synth.highpass(out, 600f);
        Synth.envelope(out, 0.001f, 0.08f, 3.4f);
        return finish(out, 0.38f);
    }

    private static float[] menuDeny() {
        float[] out = Synth.buffer(0.24f);
        Synth.saw(out, 200f, 130f, 0.5f, 1.2f);
        Synth.lowpass(out, 1200f);
        Synth.envelope(out, 0.004f, 0.22f, 2.2f);
        return finish(out, 0.45f);
    }

    // ---- world ------------------------------------------------------------

    /** Resting: the fire taking, and a low warm swell of safety. */
    private static float[] bonfireRest() {
        float[] out = Synth.buffer(1.80f);
        float[] flare = Synth.buffer(1.20f);
        Synth.noise(flare, 1f, new Random(61));
        Synth.sweepLowpass(flare, 4200f, 700f);
        Synth.envelope(flare, 0.10f, 1.05f, 1.5f);
        Synth.mix(out, flare, 0, 0.7f);

        float[] warmth = Synth.buffer(1.70f);
        Synth.tone(warmth, 196f, 0.45f);   // G3
        Synth.tone(warmth, 294f, 0.34f);   // D4
        Synth.envelope(warmth, 0.30f, 1.4f, 1.4f);
        Synth.mix(out, warmth, Synth.samples(0.08f), 1f);
        Synth.room(out, 0.30f, 0.30f);
        return finish(out, 0.7f);
    }

    /** Passing a fog gate: a soft roar of air and a low held note. */
    private static float[] fogGate() {
        float[] out = Synth.buffer(1.50f);
        Synth.noise(out, 1f, new Random(62));
        Synth.sweepLowpass(out, 700f, 240f);
        Synth.envelope(out, 0.18f, 1.3f, 1.5f);

        float[] drone = Synth.buffer(1.40f);
        Synth.tone(drone, 73f, 0.55f);
        Synth.tone(drone, 110f, 0.30f);
        Synth.envelope(drone, 0.12f, 1.25f, 1.3f);
        Synth.mix(out, drone, 0, 1f);
        Synth.room(out, 0.34f, 0.32f);
        return finish(out, 0.78f);
    }

    /** The boss noticing you. Low, loud, and longer than anything else. */
    private static float[] bossRoar() {
        float[] out = Synth.buffer(2.20f);
        Synth.saw(out, 96f, 58f, 0.55f, 1.5f);
        Synth.saw(out, 62f, 39f, 0.45f, 1.5f);
        Synth.noise(out, 0.30f, new Random(63));
        Synth.lowpass(out, 1500f);
        // A slow wobble in the pitch reads as breath rather than as a synth.
        for (int i = 0; i < out.length; i++) {
            out[i] *= 0.82f + 0.18f * (float) Math.sin(i * 7.4 * Math.PI / Synth.SAMPLE_RATE);
        }
        Synth.envelope(out, 0.14f, 2.0f, 1.35f);
        Synth.saturate(out, 2.2f);
        Synth.room(out, 0.42f, 0.42f);
        return finish(out, 0.95f);
    }

    /** Arriving somewhere new: a quiet, hollow chord. */
    private static float[] areaChange() {
        float[] out = Synth.buffer(2.00f);
        Synth.tone(out, 110f, 0.40f);
        Synth.tone(out, 165f, 0.28f);
        Synth.tone(out, 220f, 0.20f);
        Synth.envelope(out, 0.40f, 1.6f, 1.3f);
        Synth.room(out, 0.36f, 0.40f);
        return finish(out, 0.6f);
    }

    // ---- loops ------------------------------------------------------------

    /**
     * The boss bed: a drone in D with a slow-breathing fifth over it.
     *
     * Not a melody. A tune would need a composer and would wear out over the
     * twentieth attempt at the same boss; a bed that swells and recedes does the
     * one job the music has, which is to say the fight has not ended yet.
     */
    private static float[] musicBoss() {
        float[] out = Synth.buffer(12f);
        Synth.tone(out, 73.4f, 0.42f);    // D2
        Synth.tone(out, 110.0f, 0.26f);   // A2
        Synth.tone(out, 146.8f, 0.18f);   // D3
        Synth.tone(out, 174.6f, 0.10f);   // F3, the minor third
        Synth.lowpass(out, 2200f);

        // Two slow swells across the loop, out of phase, so it never sits still.
        for (int i = 0; i < out.length; i++) {
            double t = i / (double) out.length;
            float slow = 0.62f + 0.38f * (float) Math.sin(t * 2 * Math.PI - Math.PI / 2);
            float slower = 0.80f + 0.20f * (float) Math.sin(t * 6 * Math.PI);
            out[i] *= slow * slower;
        }

        // A distant drum on the beat, quiet enough to feel rather than hear.
        for (int beat = 0; beat < 8; beat++) {
            float[] hit = Synth.buffer(0.55f);
            Synth.sine(hit, 68f, 40f, 1f, 1.7f);
            Synth.envelope(hit, 0.004f, 0.5f, 2.4f);
            Synth.mix(out, hit, Synth.samples(beat * 1.5f), 0.30f);
        }
        Synth.room(out, 0.30f, 0.45f);
        Synth.normalise(out, 0.62f);
        return Synth.seamlessLoop(out, 0.8f);
    }

    /** Wind over stone. The bed under every area that is not a boss fight. */
    private static float[] ambienceWind() {
        float[] out = Synth.buffer(10f);
        Synth.noise(out, 1f, new Random(71));
        Synth.lowpass(out, 520f);
        Synth.highpass(out, 60f);
        for (int i = 0; i < out.length; i++) {
            double t = i / (double) out.length;
            // Three gusts per loop, at slightly different rates so they drift.
            float gust = 0.45f
                    + 0.30f * (float) Math.sin(t * 6 * Math.PI)
                    + 0.25f * (float) Math.sin(t * 10 * Math.PI + 1.3);
            out[i] *= Math.max(0.08f, gust);
        }
        Synth.normalise(out, 0.5f);
        return Synth.seamlessLoop(out, 1.2f);
    }

    // ---- shared -----------------------------------------------------------

    /** Normalise and remove the end clicks. Every one-shot ends here. */
    private static float[] finish(float[] out, float peak) {
        Synth.normalise(out, peak);
        Synth.deClick(out, 0.004f);
        return out;
    }

    /** Renders the whole bank. Used by the tests and by the cache builder. */
    public static ObjectMap<String, float[]> renderAll() {
        ObjectMap<String, float[]> bank = new ObjectMap<>();
        for (String id : ALL) bank.put(id, render(id));
        return bank;
    }
}
