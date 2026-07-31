package com.muamn.ashen.world;

import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.VertexAttributes.Usage;
import com.badlogic.gdx.graphics.g3d.Material;
import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.graphics.g3d.attributes.ColorAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.TextureAttribute;
import com.badlogic.gdx.graphics.g3d.utils.MeshPartBuilder;
import com.badlogic.gdx.graphics.g3d.utils.ModelBuilder;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.GdxRuntimeException;

/**
 * The world: four connected areas and the primitives they are built from.
 *
 * Areas are built on demand rather than all held in memory. A phone has no room
 * for four levels at once, and rebuilding one takes a few milliseconds because
 * it is all boxes and ramps - so the transition cost is a loading pause nobody
 * notices, and the memory cost is always exactly one area.
 *
 * Each area declares its own bonfires, enemy placements, boss arenas and exits,
 * which is what makes the world a graph rather than a sequence.
 */
public final class Areas {

    public static final String ASYLUM = "asylum_courtyard";
    public static final String TOWN = "ash_town";
    public static final String WALL = "broken_wall";
    public static final String TEMPLE = "deep_temple";

    /** Every area id, in the order the player is meant to see them. */
    public static final String[] ALL = {ASYLUM, TOWN, WALL, TEMPLE};

    private Areas() {}

    /** Builds an area by id. */
    public static Level build(String id, TextureFactory textures) {
        switch (id) {
            case ASYLUM: return asylumCourtyard(textures);
            case TOWN:   return ashTown(textures);
            case WALL:   return brokenWall(textures);
            case TEMPLE: return deepTemple(textures);
            default: throw new GdxRuntimeException("unknown area: " + id);
        }
    }

    public static boolean exists(String id) {
        for (String area : ALL) if (area.equals(id)) return true;
        return false;
    }

    // ======================================================================
    // Area 1: the asylum courtyard - where the game starts
    // ======================================================================

