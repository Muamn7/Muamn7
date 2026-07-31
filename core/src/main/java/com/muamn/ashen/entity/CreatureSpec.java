package com.muamn.ashen.entity;

import com.badlogic.gdx.graphics.Color;

/**
 * A non-humanoid body, described as a limb plan rather than a shape.
 *
 * Twenty enemy types cannot each be a hand-built model, and they cannot all be
 * humanoids either or the bestiary reads as one soldier in twenty hats. So a
 * creature is a torso plus N pairs of legs plus optional head, tail and wings,
 * and one builder and one animator cover dogs, spiders, bats and serpents alike.
 * Changing {@link #legPairs} from 2 to 4 turns a hound into a spider.
 */
public class CreatureSpec {

    /** 1 = biped, 2 = quadruped, 3 = hexapod, 4 = spider. 0 = legless. */
    public int legPairs = 2;

    // ---- torso ----
    public float bodyLength = 1.30f;
    public float bodyWidth = 0.52f;
    public float bodyHeight = 0.46f;
    /** Height of the torso's underside above the feet. */
    public float rideHeight = 0.72f;
    /** Torso taper: <1 narrows toward the tail. */
    public float rearTaper = 0.80f;

    // ---- legs ----
    public float legLength = 0.70f;
    public float legThickness = 0.11f;
    /** How far the legs splay out sideways from the body. */
    public float legSpread = 0.30f;
    /** Fraction of leg length in the upper segment. */
    public float thighFraction = 0.52f;
    /** Degrees the knee bends outward; a spider's is far more than a dog's. */
    public float kneeFlare = 18f;

    // ---- head ----
    public boolean head = true;
    public float headLength = 0.42f;
    public float headWidth = 0.30f;
    /** How far the neck reaches forward and up from the torso front. */
    public float neckLength = 0.24f;
    public float neckRise = 0.10f;
    /** Number of jaw/horn spikes. */
    public int fangs = 4;

    // ---- extras ----
    public boolean tail;
    public float tailLength = 0.70f;
    public int tailSegments = 4;

    public boolean wings;
    public float wingSpan = 1.4f;

    /** Rows of spikes down the spine. */
    public int spines;

    // ---- look ----
    public String bodyMaterial = "flesh_rot";
    public String limbMaterial = "flesh_rot";
    public String detailMaterial = "bone";
    public Color tint = new Color(Color.WHITE);

    /** How fast the gait cycles per metre travelled. */
    public float stridePerMetre = 1.9f;
    /** Vertical bob amplitude while moving. */
    public float bob = 0.05f;

    public float overallScale = 1f;

    // ---- presets ----

    /** Low, fast, four legs. Rushes and bites. */
    public static CreatureSpec hound() {
        CreatureSpec s = new CreatureSpec();
        s.legPairs = 2;
        s.bodyLength = 1.15f;
        s.bodyWidth = 0.42f;
        s.bodyHeight = 0.40f;
        s.rideHeight = 0.62f;
        s.legLength = 0.60f;
        s.legThickness = 0.09f;
        s.legSpread = 0.20f;
        s.kneeFlare = 12f;
        s.headLength = 0.40f;
        s.headWidth = 0.26f;
        s.neckLength = 0.20f;
        s.tail = true;
        s.tailLength = 0.55f;
        s.stridePerMetre = 2.4f;
        s.bodyMaterial = "leather";
        s.limbMaterial = "leather";
        return s;
    }

    /** Eight legs, splayed wide, body slung low between them. */
    public static CreatureSpec spider() {
        CreatureSpec s = new CreatureSpec();
        s.legPairs = 4;
        s.bodyLength = 1.05f;
        s.bodyWidth = 0.72f;
        s.bodyHeight = 0.52f;
        s.rideHeight = 0.78f;
        s.rearTaper = 1.25f;              // bulbous abdomen
        s.legLength = 0.95f;
        s.legThickness = 0.07f;
        s.legSpread = 0.52f;
        s.thighFraction = 0.45f;
        s.kneeFlare = 62f;                // the high-elbow spider stance
        s.headLength = 0.24f;
        s.headWidth = 0.30f;
        s.neckLength = 0.10f;
        s.neckRise = 0f;
        s.fangs = 6;
        s.stridePerMetre = 2.8f;
        s.bob = 0.03f;
        s.bodyMaterial = "flesh_rot";
        s.limbMaterial = "iron";
        return s;
    }

