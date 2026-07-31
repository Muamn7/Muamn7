package com.muamn.ashen.entity;

import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector2;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Array;

import com.muamn.ashen.Config;
import com.muamn.ashen.combat.AttackDef;
import com.muamn.ashen.combat.AttackRunner;
import com.muamn.ashen.combat.CombatMath;
import com.muamn.ashen.combat.Combatant;
import com.muamn.ashen.combat.HitInfo;
import com.muamn.ashen.combat.WeaponDef;
import com.muamn.ashen.audio.Audio;
import com.muamn.ashen.audio.SoundBank;
import com.muamn.ashen.input.ControlState;
import com.muamn.ashen.world.CharacterBody;
import com.muamn.ashen.world.CollisionMesh;

/**
 * The player character: a state machine over a {@link CharacterBody}.
 *
 * Committed actions are the point. Once a roll or a swing starts, input stops
 * steering it - you chose, and now you live with it. That single rule is most of
 * what separates Souls combat from an action game where dodging is free, and it
 * is why the state machine owns velocity outright instead of blending inputs
 * into it every frame.
 */
public class Player implements Combatant {

    public enum State {
        GROUNDED, ROLLING, BACKSTEPPING, AIRBORNE, ATTACKING,
        PARRYING, RIPOSTING, STAGGERED, DEAD
    }

    public final CharacterBody body = new CharacterBody();
    public final Stats stats = new Stats();
    public final CharacterRig rig;
    public final AttackRunner attacks = new AttackRunner();

    /** What the player is carrying. */
    public final com.muamn.ashen.item.Inventory inventory = new com.muamn.ashen.item.Inventory();
    /** Item id the use button spends, or empty for the Estus flask. */
    public String quickItem = "";

    /** Flat damage added to every swing while a resin is on the blade. */
    private float buffDamage;
    private float buffTimer;

    /**
     * Where the player's own sounds go. Null is a supported state - a headless
     * run has no audio device and the player still has to move.
     */
    public Audio audio;
    /** Metres walked since the last footstep. Steps are paced by distance, not
     * by time, so walking and sprinting sound like walking and sprinting. */
    private float strideDistance;

    private WeaponDef weapon;

    private State state = State.GROUNDED;
    private float stateTime;

    /** Heading in degrees; the model faces +Z at 0. */
    private float facing;
    private float targetFacing;

    /** Locked movement direction for the duration of a committed action. */
    private final Vector3 lockedDir = new Vector3(0f, 0f, 1f);

    private final Vector3 wish = new Vector3();
    private final Vector3 tmp = new Vector3();
    private final Vector2 flatMove = new Vector2();

    private float time;
    private boolean invulnerable;
    private boolean guarding;

    /** Poise absorbed since the last hit, and how long until it resets. */
    private float poiseDamage;
    private float poiseTimer;
    /** Base poise. Armour raises this in Part 3; for now it is a flat value. */
    public float poise = 42f;

    /** Angle the last hit came from, for the stagger pose. */
    private float staggerAngle;
    private float staggerDuration = CombatMath.STAGGER_DURATION;

    /** Set for one frame when an attack of ours connected, for feedback. */
    public boolean dealtHit;
    /** Set for one frame when we took a hit. */
    public boolean tookHit;

    private Array<Combatant> targets = new Array<>();

    /** Follow-up queued during the current swing. 0 none, 1 light, 2 heavy. */
    private int bufferedAttack;
    /** Time left in which a roll can be cancelled into a rolling attack. */
    private float rollAttackWindow;

    /** Enemy being riposted, and whether the blow has landed yet. */
    private Combatant riposteVictim;
    private boolean riposteStruck;
    /** Time left open to a critical after our own swing was parried. */
    private float riposteableTimer;

    public Player(CharacterRig rig, WeaponDef weapon) {
        this.rig = rig;
        this.weapon = weapon;
        body.radius = Config.PLAYER_RADIUS;
        body.height = Config.PLAYER_HEIGHT;
    }

    public State getState() {
        return state;
    }

    public void setTargets(Array<Combatant> targets) {
        this.targets = targets;
    }

