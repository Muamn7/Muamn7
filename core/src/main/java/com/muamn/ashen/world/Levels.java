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

/**
 * Hand-placed level layouts.
 *
 * Part 1 ships one area - the asylum courtyard - built to exercise everything the
 * engine has to do: flat ground, a ramp, discrete steps to climb, columns for the
 * camera to collide with, a drop to fall off, and a walled perimeter.
 * Parts 3 adds the rest of the world using the same primitives.
 */
public final class Levels {

    private Levels() {}

    public static Level asylumCourtyard(TextureFactory textures) {
        LevelBuilder b = new LevelBuilder(textures);

        // --- ground: a cobbled courtyard ringed by ash ---
        b.box("cobble", 0f, -0.5f, 0f, 24f, 1f, 24f, true);
        b.box("ash", 0f, -0.5f, 21f, 60f, 1f, 18f, true);
        // A causeway north from the terrace to the boss arena.
        b.box("stone_dark", 0f, -0.5f, 36f, 12f, 1f, 18f, true);
        b.box("cobble", 0f, -0.5f, 52f, 34f, 1f, 32f, true);
        b.box("ash", 0f, -0.5f, -21f, 60f, 1f, 18f, true);
        b.box("ash", 21f, -0.5f, 0f, 18f, 1f, 24f, true);
        b.box("ash", -21f, -0.5f, 0f, 18f, 1f, 24f, true);

        // --- north terrace, reached by a broad stair ---
        b.box("stone", 0f, 1f, 20f, 26f, 2f, 14f, true);
        b.ramp("stone", 0f, 0f, 10.5f, 8f, 2f, 5f, 0f, true);
        // A second way up, as discrete steps, so stepping logic gets exercised.
        for (int i = 0; i < 6; i++) {
            float h = 0.34f * (i + 1);
            b.box("stone_dark", -11f, h * 0.5f, 12.8f - i * 0.9f, 3.4f, h, 0.9f, true);
        }

        // --- perimeter wall, broken open in two places ---
        wallRun(b, -30f, 30f, 29.4f, true, 6f, 1.2f, new float[][]{{-6f, 6f}});
        wallRun(b, -30f, 30f, -29.4f, true, 6f, 1.2f, new float[][]{});
        wallRun(b, -30f, 30f, 29.4f, false, 6f, 1.2f, new float[][]{{6f, 15f}});
        wallRun(b, -30f, 30f, -29.4f, false, 6f, 1.2f, new float[][]{});

        // Walls along the causeway, so the approach reads as a corridor.
        b.box("brick", -6.6f, 2.4f, 36f, 1.2f, 4.8f, 18f, true);
        b.box("brick", 6.6f, 2.4f, 36f, 1.2f, 4.8f, 18f, true);

        // The arena: a walled circle with a single way in.
        arenaWall(b, 0f, 52f, 16f, 5.5f);
        b.column("stone_dark", -10f, 0f, 52f, 0.8f, 6.5f, 8, true);
        b.column("stone_dark", 10f, 0f, 52f, 0.8f, 6.5f, 8, true);
        b.column("stone_dark", 0f, 0f, 62f, 0.8f, 6.5f, 8, true);

        // Keep the player inside even where the wall is broken.
        b.blocker(0f, 4f, -30.6f, 62f, 10f, 1.5f);
        b.blocker(0f, 4f, 69f, 40f, 10f, 1.5f);
        b.blocker(30.6f, 4f, 0f, 1.5f, 10f, 62f);
        b.blocker(-30.6f, 4f, 0f, 1.5f, 10f, 62f);

        // --- columns around the courtyard ---
        float[][] columns = {{-9f, -9f}, {9f, -9f}, {-9f, 9f}, {9f, 9f}, {-9f, 0f}, {9f, 0f}};
        for (float[] c : columns) {
            b.column("stone_dark", c[0], 0f, c[1], 0.72f, 7.2f, 8, true);
            b.box("stone", c[0], 7.4f, c[1], 2f, 0.5f, 2f, false);   // capital
            b.box("stone", c[0], 0.18f, c[1], 2.1f, 0.36f, 2.1f, true); // base
        }

        // --- a ruined arch on the terrace ---
        b.column("stone_dark", -4.5f, 2f, 20f, 0.6f, 5f, 8, true);
        b.column("stone_dark", 4.5f, 2f, 20f, 0.6f, 5f, 8, true);
        b.box("stone", 0f, 7.4f, 20f, 11f, 0.8f, 1.6f, true);
        b.box("stone", 0f, 8.1f, 20f, 9f, 0.6f, 1.2f, false);

        // --- scattered debris to break up the floor ---
        b.box("wood", -6.2f, 0.45f, -4.4f, 1.1f, 0.9f, 1.1f, true);
        b.box("wood", -5.4f, 0.45f, -5.6f, 1.1f, 0.9f, 1.1f, true);
        b.box("wood", -5.9f, 1.35f, -4.9f, 1.0f, 0.9f, 1.0f, true);
        b.box("stone_dark", 7.4f, 0.3f, -7.2f, 2.4f, 0.6f, 1.8f, true);
        b.box("stone_dark", 6.1f, 0.22f, 5.8f, 1.6f, 0.44f, 3.2f, true);
        b.box("stone", -13.5f, 0.9f, -2f, 1.4f, 1.8f, 6f, true);

        Model model = b.build();
        Level level = new Level("asylum_courtyard", model, b.getCollision());

        level.spawn.set(5.5f, 0.2f, -9.5f);
        level.spawnFacing = -22f;

        // --- who lives here ---
        level.addSpawn("hollow_soldier", -8f, -16f, 60f)
             .addSpawn("hollow_soldier", 10f, 6f, 250f)
             .addSpawn("hollow_soldier", -13f, 14f, 150f)
             .addSpawn("hollow_archer", 12f, 21f, 200f)
             .addSpawn("feral_hound", 3f, -18f, 200f)
             .addSpawn("feral_hound", -3f, -20f, 190f)
             .addSpawn("grave_ghoul", 16f, -14f, 300f)
             .addSpawn("crag_spider", -18f, -6f, 90f)
             .addSpawn("crypt_bat", 7f, 34f, 180f)
             .addSpawn("bone_knight", 0f, 40f, 180f)
             .addSpawn("fallen_knight", -4f, 20f, 170f);

        // --- the boss behind the fog ---
        BossArena arena = new BossArena("asylum_boss", "ashen_knight",
                0f, 52f, 15.5f,
                0f, 44.5f, 0f, 7f,
                0f, 58f);
        arena.buildVisual(textures);
        level.arenas.add(arena);

        level.fogColor.set(0.40f, 0.42f, 0.41f, 1f);
        level.ambient.set(0.30f, 0.32f, 0.36f, 1f);
        level.lightColor.set(0.86f, 0.80f, 0.66f, 1f);
        level.lightDir.set(-0.40f, -0.78f, -0.48f).nor();
        level.fogNear = 12f;
        level.fogFar = 58f;

        // The bonfire is a prop so it can carry an emissive material of its own.
        Model bonfire = bonfireModel(textures);
        level.own(bonfire);
        ModelInstance fire = new ModelInstance(bonfire);
        fire.transform.setToTranslation(0f, 0f, -6f);
        level.props.add(fire);

        return level;
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
     * @param alongX  true to run along X at {@code fixed} on Z, false for the reverse
     * @param gaps    pairs of {start, end} coordinates to leave open
     */
    private static void wallRun(LevelBuilder b, float from, float to, float fixed, boolean alongX,
                                float height, float thickness, float[][] gaps) {
        float cursor = from;
        // Walk the run, emitting a segment before each gap.
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
        // Hilt buried in the coals, blade up: the series' checkpoint marker.
        MeshUtil.taper(p, 0f, 0f, 0.10f, 0.34f, 0.06f, 0.06f, 0.05f, 0.05f, 4f);
        MeshUtil.box(p, 0f, 0.36f, 0f, 0.34f, 0.05f, 0.08f, 4f);
        MeshUtil.blade(p, 0f, 0.38f, 0f, 1.15f, 0.14f, 0.045f, 0.18f, 4f);

        return mb.end();
    }
}