    public static Level asylumCourtyard(TextureFactory textures) {
        LevelBuilder b = new LevelBuilder(textures);

        // --- ground: a cobbled courtyard ringed by ash ---
        b.box("cobble", 0f, -0.5f, 0f, 24f, 1f, 24f, true);
        b.box("ash", 0f, -0.5f, 21f, 60f, 1f, 18f, true);
        b.box("stone_dark", 0f, -0.5f, 36f, 12f, 1f, 18f, true);
        b.box("cobble", 0f, -0.5f, 52f, 34f, 1f, 32f, true);
        b.box("ash", 0f, -0.5f, -21f, 60f, 1f, 18f, true);
        b.box("ash", 21f, -0.5f, 0f, 18f, 1f, 24f, true);
        b.box("ash", -21f, -0.5f, 0f, 18f, 1f, 24f, true);

        // --- north terrace, reached by a broad stair ---
        b.box("stone", 0f, 1f, 20f, 26f, 2f, 14f, true);
        b.ramp("stone", 0f, 0f, 10.5f, 8f, 2f, 5f, 0f, true);
        for (int i = 0; i < 6; i++) {
            float h = 0.34f * (i + 1);
            b.box("stone_dark", -11f, h * 0.5f, 12.8f - i * 0.9f, 3.4f, h, 0.9f, true);
        }

        // --- perimeter wall, broken open in two places ---
        // The southern breach is narrow on purpose: it is the way to the town, and
        // the exit trigger has to catch anyone who walks through it.
        wallRun(b, -30f, 30f, 29.4f, true, 6f, 1.2f, new float[][]{{-6f, 6f}});
        wallRun(b, -30f, 30f, -29.4f, true, 6f, 1.2f, new float[][]{{-3f, 3f}});
        wallRun(b, -30f, 30f, 29.4f, false, 6f, 1.2f, new float[][]{{6f, 15f}});
        wallRun(b, -30f, 30f, -29.4f, false, 6f, 1.2f, new float[][]{{1.5f, 6.5f}});
        b.box("stone_dark", 0f, 5f, -29.4f, 8f, 1.4f, 1.6f, false);   // lintel over the breach

        // --- the causeway north to the boss ---
        b.box("brick", -6.6f, 2.4f, 36f, 1.2f, 4.8f, 18f, true);
        b.box("brick", 6.6f, 2.4f, 36f, 1.2f, 4.8f, 18f, true);
        arenaWall(b, 0f, 52f, 16f, 5.5f);
        b.column("stone_dark", -10f, 0f, 52f, 0.8f, 6.5f, 8, true);
        b.column("stone_dark", 10f, 0f, 52f, 0.8f, 6.5f, 8, true);
        b.column("stone_dark", 0f, 0f, 62f, 0.8f, 6.5f, 8, true);

        b.blocker(0f, 4f, 69f, 40f, 10f, 1.5f);
        b.blocker(30.6f, 4f, 0f, 1.5f, 10f, 62f);
        // Split around the alcove: the fence has to stop where the secret starts.
        b.blocker(-30.6f, 4f, -15.5f, 1.5f, 10f, 31f);
        b.blocker(-30.6f, 4f, 20.5f, 1.5f, 10f, 21f);
        // Backstop behind the breach, so a missed trigger is a bump and not a fall.
        b.blocker(0f, 4f, -30.3f, 10f, 10f, 1.2f);

        float[][] columns = {{-9f, -9f}, {9f, -9f}, {-9f, 9f}, {9f, 9f}, {-9f, 0f}, {9f, 0f}};
        for (float[] c : columns) {
            b.column("stone_dark", c[0], 0f, c[1], 0.72f, 7.2f, 8, true);
            b.box("stone", c[0], 7.4f, c[1], 2f, 0.5f, 2f, false);
            b.box("stone", c[0], 0.18f, c[1], 2.1f, 0.36f, 2.1f, true);
        }

        b.column("stone_dark", -4.5f, 2f, 20f, 0.6f, 5f, 8, true);
        b.column("stone_dark", 4.5f, 2f, 20f, 0.6f, 5f, 8, true);
        b.box("stone", 0f, 7.4f, 20f, 11f, 0.8f, 1.6f, true);
        b.box("stone", 0f, 8.1f, 20f, 9f, 0.6f, 1.2f, false);

        // The alcove behind the west wall. Nothing marks it from the courtyard.
        b.box("cobble", -33f, -0.5f, 5f, 10f, 1f, 8f, true);
        b.box("brick", -38.5f, 2.5f, 5f, 1.2f, 5f, 9f, true);
        b.box("brick", -33f, 2.5f, 0.6f, 12f, 5f, 1.2f, true);
        b.box("brick", -33f, 2.5f, 9.4f, 12f, 5f, 1.2f, true);
        b.box("stone_dark", -33f, 5.4f, 5f, 12f, 0.8f, 10f, false);

        rubble(b, -6.2f, -4.4f, 3);
        b.box("stone_dark", 7.4f, 0.3f, -7.2f, 2.4f, 0.6f, 1.8f, true);
        b.box("stone", -13.5f, 0.9f, -2f, 1.4f, 1.8f, 6f, true);

        Level level = finish(b, ASYLUM, "ساحة المصح", "Asylum Courtyard", textures);
        level.spawn.set(5.5f, 0.2f, -9.5f);
        level.spawnFacing = -22f;
        level.bonfire(0f, -6f);

        level.addSpawn("hollow_soldier", -8f, -16f, 60f)
             .addSpawn("hollow_soldier", 10f, 6f, 250f)
             .addSpawn("hollow_soldier", -13f, 14f, 150f)
             .addSpawn("hollow_archer", 12f, 21f, 200f)
             .addSpawn("feral_hound", 3f, -18f, 200f)
             .addSpawn("feral_hound", -3f, -20f, 190f)
             .addSpawn("grave_ghoul", 16f, -14f, 300f)
             .addSpawn("crag_spider", -18f, -6f, 90f)
             .addSpawn("crypt_bat", 7f, 34f, 180f)
             .addSpawn("bone_knight", 0f, 30f, 180f)
             .addSpawn("fallen_knight", -4f, 20f, 170f);

        // The gate stands in the opening of the arena wall, which arenaWall leaves
        // on the south side - so it is at the centre minus the ring radius.
        BossArena arena = new BossArena("asylum_boss", "ashen_knight",
                0f, 52f, 15.5f, 0f, 36f, 0f, 7f, 0f, 58f);
        arena.buildVisual(textures);
        level.arenas.add(arena);

        // South gap in the wall leads down into the town.
        level.portal(new Portal(TOWN, 0f, -29f, 3.4f, 0f, 38f, 180f,
                "إلى بلدة الرماد", "To Ash Town", false));

        // Two plates set into the causeway walls, firing across it at different
        // heights of the run. There is no safe line - you watch the click and
        // pick your moment, or you take one on the way through.
        level.trap(Trap.dart(-5.6f, 29f, 90f, 46f))
             .trap(Trap.dart(5.6f, 34f, 270f, 46f));

        // Behind the west wall's blind end: the first secret in the game, put
        // somewhere a player who tests walls at all will find it.
        level.secret(new IllusoryWall("asylum_west", -29.4f, 0f, 4f, 90f,
                5.2f, 6f, 1.2f, "brick"));
        level.treasure("flask_ember", 1, -33f, 4f);
        level.treasure("soul_of_a_hollow", 2, -33.5f, 6.5f);

        mood(level, 0.40f, 0.42f, 0.41f, 0.30f, 0.32f, 0.36f, 12f, 58f);
        addBonfireProps(level, textures);
        return level;
    }

