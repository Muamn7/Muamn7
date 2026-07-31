package com.muamn.ashen.entity;

import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Array;

import com.muamn.ashen.Config;
import com.muamn.ashen.combat.AttackDef;
import com.muamn.ashen.combat.AttackRunner;
import com.muamn.ashen.combat.CombatMath;
import com.muamn.ashen.combat.Combatant;
import com.muamn.ashen.combat.HitInfo;
import com.muamn.ashen.combat.WeaponDef;
import com.muamn.ashen.world.CharacterBody;
import com.muamn.ashen.world.CollisionMesh;

/**
 * A hostile creature, driven by a state machine rather than any planning.
 *
 * The AI is built around spacing and patience because that is what makes a Souls
 * enemy readable: it closes to its weapon's range, waits out a beat, commits to
 * an attack you can see coming, then backs off. Everything a player learns about
 * an enemy is learned from those timings, so they are data, not code.
 */
public class Enemy implements Combatant {

    public enum State {
        IDLE, PATROL, ALERT, APPROACH, CIRCLE, ATTACK, RECOVER,
        STAGGERED, RIPOSTEABLE, DEAD
    }

    public final CharacterBody body = new CharacterBody();
    public final Stats stats = new Stats();
    public final AttackRunner attacks = new AttackRunner();
    public final EnemyDef def;
    public final EnemyVisual visual;

    private WeaponDef weapon;
    private State state = State.IDLE;
    private float stateTime;
    private float facing;
    private float targetFacing;

    private Combatant target;
    private final Array<Combatant> myTargets = new Array<>();

    private final Vector3 home = new Vector3();
    private final Vector3 tmp = new Vector3();
    private final Vector3 toTarget = new Vector3();

    private float poiseDamage;
    private float poiseTimer;
    private float staggerAngle;
    private float staggerDuration = CombatMath.STAGGER_DURATION;

    /** Which way this enemy is currently strafing while spacing. */
    private float circleSign = 1f;
    private float circleTimer;
    /** Set once so the death drop is only awarded a single time. */
    private boolean soulsAwarded;

    /**
     * Which phase a boss is in. Phases do not change the moveset - they sharpen
     * it. A boss that suddenly gains new attacks at 50% is a different fight;
     * one that gets faster and commits more often is the same fight turned up,
     * which is what the player has spent the last two minutes learning.
     */
    private int phase;
    private float aggression = 1f;
    /** Set for one frame when the boss crosses a phase threshold. */
    public boolean phaseChanged;

    public Enemy(EnemyDef def, EnemyVisual visual, WeaponDef weapon) {
        this.def = def;
        this.visual = visual;
        this.weapon = weapon;
        body.radius = def.radius;
        body.height = def.height;
        stats.vigor = 1;
        stats.recalculate();
        stats.maxHealth = def.health;
        stats.health = def.health;
        stats.maxStamina = 200f;
        stats.stamina = 200f;
        stats.strength = def.strength;
        stats.dexterity = def.dexterity;
    }

    public void spawn(float x, float y, float z, float facingDeg) {
        body.teleport(x, y, z);
        home.set(x, y, z);
        facing = targetFacing = facingDeg;
        state = State.IDLE;
        stateTime = 0f;
        poiseDamage = 0f;
        soulsAwarded = false;
        phase = 0;
        aggression = phaseAggression(0);
        stats.health = stats.maxHealth;
        attacks.cancel();
    }

    public void setTarget(Combatant target) {
        this.target = target;
        myTargets.clear();
        if (target != null) myTargets.add(target);
    }

    public State getState() {
        return state;
    }

    /** Souls to award, once, when this enemy dies. */
    public long claimSouls() {
        if (state != State.DEAD || soulsAwarded) return 0;
        soulsAwarded = true;
        return def.souls;
    }

    // ---- Combatant --------------------------------------------------------