    public void setWeapon(WeaponDef weapon) {
        this.weapon = weapon;
    }

    @Override
    public float damageBonus() {
        return buffDamage;
    }

    /** Puts a resin on the blade. A second resin replaces the first. */
    public void applyBuff(float damage, float seconds) {
        buffDamage = damage;
        buffTimer = seconds;
    }

    /** Seconds of weapon buff left, for the HUD. Zero when there is none. */
    public float buffRemaining() {
        return Math.max(0f, buffTimer);
    }

    public void clearBuff() {
        buffDamage = 0f;
        buffTimer = 0f;
    }

    @Override
    public WeaponDef weapon() {
        return weapon;
    }

    @Override
    public int team() {
        return 0;
    }

    @Override
    public CharacterBody body() {
        return body;
    }

    @Override
    public Stats stats() {
        return stats;
    }

    @Override
    public float facing() {
        return facing;
    }

    @Override
    public boolean invulnerable() {
        return invulnerable || state == State.DEAD;
    }

    @Override
    public boolean blocking() {
        return guarding && state != State.ROLLING && state != State.STAGGERED;
    }

    @Override
    public boolean parrying() {
        if (state != State.PARRYING) return false;
        return stateTime >= Config.PARRY_WINDUP
                && stateTime < Config.PARRY_WINDUP + Config.PARRY_ACTIVE;
    }

    @Override
    public boolean riposteable() {
        return riposteableTimer > 0f;
    }

    @Override
    public void onAttackParried(Combatant parrier) {
        attacks.cancel();
        riposteableTimer = Config.RIPOSTEABLE_DURATION;
        staggerAngle = 0f;
        staggerDuration = Config.RIPOSTEABLE_DURATION;
        setState(State.STAGGERED);
    }

    @Override
    public void applyCritical(HitInfo hit) {
        if (state == State.DEAD) return;
        tookHit = true;
        riposteableTimer = 0f;
        // Criticals ignore guard and poise entirely - that is the whole point.
        stats.damage(CombatMath.afterDefence(hit.damage, 0.02f));
        attacks.cancel();
        staggerAngle = 0f;
        staggerDuration = CombatMath.STAGGER_DURATION * 1.6f;
        setState(State.STAGGERED);
        if (stats.isDead()) setState(State.DEAD);
    }

    @Override
    public Vector3 hitCenter(Vector3 out) {
        return out.set(body.position.x, body.position.y + body.height * 0.58f, body.position.z);
    }

    @Override
    public float hitRadius() {
        return body.radius + 0.12f;
    }

    @Override
    public boolean dead() {
        return state == State.DEAD;
    }

    public boolean isInvulnerable() {
        return invulnerable;
    }

    public float getFacing() {
        return facing;
    }

    /** Ground speed in metres/second, ignoring vertical motion. */
    public float groundSpeed() {
        return Vector3.len(body.velocity.x, 0f, body.velocity.z);
    }

    public void spawn(float x, float y, float z, float facingDeg) {
        body.teleport(x, y, z);
        facing = targetFacing = facingDeg;
        state = State.GROUNDED;
        stateTime = 0f;
        attacks.cancel();
        poiseDamage = 0f;
        bufferedAttack = 0;
        riposteableTimer = 0f;
        riposteVictim = null;
        stats.health = stats.maxHealth;
        stats.stamina = stats.maxStamina;
    }