    // ======================================================================
    // Area 2: Ash Town - the hub
    // ======================================================================

    public static Level ashTown(TextureFactory textures) {
        LevelBuilder b = new LevelBuilder(textures);

        // A wide dirt street with buildings either side.
        b.box("dirt", 0f, -0.5f, 0f, 70f, 1f, 96f, true);
        b.box("cobble", 0f, -0.4f, 0f, 14f, 1f, 90f, true);   // the road itself

        // Houses down both sides, alternating depth so the street is not a corridor.
        // They stop short of z=33 so the chapel gatehouse stands clear at the end.
        for (int i = 0; i < 6; i++) {
            float z = -36f + i * 12f;
            float depth = 8f + (i % 3) * 2.5f;
            building(b, -15f - depth * 0.5f, z, depth, 9f, 5.5f + (i % 2) * 1.8f);
            building(b, 15f + depth * 0.5f, z + 5f, depth, 9f, 5f + ((i + 1) % 2) * 2.2f);
        }

        // A ruined chapel astride the road at the north end. It is two wings with a
        // roof spanning them, so the way out of town passes underneath it.
        b.box("stone", -13f, 3f, 40f, 12f, 6f, 14f, true);
        b.box("stone", 13f, 3f, 40f, 12f, 6f, 14f, true);
        b.box("stone_dark", 0f, 6.4f, 40f, 34f, 1f, 16f, false);
        b.column("stone", -8.6f, 0f, 31f, 0.7f, 6f, 8, true);
        b.column("stone", 8.6f, 0f, 31f, 0.7f, 6f, 8, true);

        b.column("stone_dark", 0f, 0f, -4f, 1.8f, 1.2f, 10, true);   // well rim
        b.box("wood", 0f, 2.4f, -4f, 0.3f, 2.4f, 0.3f, true);

        // Dead trees along the verge.
        for (int i = 0; i < 5; i++) {
            float z = -30f + i * 13f;
            float x = (i % 2 == 0 ? -11.5f : 11.5f);
            b.column("wood", x, 0f, z, 0.30f, 4.2f, 6, true);
        }

        // Town walls. Three gaps, one per exit: north to the asylum, south to the
        // wall, west to the temple stair. Each is narrow enough that the matching
        // portal trigger covers the whole opening.
        wallRun(b, -35f, 35f, 47.4f, true, 7f, 1.4f, new float[][]{{-4f, 4f}});
        wallRun(b, -35f, 35f, -47.4f, true, 7f, 1.4f, new float[][]{{-4f, 4f}});
        wallRun(b, -47f, 47f, 34.4f, false, 7f, 1.4f, new float[][]{});
        wallRun(b, -47f, 47f, -34.4f, false, 7f, 1.4f, new float[][]{{-4f, 4f}});
        b.box("stone_dark", 0f, 5.6f, 47.4f, 10f, 1.6f, 1.8f, false);
        b.box("stone_dark", 0f, 5.6f, -47.4f, 10f, 1.6f, 1.8f, false);
        b.box("stone_dark", -34.4f, 5.6f, 0f, 1.8f, 1.6f, 10f, false);

        b.blocker(0f, 5f, 49f, 74f, 12f, 1.5f);
        b.blocker(0f, 5f, -49f, 74f, 12f, 1.5f);
        b.blocker(36f, 5f, 0f, 1.5f, 12f, 100f);
        b.blocker(-36f, 5f, 0f, 1.5f, 12f, 100f);

        rubble(b, -6f, 12f, 4);
        rubble(b, 8f, -20f, 3);

        Level level = finish(b, TOWN, "بلدة الرماد", "Ash Town", textures);
        level.spawn.set(0f, 0.2f, 38f);
        level.spawnFacing = 180f;
        level.bonfire(0f, 24f);

        level.addSpawn("hollow_soldier", -4f, 16f, 180f)
             .addSpawn("hollow_soldier", 5f, 8f, 200f)
             .addSpawn("hollow_archer", -9f, -2f, 150f)
             .addSpawn("hollow_archer", 10f, -10f, 210f)
             .addSpawn("feral_hound", -2f, -14f, 20f)
             .addSpawn("feral_hound", 4f, -18f, 350f)
             .addSpawn("plague_husk", -7f, -26f, 40f)
             .addSpawn("shieldbearer", 3f, -32f, 10f)
             .addSpawn("creeping_assassin", -12f, 30f, 160f)
             .addSpawn("grave_ghoul", 13f, 20f, 230f)
             .addSpawn("crypt_bat", -6f, 36f, 190f)
             .addSpawn("depth_maggot", 9f, 0f, 260f);

        // The town is the hub: north back to the asylum, south to the wall, west
        // down into the temple. Each trigger sits just inside its gap in the wall.
        level.portal(new Portal(ASYLUM, 0f, 45.5f, 4.4f, 0f, -24f, 0f,
                        "إلى ساحة المصح", "To the Asylum", false))
             .portal(new Portal(WALL, 0f, -45.5f, 4.4f, 0f, -41f, 0f,
                        "إلى السور المكسور", "To the Broken Wall", false))
             .portal(new Portal(TEMPLE, -33.5f, 0f, 4.4f, -9f, -40f, 0f,
                        "إلى معبد الأعماق", "To the Deep Temple", true));

        mood(level, 0.46f, 0.44f, 0.40f, 0.34f, 0.33f, 0.34f, 16f, 70f);
        addBonfireProps(level, textures);
        return level;
    }