    @Override public int team() { return 1; }
    @Override public CharacterBody body() { return body; }
    @Override public Stats stats() { return stats; }
    @Override public float facing() { return facing; }
    @Override public boolean invulnerable() { return state == State.DEAD; }
    @Override public boolean blocking() { return false; }

    /** Enemies do not parry yet; that arrives with the knight archetypes. */
    @Override public boolean parrying() { return false; }

    @Override public boolean riposteable() { return state == State.RIPOSTEABLE; }

    @Override
    public void onAttackParried(Combatant parrier) {
        attacks.cancel();
        body.velocity.x = 0f;
        body.velocity.z = 0f;
        setState(State.RIPOSTEABLE);
    }

    @Override
    public void applyCritical(HitInfo hit) {
        if (state == State.DEAD) return;
        // Criticals skip absorption almost entirely and never get poised through.
        stats.damage(CombatMath.afterDefence(hit.damage, def.absorption * 0.25f));
        poiseDamage = 0f;
        attacks.cancel();
        if (stats.isDead()) {
            setState(State.DEAD);
        } else {
            staggerAngle = 0f;
            staggerDuration = CombatMath.STAGGER_DURATION * 1.5f;
            setState(State.STAGGERED);
        }
    }
    @Override public WeaponDef weapon() { return weapon; }
    @Override public boolean dead() { return state == State.DEAD; }

    @Override
    public Vector3 hitCenter(Vector3 out) {
        return out.set(body.position.x, body.position.y + body.height * 0.55f, body.position.z);
    }

    @Override
    public float hitRadius() {
        return body.radius + 0.16f;
    }

    // ---- simulation -------------------------------------------------------

    public void update(CollisionMesh mesh, float dt) {
        stateTime += dt;
        phaseChanged = false;
        updatePhase();
        if (poiseTimer > 0f) {
            poiseTimer -= dt;
            if (poiseTimer <= 0f) poiseDamage = 0f;
        }

        if (state == State.DEAD) {
            body.velocity.x = 0f;
            body.velocity.z = 0f;
            body.step(mesh, dt);
            visual.update(dt, EnemyVisual.Pose.DEAD, 0f, stateTime, null, 0f);
            visual.place(body.position, facing);
            return;
        }

        float distance = Float.MAX_VALUE;
        if (target != null && !target.dead()) {
            target.hitCenter(toTarget);
            toTarget.sub(body.position);
            toTarget.y = 0f;
            distance = toTarget.len();
        } else {
            target = null;
        }

        switch (state) {
            case IDLE:      updateIdle(distance); break;
            case ALERT:     updateAlert(dt); break;
            case APPROACH:  updateApproach(distance, dt); break;
            case CIRCLE:    updateCircle(distance, dt); break;
            case ATTACK:    updateAttack(dt); break;
            case RECOVER:   updateRecover(distance, dt); break;
            case STAGGERED:  updateStaggered(dt); break;
            case RIPOSTEABLE: updateRiposteable(dt); break;
            default:         break;
        }

        body.step(mesh, dt);

        boolean committed = state == State.ATTACK
                && attacks.phase() != AttackRunner.Phase.WINDUP;
        float turn = committed ? 0f : def.turnSpeed * dt;
        facing = approachAngle(facing, targetFacing, turn);

        updateVisual(dt);
    }

    /** Advances the boss phase when health drops past the next threshold. */
    private void updatePhase() {
        if (def.phaseThresholds.length == 0 || state == State.DEAD) return;
        float fraction = stats.healthFraction();
        while (phase < def.phaseThresholds.length
                && fraction <= def.phaseThresholds[phase]) {
            phase++;
            aggression = phaseAggression(phase);
            phaseChanged = true;
            // Crossing a threshold breaks the current swing and re-opens with
            // the new tempo, so the change is something the player can see.
            attacks.cancel();
            setState(State.RECOVER);
        }
    }

    private float phaseAggression(int index) {
        if (def.phaseAggression.length == 0) return 1f;
        return def.phaseAggression[Math.min(index, def.phaseAggression.length - 1)];
    }