    /** Membranous wings, tiny legs, hangs in the air. */
    public static CreatureSpec bat() {
        CreatureSpec s = new CreatureSpec();
        s.legPairs = 1;
        s.bodyLength = 0.70f;
        s.bodyWidth = 0.34f;
        s.bodyHeight = 0.36f;
        s.rideHeight = 1.20f;
        s.legLength = 0.28f;
        s.legThickness = 0.05f;
        s.legSpread = 0.14f;
        s.headLength = 0.26f;
        s.headWidth = 0.24f;
        s.neckLength = 0.08f;
        s.wings = true;
        s.wingSpan = 1.7f;
        s.fangs = 3;
        s.bob = 0.10f;
        s.stridePerMetre = 4.0f;
        s.bodyMaterial = "leather";
        s.limbMaterial = "cloth_dark";
        return s;
    }

    /** Legless, long, segmented. Drags itself along the ground. */
    public static CreatureSpec serpent() {
        CreatureSpec s = new CreatureSpec();
        s.legPairs = 0;
        s.bodyLength = 1.60f;
        s.bodyWidth = 0.44f;
        s.bodyHeight = 0.40f;
        s.rideHeight = 0.30f;
        s.rearTaper = 0.55f;
        s.headLength = 0.46f;
        s.headWidth = 0.34f;
        s.neckLength = 0.26f;
        s.neckRise = 0.22f;
        s.tail = true;
        s.tailLength = 1.25f;
        s.tailSegments = 6;
        s.fangs = 5;
        s.spines = 6;
        s.bob = 0.02f;
        s.stridePerMetre = 1.4f;
        s.bodyMaterial = "flesh_rot";
        return s;
    }

    /** Squat, heavy, four thick legs and a spined back. */
    public static CreatureSpec drake() {
        CreatureSpec s = new CreatureSpec();
        s.legPairs = 2;
        s.bodyLength = 2.20f;
        s.bodyWidth = 0.95f;
        s.bodyHeight = 0.85f;
        s.rideHeight = 1.10f;
        s.legLength = 1.05f;
        s.legThickness = 0.20f;
        s.legSpread = 0.42f;
        s.kneeFlare = 22f;
        s.headLength = 0.75f;
        s.headWidth = 0.48f;
        s.neckLength = 0.55f;
        s.neckRise = 0.28f;
        s.fangs = 7;
        s.tail = true;
        s.tailLength = 1.6f;
        s.tailSegments = 5;
        s.spines = 7;
        s.wings = true;
        s.wingSpan = 2.6f;
        s.stridePerMetre = 1.1f;
        s.bodyMaterial = "stone_dark";
        s.limbMaterial = "stone_dark";
        s.detailMaterial = "bone";
        return s;
    }

    /** Chest-high, blind, all mouth. */
    public static CreatureSpec maggot() {
        CreatureSpec s = new CreatureSpec();
        s.legPairs = 0;
        s.bodyLength = 1.20f;
        s.bodyWidth = 0.60f;
        s.bodyHeight = 0.60f;
        s.rideHeight = 0.34f;
        s.rearTaper = 0.70f;
        s.head = true;
        s.headLength = 0.34f;
        s.headWidth = 0.44f;
        s.neckLength = 0.06f;
        s.fangs = 8;
        s.spines = 4;
        s.bob = 0.07f;
        s.stridePerMetre = 2.2f;
        s.bodyMaterial = "flesh_rot";
        return s;
    }
}