    /**
     * One fixed simulation step.
     *
     * @param cameraYaw  yaw of the camera, so movement is camera-relative
     * @param lockTarget position being locked on to, or null
     */
    public void update(ControlState input, CollisionMesh mesh, float cameraYaw,
                       Vector3 lockTarget, float dt) {
        time += dt;
        stateTime += dt;
        dealtHit = false;
        tookHit = false;

        if (poiseTimer > 0f) {
            poiseTimer -= dt;
            if (poiseTimer <= 0f) poiseDamage = 0f;
        }
        if (rollAttackWindow > 0f) rollAttackWindow -= dt;
        if (riposteableTimer > 0f) riposteableTimer -= dt;
        if (buffTimer > 0f) {
            buffTimer -= dt;
            if (buffTimer <= 0f) buffDamage = 0f;
        }

        if (state == State.DEAD) {
            body.velocity.x = 0f;
            body.velocity.z = 0f;
            body.step(mesh, dt);
            rig.poseDeath(Math.min(stateTime / 0.9f, 1f));
            rig.place(body.position, facing);
            return;
        }

        guarding = input.guardHeld && state == State.GROUNDED && stats.stamina > 0f;

        // Camera-relative movement basis, flattened to the ground plane.
        float fx = -MathUtils.sinDeg(cameraYaw), fz = -MathUtils.cosDeg(cameraYaw);
        float rx = -fz, rz = fx;
        flatMove.set(input.move);
        if (flatMove.len2() > 1f) flatMove.nor();
        wish.set(fx * flatMove.y + rx * flatMove.x, 0f, fz * flatMove.y + rz * flatMove.x);
        float wishLen = Vector3.len(wish.x, 0f, wish.z);
        if (wishLen > 1e-4f) wish.scl(1f / wishLen);

        switch (state) {
            case GROUNDED:     updateGrounded(input, wishLen, lockTarget, dt); break;
            case ROLLING:      updateRoll(input, dt); break;
            case BACKSTEPPING: updateBackstep(dt); break;
            case AIRBORNE:     updateAirborne(wishLen, dt); break;
            case ATTACKING:    updateAttacking(input, lockTarget, dt); break;
            case PARRYING:     updateParry(dt); break;
            case RIPOSTING:    updateRiposte(dt); break;
            case STAGGERED:    updateStaggered(dt); break;
            default: break;
        }

        boolean actionBlocksRegen = state == State.ROLLING || state == State.BACKSTEPPING
                || state == State.ATTACKING || guarding;
        stats.update(dt, actionBlocksRegen);

        body.step(mesh, dt);

        if (state == State.GROUNDED && !body.grounded) {
            setState(State.AIRBORNE);
        } else if (state == State.AIRBORNE && body.grounded) {
            setState(State.GROUNDED);
        }

        updateFootsteps(dt);

        // Turn toward the intended heading. Committed actions keep their facing.
        float turnRate = committed() ? 0f : Config.TURN_SPEED * 57.29578f * dt;
        facing = approachAngle(facing, targetFacing, turnRate);

        updatePose(dt);
    }

    private boolean committed() {
        return state == State.ROLLING || state == State.BACKSTEPPING
                || state == State.STAGGERED || state == State.PARRYING
                || state == State.RIPOSTING
                || (state == State.ATTACKING && attacks.phase() != AttackRunner.Phase.WINDUP);
    }

