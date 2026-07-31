package com.muamn.ashen.entity;

import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.math.Vector3;

import com.muamn.ashen.combat.AttackDef;

/** Draws an enemy with the procedural creature rig. */
public class CreatureVisual implements EnemyVisual {

    private final CreatureRig rig;

    public CreatureVisual(CreatureRig rig) {
        this.rig = rig;
    }

    @Override
    public void update(float dt, Pose pose, float speed, float stateTime,
                       AttackDef attack, float attackT) {
        switch (pose) {
            case ATTACK:
                if (attack != null) rig.poseAttack(attack, attackT);
                else rig.poseLocomotion(dt, speed);
                break;
            case STAGGER:
                rig.poseStagger(Math.min(stateTime / 0.55f, 1f));
                break;
            case DEAD:
                rig.poseDeath(Math.min(stateTime / 0.9f, 1f));
                break;
            default:
                rig.poseLocomotion(dt, speed);
                break;
        }
    }

    @Override
    public void place(Vector3 feetPosition, float facingDeg) {
        rig.place(feetPosition, facingDeg);
    }

    @Override
    public ModelInstance instance() {
        return rig.instance;
    }

    public CreatureRig rig() {
        return rig;
    }

    @Override
    public void dispose() {
        rig.getModel().dispose();
    }
}