    // ======================================================================
    // Area 3: the Broken Wall - vertical, ruined, dangerous
    // ======================================================================

    public static Level brokenWall(TextureFactory textures) {
        LevelBuilder b = new LevelBuilder(textures);

        b.box("stone_dark", 0f, -0.5f, 0f, 64f, 1f, 100f, true);

        // The wall itself, running east-west, collapsed in the middle.
        b.box("brick", -22f, 6f, 8f, 20f, 12f, 6f, true);
        b.box("brick", 22f, 6f, 8f, 20f, 12f, 6f, true);
        // The breach: a slope of rubble the player climbs.
        b.ramp("stone_dark", 0f, 0f, 2f, 16f, 6f, 10f, 0f, true);
        b.ramp("stone_dark", 0f, 0f, 14f, 16f, 6f, 10f, 180f, true);
        b.box("stone_dark", 0f, 3f, 8f, 16f, 6f, 3f, true);

        // A rampart walk on top, reached by stairs at both ends.
        b.box("stone", -22f, 12.3f, 8f, 20f, 0.6f, 6f, true);
        b.box("stone", 22f, 12.3f, 8f, 20f, 0.6f, 6f, true);
        for (int i = 0; i < 12; i++) {
            float h = 1f * (i + 1);
            b.box("stone", -30f, h * 0.5f, 16f + i * 1.1f, 4f, h, 1.1f, true);
        }
        // Battlements, so falling off the walk is a real risk.
        for (int i = 0; i < 14; i++) {
            float x = -31f + i * 4.6f;
            if (Math.abs(x) < 8f) continue;
            b.box("brick", x, 13.4f, 5.6f, 1.6f, 1.6f, 1.2f, true);
        }

        // Towers at the ends. The east one is a shell around a chamber, opening
        // west onto the rampart - and that opening is bricked up.
        b.column("brick", -32f, 0f, 8f, 4.2f, 17f, 10, true);
        b.box("stone_dark", 32f, -0.5f, 8f, 10f, 1f, 10f, true);
        b.box("brick", 32f, 8.5f, 12.4f, 10f, 17f, 1.4f, true);
        b.box("brick", 32f, 8.5f, 3.6f, 10f, 17f, 1.4f, true);
        b.box("brick", 36.5f, 8.5f, 8f, 1.4f, 17f, 10f, true);
        b.box("brick", 27.5f, 8.5f, 4.6f, 1.4f, 17f, 3.2f, true);
        b.box("brick", 27.5f, 8.5f, 11.4f, 1.4f, 17f, 3.2f, true);
        // Brick above the false panel, so the gap is only where the panel is.
        b.box("brick", 27.5f, 11.5f, 8f, 1.4f, 11f, 4f, true);
        b.box("stone_dark", 32f, 6.2f, 8f, 11f, 0.8f, 11f, false);

        // South approach: a ruined market with cover.
        for (int i = 0; i < 5; i++) {
            float z = -12f - i * 8f;
            b.box("stone", -12f + (i % 2) * 20f, 1.4f, z, 6f, 2.8f, 5f, true);
        }
        rubble(b, -4f, -20f, 5);
        rubble(b, 6f, -34f, 4);

        // North side: the arena approach.
        b.box("cobble", 0f, -0.5f, 40f, 40f, 1f, 40f, true);
        arenaWall(b, 0f, 44f, 15f, 6f);
        b.box("brick", -8f, 3f, 26f, 1.4f, 6f, 16f, true);
        b.box("brick", 8f, 3f, 26f, 1.4f, 6f, 16f, true);

        b.blocker(0f, 6f, 62f, 60f, 14f, 1.5f);
        b.blocker(0f, 6f, -52f, 68f, 14f, 1.5f);
        // Past the east tower, not through it.
        b.blocker(38f, 6f, 0f, 1.5f, 14f, 110f);
        b.blocker(-33f, 6f, 0f, 1.5f, 14f, 110f);

        Level level = finish(b, WALL, "السور المكسور", "The Broken Wall", textures);
        // The player arrives from the town at the south end and works north, over
        // the breach, to the arena - so this is the south end, not the arena side.
        level.spawn.set(0f, 0.2f, -41f);
        level.spawnFacing = 0f;
        level.bonfire(0f, -36f);
        level.bonfire(0f, 22f);

        level.addSpawn("hollow_archer", -22f, 13f, 180f)
             .addSpawn("hollow_archer", 22f, 13f, 180f)
             .addSpawn("bone_knight", 0f, 8f, 180f)
             .addSpawn("bone_knight", -6f, -4f, 90f)
             .addSpawn("fallen_knight", 5f, -14f, 160f)
             .addSpawn("shieldbearer", -8f, -22f, 30f)
             .addSpawn("pale_shade", 10f, -28f, 200f)
             .addSpawn("crag_spider", -14f, -34f, 60f)
             .addSpawn("stone_sentinel", 0f, -36f, 0f)
             .addSpawn("flame_zealot", -5f, 18f, 170f)
             .addSpawn("blind_executioner", 5f, 26f, 190f)
             .addSpawn("young_drake", -11f, 30f, 150f);

        BossArena arena = new BossArena("wall_boss", "bone_king",
                0f, 44f, 14.5f, 0f, 29f, 0f, 7f, 0f, 50f);
        arena.buildVisual(textures);
        level.arenas.add(arena);

        level.portal(new Portal(TOWN, 0f, -46f, 3.4f, 0f, -38f, 0f,
                "إلى بلدة الرماد", "To Ash Town", false));

        // Blades hung in the breach, on different clocks so the two never open
        // at once. The breach is the only way north, so this is a toll.
        level.trap(Trap.blade(-3.4f, 5f, 0f, 62f, 1.5f))
             .trap(Trap.blade(3.4f, 11f, 0f, 62f, 2.1f));
        // Spikes on the landing at the top of the east stair, where a player
        // running from the archers stops looking at the floor.
        level.trap(Trap.spikes(-30f, 27f, 48f, 2.4f));

        // Inside the east tower. The tower is solid from every side, which is
        // exactly why someone would try hitting it.
        level.secret(new IllusoryWall("wall_tower", 27.5f, 0f, 8f, 90f,
                3.8f, 6f, 1.4f, "brick"));
        level.treasure("ember_lump", 1, 32f, 8f);
        level.treasure("greenblood_leaf", 2, 33.5f, 9.5f);

        mood(level, 0.34f, 0.36f, 0.40f, 0.26f, 0.28f, 0.34f, 14f, 62f);
        addBonfireProps(level, textures);
        return level;
    }