    private void updateGrounded(ControlState input, float wishLen, Vector3 lockTarget, float dt) {
        if (input.rollPressed) {
            if (wishLen > 0.2f) {
                if (stats.spendStamina(Config.ROLL_STAMINA)) {
                    lockedDir.set(wish);
                    targetFacing = facing = headingOf(lockedDir);
                    setState(State.ROLLING);
                    return;
                }
            } else if (stats.spendStamina(Config.BACKSTEP_STAMINA)) {
                lockedDir.set(MathUtils.sinDeg(facing), 0f, MathUtils.cosDeg(facing)).scl(-1f);
                setState(State.BACKSTEPPING);
                return;
            }
        }

        boolean sprinting = input.sprintHeld && wishLen > 0.1f && stats.stamina > 0f && !guarding;

        // Guard held plus a light attack is a parry, not a swing. Reusing the
        // two buttons keeps the phone layout at six.
        if (input.attackLightPressed && guarding) {
            if (stats.spendStamina(Config.PARRY_STAMINA)) {
                setState(State.PARRYING);
                return;
            }
        }

        // An opening beats everything else: take it before considering a swing.
        if (input.attackLightPressed) {
            Combatant opening = findRiposteTarget();
            if (opening != null) {
                riposteVictim = opening;
                riposteStruck = false;
                tmp.set(opening.body().position).sub(body.position);
                targetFacing = facing = headingOf(tmp);
                setState(State.RIPOSTING);
                return;
            }
        }

        if (input.attackLightPressed || input.attackHeavyPressed) {
            AttackDef chosen;
            boolean heavy = input.attackHeavyPressed;
            int chain = 0;
            if (rollAttackWindow > 0f) {
                chosen = weapon.moveset.rolling;
            } else if (sprinting) {
                chosen = weapon.moveset.running;
            } else {
                chosen = heavy ? weapon.moveset.heavy(0) : weapon.moveset.light(0);
            }
            if (startAttack(chosen, heavy, chain, lockTarget)) return;
        }

        if (sprinting) {
            stats.drainStamina(Config.SPRINT_STAMINA_PER_SEC * dt);
            if (stats.stamina <= 0f) sprinting = false;
        }

        float speed = sprinting ? Config.RUN_SPEED
                : Config.WALK_SPEED * MathUtils.clamp(wishLen / 0.9f, 0f, 1f);
        if (guarding) speed *= 0.55f;
        if (wishLen <= 0.05f) speed = 0f;

        // Accelerate rather than snap, so direction changes have weight.
        float accel = sprinting ? 22f : 18f;
        tmp.set(wish).scl(speed);
        body.velocity.x = MathUtils.lerp(body.velocity.x, tmp.x, Math.min(1f, accel * dt));
        body.velocity.z = MathUtils.lerp(body.velocity.z, tmp.z, Math.min(1f, accel * dt));

        if (wishLen > 0.05f) {
            // While locked on, walk sideways facing the target instead of turning.
            if (lockTarget != null && !input.sprintHeld) {
                tmp.set(lockTarget).sub(body.position);
                targetFacing = headingOf(tmp);
            } else {
                targetFacing = headingOf(wish);
            }
        } else if (lockTarget != null) {
            tmp.set(lockTarget).sub(body.position);
            targetFacing = headingOf(tmp);
        }
    }

    /** @return true if the attack started. */
    private boolean startAttack(AttackDef attack, boolean heavy, int chain, Vector3 lockTarget) {
        // Attacks go through even on low stamina; you just pay for it afterwards.
        if (stats.stamina <= 0f) return false;
        stats.drainStamina(attack.staminaCost);
        if (lockTarget != null) {
            tmp.set(lockTarget).sub(body.position);
            targetFacing = facing = headingOf(tmp);
        }
        attacks.begin(attack, heavy, chain);
        bufferedAttack = 0;
        setState(State.ATTACKING);
        if (audio != null) {
            // Pitched by the weapon's own speed, so a dagger and a greatsword do
            // not sound like the same swing played at the same rate.
            audio.play(heavy ? SoundBank.SWING_HEAVY : SoundBank.SWING_LIGHT,
                    heavy ? 0.85f : 0.7f,
                    MathUtils.clamp(0.55f / Math.max(0.12f, attack.active + attack.windup),
                            0.8f, 1.35f) * Audio.vary(0.05f));
        }
        return true;
    }

    private void updateAttacking(ControlState input, Vector3 lockTarget, float dt) {
        AttackDef attack = attacks.current();
        if (attack == null) {
            setState(State.GROUNDED);
            return;
        }

        // Rolling out of recovery is the escape hatch, and it costs stamina.
        if (input.rollPressed && attacks.phase() == AttackRunner.Phase.RECOVERY
                && stats.spendStamina(Config.ROLL_STAMINA)) {
            attacks.cancel();
            lockedDir.set(wish.len2() > 0.04f ? wish
                    : tmp.set(MathUtils.sinDeg(facing), 0f, MathUtils.cosDeg(facing)));
            targetFacing = facing = headingOf(lockedDir);
            setState(State.ROLLING);
            return;
        }

        if (input.attackLightPressed) bufferedAttack = 1;
        else if (input.attackHeavyPressed) bufferedAttack = 2;

        // Slow tracking during the windup only: you can adjust your aim, not
        // steer a swing that has already left.
        if (lockTarget != null && attacks.phase() == AttackRunner.Phase.WINDUP) {
            tmp.set(lockTarget).sub(body.position);
            targetFacing = headingOf(tmp);
            facing = approachAngle(facing, targetFacing, 260f * dt);
        }

        float speed = attacks.stepSpeed();
        body.velocity.x = MathUtils.sinDeg(facing) * speed;
        body.velocity.z = MathUtils.cosDeg(facing) * speed;

        if (attacks.resolveHits(this, weapon, targets) > 0) dealtHit = true;

        boolean finished = attacks.update(dt);

        if (!finished && bufferedAttack != 0 && attacks.canChain()) {
            boolean heavy = bufferedAttack == 2;
            int next = attacks.getChainIndex() + 1;
            AttackDef follow = heavy ? weapon.moveset.heavy(next) : weapon.moveset.light(next);
            if (stats.stamina > 0f) {
                stats.drainStamina(follow.staminaCost);
                attacks.begin(follow, heavy, next);
                stateTime = 0f;
            }
            bufferedAttack = 0;
        } else if (finished) {
            setState(State.GROUNDED);
        }
    }

