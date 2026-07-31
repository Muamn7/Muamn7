package com.muamn.ashen.entity;

import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Disposable;

import com.muamn.ashen.combat.AttackDef;

/**
 * How an enemy is drawn, decoupled from how it behaves.
 *
 * There are two kinds in the game and they have nothing in common under the
 * hood: a procedurally posed humanoid, and an imported rig playing exported
 * animations. Keeping the AI blind to the difference is what lets an imported
 * model be dropped in as a new enemy without touching a line of behaviour code.
 */
public interface EnemyVisual extends Disposable {

    enum Pose { IDLE, MOVE, ATTACK, STAGGER, DEAD }

    /**
     * @param stateTime seconds in the current AI state
     * @param attack    the attack in progress, or null
     * @param attackT   0..1 through that attack
     */
    void update(float dt, Pose pose, float speed, float stateTime, AttackDef attack, float attackT);

    void place(Vector3 feetPosition, float facingDeg);

    ModelInstance instance();
}