    // ======================================================================
    // Area 4: the Deep Temple - dark, tight, and full of drops
    // ======================================================================

    public static Level deepTemple(TextureFactory textures) {
        LevelBuilder b = new LevelBuilder(textures);

        // A long hall with a pit down the middle and ledges either side. The ledges
        // run under the south wall so there is floor everywhere the player can walk.
        b.box("stone_dark", -10f, -0.5f, -2f, 12f, 1f, 94f, true);
        b.box("stone_dark", 10f, -0.5f, -2f, 12f, 1f, 94f, true);
        // The floor of the pit, four metres down: survivable, and a long way back.
        b.box("stone_dark", 0f, -4.5f, -2f, 10f, 1f, 94f, true);
        // Bridges across it.
        for (int i = 0; i < 4; i++) {
            b.box("stone", 0f, -0.5f, -30f + i * 22f, 10f, 1f, 4f, true);
        }

        // Rows of columns, close together, so the camera has to work.
        for (int i = 0; i < 9; i++) {
            float z = -40f + i * 9f;
            b.column("stone_dark", -13f, 0f, z, 0.85f, 9f, 8, true);
            b.column("stone_dark", 13f, 0f, z, 0.85f, 9f, 8, true);
            b.box("stone", -13f, 9.3f, z, 2.4f, 0.7f, 2.4f, false);
            b.box("stone", 13f, 9.3f, z, 2.4f, 0.7f, 2.4f, false);
        }

        // Outer walls and a vaulted ceiling, so it reads as indoors. They stop at
        // z=29, where the hall opens into the sanctum.
        // The west run is broken at z=-14, where the false panel sits.
        b.box("brick", -17f, 5f, -31.5f, 2f, 10f, 31f, true);
        b.box("brick", -17f, 5f, 6.5f, 2f, 10f, 45f, true);
        b.box("brick", -17f, 7.5f, -14f, 2f, 5f, 4f, true);
        b.box("brick", 17f, 5f, -9f, 2f, 10f, 76f, true);
        b.box("brick", 0f, 5f, -47f, 36f, 10f, 2f, true);
        b.box("stone_dark", 0f, 10.4f, -9f, 36f, 1.2f, 78f, false);

        // The sanctum: a chamber wide enough to fight a boss in, floored across
        // the pit so the fight is on solid ground.
        b.box("stone", 0f, -0.5f, 46f, 40f, 1f, 34f, true);
        b.box("brick", -21f, 6f, 46f, 2f, 12f, 34f, true);
        b.box("brick", 21f, 6f, 46f, 2f, 12f, 34f, true);
        b.box("brick", 0f, 6f, 64f, 44f, 12f, 2f, true);
        b.box("stone_dark", 0f, 12.4f, 46f, 44f, 1.2f, 36f, false);
        arenaWall(b, 0f, 46f, 13f, 5f);

        b.blocker(0f, 6f, -50f, 40f, 16f, 1.5f);

        // The vault behind the west wall. Sealed on every side but the panel.
        b.box("stone_dark", -22f, -0.5f, -14f, 12f, 1f, 9f, true);
        b.box("brick", -28.5f, 3f, -14f, 1.2f, 8f, 10f, true);
        b.box("brick", -22f, 3f, -18.9f, 13f, 8f, 1.2f, true);
        b.box("brick", -22f, 3f, -9.1f, 13f, 8f, 1.2f, true);
        b.box("stone_dark", -22f, 6.4f, -14f, 14f, 0.8f, 11f, false);

        rubble(b, -8f, -22f, 3);
        rubble(b, 9f, 6f, 4);

        Level level = finish(b, TEMPLE, "معبد الأعماق", "Deep Temple", textures);
        // The stair from the town comes out on the west ledge at the south end.
        level.spawn.set(-9f, 0.2f, -40f);
        level.spawnFacing = 0f;
        level.bonfire(-9f, -36f);

        level.addSpawn("depth_maggot", -9f, -30f, 0f)
             .addSpawn("depth_maggot", 9f, -18f, 340f)
             .addSpawn("abyss_crawler", 0f, -8f, 0f)
             .addSpawn("abyss_crawler", -9f, 4f, 20f)
             .addSpawn("crypt_bat", 9f, -4f, 200f)
             .addSpawn("crypt_bat", -9f, 14f, 160f)
             .addSpawn("pale_shade", 9f, 18f, 190f)
             .addSpawn("hollow_sorcerer", -9f, 26f, 180f)
             .addSpawn("hollow_sorcerer", 9f, 30f, 180f)
             .addSpawn("flame_zealot", 0f, 14f, 180f)
             .addSpawn("stone_sentinel", -9f, -12f, 30f)
             .addSpawn("plague_husk", 9f, -34f, 350f);

        BossArena arena = new BossArena("temple_boss", "abyss_horror",
                0f, 46f, 12.5f, 0f, 33f, 0f, 6f, 0f, 52f);
        arena.buildVisual(textures);
        level.arenas.add(arena);

        level.portal(new Portal(TOWN, -9f, -44.5f, 3.4f, -28f, 0f, 90f,
                "إلى بلدة الرماد", "To Ash Town", true));

        // Spikes in the middle of two of the four bridges. Crossing a bridge in
        // the dark is already a decision; this makes it a timed one.
        level.trap(Trap.spikes(0f, -8f, 54f, 2.2f))
             .trap(Trap.spikes(0f, 14f, 54f, 3.1f));
        // A dart lane down the west colonnade, fired from the far end.
        level.trap(Trap.dart(-9f, 34f, 180f, 52f));

        // Behind the west wall at the darkest point of the hall.
        level.secret(new IllusoryWall("temple_west", -17f, 0f, -14f, 90f,
                4.0f, 5f, 2.0f, "brick"));
        level.treasure("ember_core", 1, -21.5f, -14f);
        level.treasure("soul_of_a_beast", 1, -22.5f, -12f);
        level.treasure("resin_of_embers", 2, -22.5f, -16f);

        // Almost no light. The temple is meant to be read by torchlight.
        mood(level, 0.14f, 0.15f, 0.18f, 0.16f, 0.16f, 0.22f, 8f, 34f);
        addBonfireProps(level, textures);
        return level;
    }