    /**
     * The nearest enemy that is open to a critical and close enough in front.
     */
    private Combatant findRiposteTarget() {
        Combatant best = null;
        float bestDistance = Config.RIPOSTE_RANGE;
        for (Combatant candidate : targets) {
            if (candidate == this || candidate.dead() || candidate.team() == team()) continue;
            if (!candidate.riposteable()) continue;
            tmp.set(candidate.body().position).sub(body.position);
            tmp.y = 0f;
            float distance = tmp.len();
            if (distance > bestDistance) continue;
            // Must be roughly in front, or you would riposte behind your back.
            if (distance > 1e-3f) {
                float heading = headingOf(tmp);
                if (Math.abs(CombatMath.angleDifference(facing, heading)) > 70f) continue;
            }
            bestDistance = distance;
            best = candidate;
        }
        return best;
    }

    private void updateParry(float dt) {
        body.velocity.x *= 1f - Math.min(1f, 9f * dt);
        body.velocity.z *= 1f - Math.min(1f, 9f * dt);
        float total = Config.PARRY_WINDUP + Config.PARRY_ACTIVE + Config.PARRY_RECOVERY;
        if (stateTime >= total) setState(State.GROUNDED);
    }

    private void updateRiposte(float dt) {
        body.velocity.x *= 1f - Math.min(1f, 10f * dt);
        body.velocity.z *= 1f - Math.min(1f, 10f * dt);

        float strikeAt = Config.RIPOSTE_DURATION * Config.RIPOSTE_STRIKE_AT;
        if (!riposteStruck && stateTime >= strikeAt && riposteVictim != null) {
            riposteStruck = true;
            AttackDef attack = weapon.moveset.heavy(0);
            float damage = (weapon.damageAgainst(stats, attack) + buffDamage)
                    * (weapon.critical / 100f) * Config.RIPOSTE_MULTIPLIER;
            riposteHit.set(this, damage, attack.poise * 3f);
            riposteHit.critical = true;
            riposteHit.direction.set(MathUtils.sinDeg(facing), 0f, MathUtils.cosDeg(facing));
            riposteVictim.hitCenter(riposteHit.point);
            riposteVictim.applyCritical(riposteHit);
            dealtHit = true;
        }
        if (stateTime >= Config.RIPOSTE_DURATION) {
            riposteVictim = null;
            setState(State.GROUNDED);
        }
    }

    private final HitInfo riposteHit = new HitInfo();

    private void updateStaggered(float dt) {
        body.velocity.x *= 1f - Math.min(1f, 7f * dt);
        body.velocity.z *= 1f - Math.min(1f, 7f * dt);
        if (stateTime >= staggerDuration) setState(State.GROUNDED);
    }

    private void updateRoll(ControlState input, float dt) {
        float t = stateTime / Config.ROLL_DURATION;
        invulnerable = t >= Config.ROLL_IFRAME_START && t <= Config.ROLL_IFRAME_END;

        // Fast out of the gate, settling toward the end.
        float speed = Config.ROLL_SPEED * (1f - MathUtils.clamp(t, 0f, 1f) * 0.72f);
        body.velocity.x = lockedDir.x * speed;
        body.velocity.z = lockedDir.z * speed;

        if (t >= 1f) {
            invulnerable = false;
            rollAttackWindow = 0.28f;
            setState(State.GROUNDED);
        }
    }