    public int getPhase() {
        return phase;
    }

    public int phaseCount() {
        return def.phaseThresholds.length + 1;
    }

    private void updateIdle(float distance) {
        body.velocity.x *= 0.85f;
        body.velocity.z *= 0.85f;
        if (target != null && distance <= def.aggroRange) {
            setState(State.ALERT);
        }
    }

    /** A beat of hesitation before charging, so the player sees the aggro. */
    private void updateAlert(float dt) {
        body.velocity.x *= 0.8f;
        body.velocity.z *= 0.8f;
        faceTarget();
        if (stateTime >= def.alertDelay / aggression) setState(State.APPROACH);
    }

    private void updateApproach(float distance, float dt) {
        if (target == null) {
            setState(State.IDLE);
            return;
        }
        faceTarget();

        float attackRange = weapon.moveset.light(0).reach * 0.72f;
        if (distance <= attackRange) {
            chooseAttack(distance);
            return;
        }
        if (distance > def.leashRange) {
            setState(State.IDLE);
            return;
        }

        float speed = (distance > def.aggroRange * 0.5f ? def.runSpeed : def.walkSpeed)
                * aggression;
        moveToward(toTarget, speed, dt);
    }

    /** Strafing at the edge of range. This is the beat a player can act inside. */
    private void updateCircle(float distance, float dt) {
        if (target == null) {
            setState(State.IDLE);
            return;
        }
        faceTarget();
        circleTimer -= dt;
        if (circleTimer <= 0f) {
            circleSign = MathUtils.randomBoolean() ? 1f : -1f;
            circleTimer = MathUtils.random(0.7f, 1.6f);
        }

        float attackRange = weapon.moveset.light(0).reach * 0.72f;
        // Strafe sideways, drifting in or out to hold the preferred spacing.
        tmp.set(-toTarget.z, 0f, toTarget.x).nor().scl(circleSign);
        float drift = distance > attackRange * 1.25f ? 1f : (distance < attackRange * 0.8f ? -1f : 0f);
        tmp.mulAdd(toTarget.cpy().nor(), drift * 0.8f);
        moveToward(tmp, def.walkSpeed * aggression, dt);

        // A more aggressive phase spends less time spacing before committing.
        if (stateTime >= def.circleTime / aggression) chooseAttack(distance);
    }

    private void chooseAttack(float distance) {
        AttackDef attack;
        // Heavy attacks come out when the enemy has time to commit to them.
        boolean heavy = MathUtils.random() < def.heavyChance * aggression
                && distance > weapon.moveset.light(0).reach * 0.5f;
        attack = heavy ? weapon.moveset.heavy(0) : weapon.moveset.light(0);
        attacks.begin(attack, heavy, 0);
        setState(State.ATTACK);
    }

    private void updateAttack(float dt) {
        AttackDef attack = attacks.current();
        if (attack == null) {
            setState(State.RECOVER);
            return;
        }
        if (attacks.phase() == AttackRunner.Phase.WINDUP) faceTarget();

        float speed = attacks.stepSpeed() * def.stepScale;
        body.velocity.x = MathUtils.sinDeg(facing) * speed;
        body.velocity.z = MathUtils.cosDeg(facing) * speed;

        attacks.resolveHits(this, weapon, myTargets);

        if (attacks.update(dt)) setState(State.RECOVER);
    }

    /** The punish window. Longer recovery means a more beatable enemy. */
    private void updateRecover(float distance, float dt) {
        body.velocity.x *= 1f - Math.min(1f, 6f * dt);
        body.velocity.z *= 1f - Math.min(1f, 6f * dt);
        faceTarget();
        if (stateTime >= def.recoverTime / aggression) {
            setState(target == null ? State.IDLE : State.CIRCLE);
            circleTimer = 0f;
        }
    }