    // ======================================================================
    // Shared construction
    // ======================================================================

    private static Level finish(LevelBuilder b, String id, String nameAr, String nameEn,
                                TextureFactory textures) {
        Level level = new Level(id, b.build(), b.getCollision());
        level.nameAr = nameAr;
        level.nameEn = nameEn;
        return level;
    }

    private static void mood(Level level, float fogR, float fogG, float fogB,
                             float ambR, float ambG, float ambB,
                             float near, float far) {
        level.fogColor.set(fogR, fogG, fogB, 1f);
        level.ambient.set(ambR, ambG, ambB, 1f);
        level.lightColor.set(0.86f, 0.80f, 0.66f, 1f);
        level.lightDir.set(-0.40f, -0.78f, -0.48f).nor();
        level.fogNear = near;
        level.fogFar = far;
    }

    /** Places a bonfire prop at every bonfire the area declared. */
    private static void addBonfireProps(Level level, TextureFactory textures) {
        if (level.bonfires.size == 0) return;
        Model model = bonfireModel(textures);
        level.own(model);
        for (com.badlogic.gdx.math.Vector3 fire : level.bonfires) {
            ModelInstance instance = new ModelInstance(model);
            instance.transform.setToTranslation(fire.x, fire.y, fire.z);
            level.props.add(instance);
        }
    }