    private void updateBackstep(float dt) {
        float t = stateTime / Config.BACKSTEP_DURATION;
        float speed = Config.BACKSTEP_SPEED * (1f - MathUtils.clamp(t, 0f, 1f)) * 1.3f;
        body.velocity.x = lockedDir.x * speed;
        body.velocity.z = lockedDir.z * speed;
        if (t >= 1f) setState(State.GROUNDED);
    }

    private void updateAirborne(float wishLen, float dt) {
        // Very little air control, by design.
        if (wishLen > 0.05f) {
            body.velocity.x = MathUtils.lerp(body.velocity.x, wish.x * Config.WALK_SPEED,
                    Math.min(1f, 1.6f * dt));
            body.velocity.z = MathUtils.lerp(body.velocity.z, wish.z * Config.WALK_SPEED,
                    Math.min(1f, 1.6f * dt));
            targetFacing = headingOf(wish);
        }
    }

    @Override
    public void applyHit(HitInfo hit) {
        if (invulnerable()) return;
        // A parried swing costs the parrier nothing but a sliver of stamina.
        if (hit.wasParried) {
            stats.drainStamina(4f);
            if (audio != null) audio.play(SoundBank.PARRY, 1f, Audio.vary(0.04f));
            return;
        }
        tookHit = true;

        // Being caught from behind hurts the same way it hurts an enemy.
        if (hit.attacker != null
                && CombatMath.isBackstab(facing, hit.attacker.facing(), hit.direction)) {
            hit.critical = true;
            hit.damage *= (hit.attacker.weapon().critical / 100f) * Config.BACKSTAB_MULTIPLIER;
        }

        float damage = hit.damage;
        boolean blocked = blocking()
                && CombatMath.isFrontal(facing, hit.direction, CombatMath.GUARD_ARC)
                && !hit.critical;

        if (blocked) {
            float cost = CombatMath.guardStamina(weapon, damage);
            damage = CombatMath.damageThroughGuard(weapon, damage);
            hit.wasBlocked = true;
            if (!stats.spendStamina(cost)) {
                // Guard broken: the rest of the stamina goes and you are opened up.
                stats.drainStamina(stats.stamina);
                staggerAngle = CombatMath.angleDifference(facing, headingOf(hit.direction));
                staggerDuration = CombatMath.GUARD_BREAK_DURATION;
                hit.staggered = true;
                setState(State.STAGGERED);
            }
        } else {
            poiseDamage += hit.poise;
            poiseTimer = CombatMath.POISE_RECOVERY;
            if (poiseDamage >= poise || hit.critical) {
                poiseDamage = 0f;
                staggerAngle = CombatMath.angleDifference(facing, headingOf(hit.direction));
                staggerDuration = CombatMath.STAGGER_DURATION;
                hit.staggered = true;
                attacks.cancel();
                setState(State.STAGGERED);
            }
        }

        stats.damage(CombatMath.afterDefence(damage, 0.10f));

        if (audio != null) {
            if (blocked) audio.play(SoundBank.HIT_GUARD, 0.9f, Audio.vary(0.07f));
            else if (hit.critical) audio.play(SoundBank.CRITICAL, 1f, 1f);
            else audio.play(SoundBank.HIT_FLESH, 0.9f, Audio.vary(0.08f));
            // The grunt sits under the impact rather than replacing it.
            if (!blocked) audio.play(SoundBank.HURT, 0.55f, Audio.vary(0.10f));
        }

        // Knockback, scaled down when the blow was caught on a guard.
        float push = blocked ? 1.2f : 3.0f;
        body.velocity.x += hit.direction.x * push;
        body.velocity.z += hit.direction.z * push;

        if (stats.isDead()) {
            attacks.cancel();
            setState(State.DEAD);
        }
    }

