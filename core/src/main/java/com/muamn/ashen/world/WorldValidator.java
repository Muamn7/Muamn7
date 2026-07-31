package com.muamn.ashen.world;

import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.ObjectMap;
import com.badlogic.gdx.utils.ObjectSet;

import com.muamn.ashen.combat.WeaponLibrary;
import com.muamn.ashen.entity.EnemyLibrary;

/**
 * Builds every area and checks the world holds together.
 *
 * This cannot be a unit test: building an area needs textures, which needs a GL
 * context. So it runs as part of the CI smoke run instead, with
 * {@code -Dashen.validateWorld=true}, and fails the build if anything is wrong.
 *
 * The checks are the ones that break a game silently rather than loudly - a
 * portal to an area that does not exist, an area with no bonfire to respawn at,
 * a boss arena naming a boss that was renamed, or a one-way door nobody can get
 * back through.
 */
public final class WorldValidator {

    /** Scratch, so the checks below allocate nothing per placement. */
    private static final Vector3 TEMP = new Vector3();

    private WorldValidator() {}

    /** @return a list of problems; empty means the world is sound. */
    public static Array<String> validate(TextureFactory textures,
                                         EnemyLibrary bestiary,
                                         WeaponLibrary weapons) {
        Array<String> problems = new Array<>();
        ObjectMap<String, Level> built = new ObjectMap<>();

        try {
            for (String id : Areas.ALL) {
                Level level = Areas.build(id, textures);
                built.put(id, level);

                if (!level.id.equals(id)) {
                    problems.add(id + ": built level reports id '" + level.id + "'");
                }
                if (level.nameEn.isEmpty() || level.nameAr.isEmpty()) {
                    problems.add(id + ": missing a display name");
                }
                if (level.bonfires.size == 0) {
                    problems.add(id + ": has no bonfire, so dying there is unrecoverable");
                }
                if (level.collision.ownTriangleCount() < 100) {
                    problems.add(id + ": has almost no collision ("
                            + level.collision.ownTriangleCount() + " triangles)");
                }
                if (level.spawns.size == 0) {
                    problems.add(id + ": is empty of enemies");
                }

                for (Level.Spawn spawn : level.spawns) {
                    if (!bestiary.has(spawn.enemyId)) {
                        problems.add(id + ": spawns unknown enemy '" + spawn.enemyId + "'");
                    }
                }
                for (BossArena arena : level.arenas) {
                    if (!bestiary.has(arena.bossId)) {
                        problems.add(id + ": arena '" + arena.id
                                + "' names unknown boss '" + arena.bossId + "'");
                    }
                    if (arena.radius < 6f) {
                        problems.add(id + ": arena '" + arena.id + "' is too small to fight in");
                    }
                    // The gate stands in the opening of the arena wall, so it has to
                    // be on the edge - a gate placed short of it lets the player walk
                    // into the arena without triggering the fight.
                    float gateDistance = distanceXZ(arena.gate, arena.center);
                    if (Math.abs(gateDistance - arena.radius) > 2f) {
                        problems.add(id + ": arena '" + arena.id + "' gate is "
                                + Math.round(gateDistance) + "m out on a "
                                + Math.round(arena.radius) + "m arena, so it is not on the edge");
                    }
                    if (!arena.contains(arena.bossSpawn)) {
                        problems.add(id + ": arena '" + arena.id
                                + "' spawns its boss outside the arena");
                    }
                    // Nothing that belongs to the area at large may sit inside the
                    // arena: the barrier seals it during the fight, so anything in
                    // there is either trapped with the boss or fought for free.
                    if (arena.contains(level.spawn)) {
                        problems.add(id + ": the player start is inside arena '" + arena.id + "'");
                    }
                    for (Vector3 fire : level.bonfires) {
                        if (arena.contains(fire)) {
                            problems.add(id + ": a bonfire is inside arena '" + arena.id + "'");
                        }
                    }
                    for (Level.Spawn spawn : level.spawns) {
                        if (arena.contains(TEMP.set(spawn.x, 0f, spawn.z))) {
                            problems.add(id + ": '" + spawn.enemyId
                                    + "' is inside arena '" + arena.id + "'");
                        }
                    }
                    for (Portal portal : level.portals) {
                        if (arena.contains(portal.position)) {
                            problems.add(id + ": the exit to " + portal.targetArea
                                    + " is inside arena '" + arena.id + "'");
                        }
                    }
                }
            }

            // --- the graph ---
            ObjectSet<String> reachable = new ObjectSet<>();
            walk(Areas.ASYLUM, built, reachable);

            for (String id : Areas.ALL) {
                Level level = built.get(id);
                if (level == null) continue;
                for (Portal portal : level.portals) {
                    if (!Areas.exists(portal.targetArea)) {
                        problems.add(id + ": portal leads to unknown area '"
                                + portal.targetArea + "'");
                        continue;
                    }
                    Level target = built.get(portal.targetArea);
                    if (target == null) continue;
                    // Landing inside a boss arena would start a fight on arrival.
                    for (BossArena arena : target.arenas) {
                        if (arena.contains(portal.targetPosition)) {
                            problems.add(id + ": portal to " + portal.targetArea
                                    + " lands inside a boss arena");
                        }
                    }
                    // Landing inside one of the target's own exits sends the player
                    // straight back, which reads as the door being broken.
                    for (Portal back : target.portals) {
                        if (back.contains(portal.targetPosition)) {
                            problems.add(id + ": portal to " + portal.targetArea
                                    + " lands inside that area's exit to " + back.targetArea);
                        }
                    }
                }
                if (!reachable.contains(id)) {
                    problems.add(id + ": cannot be reached from the starting area");
                }
            }

            // Every area except the start must have a way back out.
            for (String id : Areas.ALL) {
                Level level = built.get(id);
                if (level != null && level.portals.size == 0) {
                    problems.add(id + ": is a dead end with no exits");
                }
            }
        } finally {
            for (Level level : built.values()) level.dispose();
        }
        return problems;
    }

    private static void walk(String id, ObjectMap<String, Level> built, ObjectSet<String> seen) {
        if (!seen.add(id)) return;
        Level level = built.get(id);
        if (level == null) return;
        for (Portal portal : level.portals) walk(portal.targetArea, built, seen);
    }

    private static float distanceXZ(Vector3 a, Vector3 b) {
        float dx = a.x - b.x, dz = a.z - b.z;
        return (float) Math.sqrt(dx * dx + dz * dz);
    }
}
