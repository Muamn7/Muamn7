package com.muamn.ashen.world;

import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.Disposable;

/** One playable area: its geometry, its collision and its lighting mood. */
public class Level implements Disposable {

    public final String id;
    public final Model model;
    public final ModelInstance instance;
    public final CollisionMesh collision;

    public final Vector3 spawn = new Vector3();
    public float spawnFacing;

    public final Color fogColor = new Color(0.42f, 0.44f, 0.46f, 1f);
    public final Color ambient = new Color(0.30f, 0.31f, 0.38f, 1f);
    public final Color lightColor = new Color(0.85f, 0.80f, 0.70f, 1f);
    public final Vector3 lightDir = new Vector3(-0.45f, -0.82f, -0.35f).nor();
    public float fogNear = 14f;
    public float fogFar = 62f;

    /** An item lying somewhere on purpose, rather than dropped by something. */
    public static class Treasure {
        /** Stable identity, so a save can remember it was taken. */
        public final String id;
        public final String itemId;
        public final int count;
        public final float x, z;

        public Treasure(String id, String itemId, int count, float x, float z) {
            this.id = id;
            this.itemId = itemId;
            this.count = count;
            this.x = x;
            this.z = z;
        }
    }

    /** Where an enemy stands when the area is fresh or has been rested at. */
    public static class Spawn {
        public final String enemyId;
        public final float x, z, facing;

        public Spawn(String enemyId, float x, float z, float facing) {
            this.enemyId = enemyId;
            this.x = x;
            this.z = z;
            this.facing = facing;
        }
    }

    /** Enemy placements. Respawned wholesale when the player rests. */
    public final Array<Spawn> spawns = new Array<>();
    /** Boss encounters in this area. */
    public final Array<BossArena> arenas = new Array<>();
    /** Ways out of this area. */
    public final Array<Portal> portals = new Array<>();
    /** Bonfires in this area, in world coordinates. */
    public final Array<Vector3> bonfires = new Array<>();
    /** Hazards in this area. */
    public final Array<Trap> traps = new Array<>();
    /** Walls that are not walls. */
    public final Array<IllusoryWall> secrets = new Array<>();
    /** Loot placed by hand, usually behind one of those walls. */
    public final Array<Treasure> treasures = new Array<>();

    /**
     * Collision for the illusory walls.
     *
     * Kept as an overlay rather than mixed into the level's own triangles so a
     * wall opening costs one small rebuild instead of the whole spatial hash,
     * and so {@code ownTriangleCount} still measures the level itself.
     */
    private final CollisionMesh secretCollision = new CollisionMesh();

    /** Human-readable area name, shown when the player arrives. */
    public String nameAr = "";
    public String nameEn = "";

    /** Extra instances drawn with the level, e.g. props with their own transform. */
    public final Array<ModelInstance> props = new Array<>();
    /** Models this level owns and must dispose. */
    private final Array<Model> ownedModels = new Array<>();

    public Level(String id, Model model, CollisionMesh collision) {
        this.id = id;
        this.model = model;
        this.instance = new ModelInstance(model);
        this.collision = collision;
        this.collision.setOverlay(secretCollision);
        ownedModels.add(model);
    }

    /**
     * The mesh a boss barrier layers onto.
     *
     * The barrier goes on top of the secrets rather than on top of the level,
     * because the level's overlay slot is already the secrets mesh and only one
     * of the two would survive.
     */
    public CollisionMesh barrierHost() {
        return secretCollision;
    }

    public Level trap(Trap trap) {
        traps.add(trap);
        return this;
    }

    /** Adds an illusory wall and rebuilds the secret collision. */
    public Level secret(IllusoryWall wall) {
        secrets.add(wall);
        rebuildSecretCollision();
        return this;
    }

    public Level treasure(String itemId, int count, float x, float z) {
        treasures.add(new Treasure(id + "#" + treasures.size, itemId, count, x, z));
        return this;
    }

    /**
     * Rebuilds the collision for whichever walls are still standing.
     *
     * Cheap enough to do on every reveal: it is a handful of triangles, and the
     * alternative - removing triangles from a spatial hash in place - is a whole
     * mechanism to maintain for something that happens a dozen times a game.
     */
    public void rebuildSecretCollision() {
        CollisionMesh barrier = secretCollision.getOverlay();
        secretCollision.clear();
        secretCollision.setOverlay(barrier);
        for (IllusoryWall wall : secrets) wall.addCollision(secretCollision);
    }

    /** Registers a model whose lifetime is tied to this level. */
    public void own(Model m) {
        ownedModels.add(m);
    }

    /** Everything to draw for this level, level geometry first. */
    public Array<ModelInstance> renderables(Array<ModelInstance> out) {
        out.clear();
        out.add(instance);
        out.addAll(props);
        for (BossArena arena : arenas) {
            ModelInstance fog = arena.fogInstance();
            if (fog != null) out.add(fog);
        }
        for (Trap trap : traps) {
            if (trap.instance() != null) out.add(trap.instance());
        }
        for (IllusoryWall wall : secrets) {
            if (wall.instance() != null) out.add(wall.instance());
        }
        return out;
    }

    /** Adds a way out of this area. */
    public Level portal(Portal portal) {
        portals.add(portal);
        return this;
    }

    /** Adds a bonfire at ground level. */
    public Level bonfire(float x, float z) {
        bonfires.add(new Vector3(x, 0f, z));
        return this;
    }

    /** The bonfire nearest a point, or null if this area has none. */
    public Vector3 nearestBonfire(Vector3 to) {
        Vector3 best = null;
        float bestDistance = Float.MAX_VALUE;
        for (Vector3 fire : bonfires) {
            float d = fire.dst2(to);
            if (d < bestDistance) {
                bestDistance = d;
                best = fire;
            }
        }
        return best;
    }

    /**
     * Adds an enemy placement. Named {@code addSpawn} rather than {@code spawn}
     * so it never reads as a call on the {@link #spawn} player start point.
     */
    public Level addSpawn(String enemyId, float x, float z, float facing) {
        spawns.add(new Spawn(enemyId, x, z, facing));
        return this;
    }

    @Override
    public void dispose() {
        for (BossArena arena : arenas) arena.dispose();
        arenas.clear();
        for (Trap trap : traps) trap.dispose();
        traps.clear();
        for (IllusoryWall wall : secrets) wall.dispose();
        secrets.clear();
        treasures.clear();
        portals.clear();
        bonfires.clear();
        for (Model m : ownedModels) m.dispose();
        ownedModels.clear();
        props.clear();
        spawns.clear();
    }
}