    /**
     * Held open after a parry. If nobody takes the opening it recovers, which
     * keeps a missed riposte from being punished twice.
     */
    private void updateRiposteable(float dt) {
        body.velocity.x *= 1f - Math.min(1f, 10f * dt);
        body.velocity.z *= 1f - Math.min(1f, 10f * dt);
        if (stateTime >= com.muamn.ashen.Config.RIPOSTEABLE_DURATION) setState(State.RECOVER);
    }

    private void updateStaggered(float dt) {
        body.velocity.x *= 1f - Math.min(1f, 8f * dt);
        body.velocity.z *= 1f - Math.min(1f, 8f * dt);
        if (stateTime >= staggerDuration) setState(State.RECOVER);
    }

    private void moveToward(Vector3 direction, float speed, float dt) {
        tmp.set(direction);
        tmp.y = 0f;
        if (tmp.len2() < 1e-6f) return;
        tmp.nor().scl(speed);
        body.velocity.x = MathUtils.lerp(body.velocity.x, tmp.x, Math.min(1f, 12f * dt));
        body.velocity.z = MathUtils.lerp(body.velocity.z, tmp.z, Math.min(1f, 12f * dt));
    }

    private void faceTarget() {
        if (target == null) return;
        targetFacing = MathUtils.atan2(toTarget.x, toTarget.z) * MathUtils.radiansToDegrees;
    }

    @Override
    public void applyHit(HitInfo hit) {
        if (state == State.DEAD) return;

        if (hit.wasParried) return;   // we caught it on a parry; nothing lands

        float damage = CombatMath.afterDefence(hit.damage, def.absorption);
        if (hit.attacker != null
                && CombatMath.isBackstab(facing, hit.attacker.facing(), hit.direction)) {
            damage *= (hit.attacker.weapon().critical / 100f)
                    * com.muamn.ashen.Config.BACKSTAB_MULTIPLIER;
            hit.critical = true;
        }
        stats.damage(damage);

        poiseDamage += hit.poise;
        poiseTimer = CombatMath.POISE_RECOVERY;
        if (poiseDamage >= def.poise || hit.critical) {
            poiseDamage = 0f;
            staggerAngle = CombatMath.angleDifference(facing,
                    MathUtils.atan2(hit.direction.x, hit.direction.z) * MathUtils.radiansToDegrees);
            staggerDuration = CombatMath.STAGGER_DURATION;
            hit.staggered = true;
            attacks.cancel();
            setState(State.STAGGERED);
        }

        body.velocity.x += hit.direction.x * 2.2f;
        body.velocity.z += hit.direction.z * 2.2f;

        // Getting hit is how a passive enemy notices you.
        if (target == null && hit.attacker != null) setTarget(hit.attacker);
        if (state == State.IDLE) setState(State.ALERT);

        if (stats.isDead()) {
            attacks.cancel();
            setState(State.DEAD);
        }
    }

    private void updateVisual(float dt) {
        float speed = Vector3.len(body.velocity.x, 0f, body.velocity.z);
        EnemyVisual.Pose pose;
        switch (state) {
            case ATTACK:    pose = EnemyVisual.Pose.ATTACK; break;
            case STAGGERED:
            case RIPOSTEABLE: pose = EnemyVisual.Pose.STAGGER; break;
            case DEAD:      pose = EnemyVisual.Pose.DEAD; break;
            case ALERT:
            case RECOVER:   pose = EnemyVisual.Pose.IDLE; break;
            default:        pose = speed > 0.15f ? EnemyVisual.Pose.MOVE : EnemyVisual.Pose.IDLE;
        }
        visual.update(dt, pose, speed, stateTime, attacks.current(), attacks.normalisedTime());
        visual.place(body.position, facing);
    }

    private void setState(State next) {
        state = next;
        stateTime = 0f;
    }

    private static float approachAngle(float current, float target, float maxDelta) {
        if (maxDelta <= 0f) return current;
        float diff = ((target - current) % 360f + 540f) % 360f - 180f;
        if (Math.abs(diff) <= maxDelta) return target;
        return current + Math.signum(diff) * maxDelta;
    }
}