    private void updatePose(float dt) {
        switch (state) {
            case ROLLING:
                rig.poseRoll(stateTime / Config.ROLL_DURATION);
                break;
            case BACKSTEPPING:
                rig.poseBackstep(stateTime / Config.BACKSTEP_DURATION);
                break;
            case AIRBORNE:
                rig.poseFall(body.velocity.y);
                break;
            case ATTACKING:
                if (attacks.current() != null) {
                    rig.poseAttack(attacks.current(), attacks.normalisedTime());
                }
                break;
            case PARRYING:
                rig.poseParry(stateTime
                        / (Config.PARRY_WINDUP + Config.PARRY_ACTIVE + Config.PARRY_RECOVERY));
                break;
            case RIPOSTING:
                rig.poseRiposte(stateTime / Config.RIPOSTE_DURATION);
                break;
            case STAGGERED:
                rig.poseStagger(stateTime / staggerDuration, staggerAngle);
                break;
            case DEAD:
                rig.poseDeath(Math.min(stateTime / 0.9f, 1f));
                break;
            default:
                if (guarding) rig.poseGuard(dt, groundSpeed(), Config.RUN_SPEED, time);
                else rig.poseLocomotion(dt, groundSpeed(), Config.RUN_SPEED, time);
                break;
        }
        rig.place(body.position, facing);
    }

    private void setState(State next) {
        State previous = state;
        state = next;
        stateTime = 0f;
        if (next != State.ROLLING) invulnerable = false;
        cueForState(previous, next);
    }

    /**
     * One sound per state entry, fired from the single place states change so a
     * new transition cannot be added without one.
     */
    private void cueForState(State previous, State next) {
        if (audio == null || previous == next) return;
        switch (next) {
            case ROLLING:
            case BACKSTEPPING:
                audio.play(SoundBank.ROLL, 0.75f, Audio.vary(0.06f));
                break;
            case PARRYING:
                // The swish of the shield coming up; the ring only happens if it
                // actually catches something, and that is fired from applyHit.
                audio.play(SoundBank.SWING_LIGHT, 0.35f, 1.5f);
                break;
            case STAGGERED:
                audio.play(SoundBank.STAGGER, 0.8f, Audio.vary(0.08f));
                break;
            case DEAD:
                audio.play(SoundBank.DEATH, 1f, 1f);
                break;
            case GROUNDED:
                if (previous == State.AIRBORNE && body.landingImpact > 3.5f) {
                    audio.play(SoundBank.LAND,
                            MathUtils.clamp(body.landingImpact / 14f, 0.25f, 1f),
                            Audio.vary(0.05f));
                }
                strideDistance = 0f;
                break;
            default:
                break;
        }
    }

    /** Paces footsteps by ground covered. Called once per simulation step. */
    private void updateFootsteps(float dt) {
        if (audio == null) return;
        if (state != State.GROUNDED || !body.grounded) return;
        float speed = groundSpeed();
        if (speed < 0.4f) {
            strideDistance = 0f;
            return;
        }
        strideDistance += speed * dt;
        // A longer stride when running, so the rate does not become a machine gun.
        float stride = speed > Config.WALK_SPEED * 1.4f ? 1.85f : 1.35f;
        if (strideDistance < stride) return;
        strideDistance -= stride;
        audio.play(SoundBank.FOOTSTEP,
                MathUtils.clamp(speed / Config.RUN_SPEED, 0.35f, 1f) * 0.7f,
                Audio.vary(0.12f));
    }

    /** Heading in degrees for a direction vector, matching the model's +Z front. */
    private static float headingOf(Vector3 dir) {
        return MathUtils.atan2(dir.x, dir.z) * MathUtils.radiansToDegrees;
    }

    private static float approachAngle(float current, float target, float maxDelta) {
        if (maxDelta <= 0f) return current;
        float diff = ((target - current) % 360f + 540f) % 360f - 180f;
        if (Math.abs(diff) <= maxDelta) return target;
        return current + Math.signum(diff) * maxDelta;
    }

    /** Chest height, used as the camera focus and the lock-on anchor. */
    public Vector3 chest(Vector3 out) {
        return out.set(body.position.x, body.position.y + body.height * 0.62f, body.position.z);
    }
}
