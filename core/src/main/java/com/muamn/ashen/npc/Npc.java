package com.muamn.ashen.npc;

import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Disposable;

import com.muamn.ashen.entity.EnemyVisual;

/**
 * A standing character in the world.
 *
 * Deliberately not a {@code Combatant}. An NPC that could be hit would need a
 * hurt state, a death state, a soul reward and a decision about whether the
 * world remembers you killed them - all of which is a system, not a character.
 * These people stand, talk, and in one case sell things.
 */
public class Npc implements Disposable {

    /** How close the player must be to start talking. */
    public static final float TALK_RANGE = 2.4f;

    public final NpcDef def;
    public final EnemyVisual visual;
    public final Vector3 position = new Vector3();

    /**
     * Which line comes next. It stops on the last one rather than wrapping,
     * because a character who loops back to their opening line every time reads
     * as a machine, and one who repeats their final line reads as someone who
     * has said all they have to say.
     */
    private int line;
    private float time;

    public Npc(NpcDef def, EnemyVisual visual) {
        this.def = def;
        this.visual = visual;
        this.position.set(def.x, 0.2f, def.z);
        visual.place(position, def.facing);
    }

    public void update(float dt) {
        time += dt;
        visual.update(dt, EnemyVisual.Pose.IDLE, 0f, time, null, 0f);
        visual.place(position, def.facing);
    }

    public boolean inRange(Vector3 playerPosition) {
        float dx = playerPosition.x - position.x;
        float dz = playerPosition.z - position.z;
        return dx * dx + dz * dz <= TALK_RANGE * TALK_RANGE;
    }

    /** The line being spoken now, or null if this character has nothing to say. */
    public NpcDef.Line currentLine() {
        if (def.lines.size == 0) return null;
        return def.lines.get(Math.min(line, def.lines.size - 1));
    }

    /** @return true if there was another line to move to. */
    public boolean advance() {
        if (line >= def.lines.size - 1) return false;
        line++;
        return true;
    }

    /** True once the last line has been reached. */
    public boolean saidEverything() {
        return line >= def.lines.size - 1;
    }

    @Override
    public void dispose() {
        visual.dispose();
    }
}