    /** A simple house: walls, a doorway-less shell, and a pitched roof. */
    private static void building(LevelBuilder b, float x, float z,
                                 float depth, float width, float height) {
        b.box("brick", x, height * 0.5f, z, depth, height, width, true);
        b.box("wood", x, height + 0.35f, z, depth * 1.12f, 0.7f, width * 1.12f, false);
        b.box("stone_dark", x, height + 0.95f, z, depth * 0.7f, 0.6f, width * 0.7f, false);
    }

    /** A scatter of broken masonry, for cover and to break up flat ground. */
    private static void rubble(LevelBuilder b, float x, float z, int count) {
        for (int i = 0; i < count; i++) {
            float ox = MathUtils.cosDeg(i * 73f) * (0.8f + i * 0.45f);
            float oz = MathUtils.sinDeg(i * 73f) * (0.8f + i * 0.45f);
            float size = 0.7f + (i % 3) * 0.35f;
            b.box(i % 2 == 0 ? "stone_dark" : "stone",
                    x + ox, size * 0.5f, z + oz, size * 1.4f, size, size * 1.2f, true);
        }
    }

    /** A ring of wall around an arena, open only where the fog gate stands. */
    private static void arenaWall(LevelBuilder b, float cx, float cz,
                                  float radius, float height) {
        int segments = 20;
        for (int i = 0; i < segments; i++) {
            float a = i * 360f / segments;
            // Leave the south side open; that is where the fog gate stands.
            if (Math.abs(((a - 270f) % 360f + 540f) % 360f - 180f) < 18f) continue;
            float x = cx + MathUtils.cosDeg(a) * radius;
            float z = cz + MathUtils.sinDeg(a) * radius;
            float segWidth = 2f * MathUtils.PI * radius / segments * 1.25f;
            b.box("brick", x, height * 0.5f, z, segWidth, height, 2.2f, true);
            b.box("stone_dark", x, height + 0.25f, z, segWidth * 1.1f, 0.5f, 2.6f, false);
        }
    }

