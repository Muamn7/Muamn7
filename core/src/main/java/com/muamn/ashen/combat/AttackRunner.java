package com.muamn.ashen.combat;

import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.ObjectSet;

/**
 * Runs one attack: its timing, its forward step, and its hitbox.
 *
 * The hitbox is a line segment from the attacker's chest out to the weapon's
 * reach, swept through the attack's arc as the swing progresses, tested against
 * each target's hurt capsule. That is not a physical simulation of the blade,
 * and deliberately so - a swept segment is predictable, cheap, and does not
 * punish the player for a millimetre of animation drift. Every attack registers
 * at most one hit per target.
 */
public class AttackRunner {

    public enum Phase { IDLE, WINDUP, ACTIVE, RECOVERY }

    private AttackDef attack;
    private float time;
    private boolean heavy;
    private int chainIndex;

    /** Targets already hit by the current swing. */
    private final ObjectSet<Combatant> hitThisSwing = new ObjectSet<>();

    private final Vector3 origin = new Vector3();
    private final Vector3 tip = new Vector3();
    private final Vector3 toTarget = new Vector3();
    private final Vector3 closest = new Vector3();
    private final HitInfo hit = new HitInfo();

    public void begin(AttackDef attack, boolean heavy, int chainIndex) {
        this.attack = attack;
        this.heavy = heavy;
        this.chainIndex = chainIndex;
        this.time = 0f;
        hitThisSwing.clear();
    }

    public void cancel() {
        attack = null;
        time = 0f;
        hitThisSwing.clear();
    }

    public boolean isRunning() {
        return attack != null;
    }

    public AttackDef current() {
        return attack;
    }

    public boolean isHeavy() {
        return heavy;
    }

    public int getChainIndex() {
        return chainIndex;
    }

    public float getTime() {
        return time;
    }

    public float normalisedTime() {
        return attack == null ? 0f : MathUtils.clamp(time / attack.duration(), 0f, 1f);
    }

    public Phase phase() {
        if (attack == null) return Phase.IDLE;
        if (time < attack.windup) return Phase.WINDUP;
        if (time < attack.activeEnd()) return Phase.ACTIVE;
        return Phase.RECOVERY;
    }

    /**
     * A follow-up may be buffered from partway through the active window. Souls
     * games let you queue the next swing before the current one finishes, which
     * is what makes chains feel responsive without making them spammable.
     */
    public boolean canChain() {
        return attack != null && time >= attack.windup + attack.active * 0.5f;
    }

    /** Advances the attack. Returns true when it has finished. */
    public boolean update(float dt) {
        if (attack == null) return true;
        time += dt;
        if (time >= attack.duration()) {
            attack = null;
            return true;
        }
        return false;
    }

    /** Forward speed contributed by the attack's step, in metres/second. */
    public float stepSpeed() {
        if (attack == null || attack.step <= 0f) return 0f;
        // The lunge happens across the windup and the active window, then stops.
        float end = attack.activeEnd();
        if (time > end) return 0f;
        float t = MathUtils.clamp(time / Math.max(end, 1e-4f), 0f, 1f);
        // Ease in then out, so the step has weight rather than a constant slide.
        float curve = MathUtils.sin(t * MathUtils.PI);
        return attack.step / Math.max(end, 1e-4f) * curve * 1.6f;
    }

    /**
     * Tests the live hitbox against {@code targets} and applies hits.
     *
     * @return the number of targets hit this step
     */
    public int resolveHits(Combatant attacker, WeaponDef weapon, Array<Combatant> targets) {
        if (attack == null || !attack.isActiveAt(time)) return 0;

        attacker.hitCenter(origin);
        float progress = attack.swingProgress(time);

        // Where along the arc the blade is right now.
        float sweep;
        switch (attack.motion) {
            case SWING_H:
                sweep = -attack.arc * 0.5f + attack.arc * progress;
                break;
            case SWING_V:
                sweep = MathUtils.lerp(-attack.arc * 0.18f, attack.arc * 0.18f, progress);
                break;
            default:
                sweep = 0f;
                break;
        }
        float angle = attacker.facing() + sweep;
        tip.set(origin).add(MathUtils.sinDeg(angle) * attack.reach, 0f,
                MathUtils.cosDeg(angle) * attack.reach);
        // A vertical chop dips toward the ground, so it catches crouching enemies.
        if (attack.motion == AttackDef.Motion.SWING_V) {
            tip.y -= attack.reach * 0.35f * progress;
        }

        int hits = 0;
        for (Combatant target : targets) {
            if (target == attacker || target.dead()) continue;
            if (target.team() == attacker.team()) continue;
            if (target.invulnerable()) continue;
            if (hitThisSwing.contains(target)) continue;

            target.hitCenter(toTarget);
            float distance = distancePointSegment(toTarget, origin, tip, closest);
            if (distance > target.hitRadius() + 0.20f) continue;

            hitThisSwing.add(target);
            float damage = weapon.damageAgainst(attacker.stats(), attack);
            hit.set(attacker, damage, attack.poise);
            hit.direction.set(toTarget).sub(origin);
            hit.direction.y = 0f;
            if (hit.direction.len2() < 1e-6f) {
                hit.direction.set(MathUtils.sinDeg(attacker.facing()), 0f,
                        MathUtils.cosDeg(attacker.facing()));
            }
            hit.direction.nor();
            hit.point.set(closest);
            target.applyHit(hit);
            hits++;
        }
        return hits;
    }

    /** Distance from {@code p} to segment ab, writing the closest point to {@code out}. */
    static float distancePointSegment(Vector3 p, Vector3 a, Vector3 b, Vector3 out) {
        float abx = b.x - a.x, aby = b.y - a.y, abz = b.z - a.z;
        float len2 = abx * abx + aby * aby + abz * abz;
        float t = len2 < 1e-8f ? 0f
                : MathUtils.clamp(((p.x - a.x) * abx + (p.y - a.y) * aby + (p.z - a.z) * abz) / len2,
                        0f, 1f);
        out.set(a.x + abx * t, a.y + aby * t, a.z + abz * t);
        return out.dst(p);
    }
}