    /**
     * A run of wall along one axis with gaps knocked out of it.
     *
     * @param alongX true to run along X at {@code fixed} on Z, false for the reverse
     * @param gaps   pairs of {start, end} coordinates to leave open
     */
    private static void wallRun(LevelBuilder b, float from, float to, float fixed, boolean alongX,
                                float height, float thickness, float[][] gaps) {
        float cursor = from;
        for (float[] gap : gaps) {
            if (gap[0] > cursor) segment(b, cursor, gap[0], fixed, alongX, height, thickness);
            cursor = Math.max(cursor, gap[1]);
        }
        if (cursor < to) segment(b, cursor, to, fixed, alongX, height, thickness);
    }

    private static void segment(LevelBuilder b, float a, float c, float fixed, boolean alongX,
                                float height, float thickness) {
        float mid = (a + c) * 0.5f;
        float len = c - a;
        if (len <= 0.01f) return;
        if (alongX) {
            b.box("brick", mid, height * 0.5f, fixed, len, height, thickness, true);
            b.box("stone_dark", mid, height + 0.22f, fixed, len, 0.44f, thickness * 1.25f, false);
        } else {
            b.box("brick", fixed, height * 0.5f, mid, thickness, height, len, true);
            b.box("stone_dark", fixed, height + 0.22f, mid, thickness * 1.25f, 0.44f, len, false);
        }
    }

    /** A bonfire: a ring of stones, a coiled sword, and glowing embers. */
    public static Model bonfireModel(TextureFactory textures) {
        long attrs = Usage.Position | Usage.Normal | Usage.TextureCoordinates;

        Material stone = new Material(
                TextureAttribute.createDiffuse(textures.get("stone_dark")),
                ColorAttribute.createDiffuse(Color.WHITE));
        Material steel = new Material(
                TextureAttribute.createDiffuse(textures.get("steel")),
                ColorAttribute.createDiffuse(Color.WHITE));
        // Emissive tells the shader to skip lighting, so the coals stay bright
        // in a level that is otherwise lit by one dim directional light.
        Material embers = new Material(
                TextureAttribute.createDiffuse(textures.get("ember")),
                ColorAttribute.createDiffuse(Color.WHITE),
                ColorAttribute.createEmissive(1f, 1f, 1f, 1f));

        ModelBuilder mb = new ModelBuilder();
        mb.begin();

        MeshPartBuilder p = mb.part("ring", GL20.GL_TRIANGLES, attrs, stone);
        for (int i = 0; i < 9; i++) {
            float a = i * (360f / 9f);
            float x = MathUtils.cosDeg(a) * 1.15f;
            float z = MathUtils.sinDeg(a) * 1.15f;
            MeshUtil.taper(p, x, z, 0f, 0.34f + (i % 3) * 0.06f,
                    0.42f, 0.42f, 0.30f, 0.30f, 2f);
        }

        p = mb.part("coals", GL20.GL_TRIANGLES, attrs, embers);
        MeshUtil.prism(p, 0f, 0.02f, 0f, 0.95f, 0.16f, 10, 2f);

        p = mb.part("sword", GL20.GL_TRIANGLES, attrs, steel);
        MeshUtil.taper(p, 0f, 0f, 0.10f, 0.34f, 0.06f, 0.06f, 0.05f, 0.05f, 4f);
        MeshUtil.box(p, 0f, 0.36f, 0f, 0.34f, 0.05f, 0.08f, 4f);
        MeshUtil.blade(p, 0f, 0.38f, 0f, 1.15f, 0.14f, 0.045f, 0.18f, 4f);

        return mb.end();
    }

    /** Every area, built once, for validation. Callers must dispose them. */
    public static Array<Level> buildAll(TextureFactory textures) {
        Array<Level> levels = new Array<>();
        for (String id : ALL) levels.add(build(id, textures));
        return levels;
    }
}
