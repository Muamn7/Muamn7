package com.muamn.ashen.entity;

import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.math.Vector3;

import com.muamn.ashen.combat.AttackDef;

/** Draws an enemy with the procedural humanoid rig. */
public class RigVisual implements EnemyVisual {

    private final CharacterRig rig;
    private final float runSpeed;
    private float time;

    public RigVisual(CharacterRig rig, float runSpeed) {
        this.rig = rig;
        this.runSpeed = runSpeed;
    }

    @Override
    public void update(float dt, Pose pose, float speed, float stateTime,
                       AttackDef attack, float attackT) {
        time += dt;
        switch (pose) {
            case ATTACK:
                if (attack != null) rig.poseAttack(attack, attackT);
                else rig.poseLocomotion(dt, speed, runSpeed, time);
                break;
            case STAGGER:
                rig.poseStagger(Math.min(stateTime / 0.55f, 1f), 0f);
                break;
            case DEAD:
                rig.poseDeath(Math.min(stateTime / 0.9f, 1f));
                break;
            default:
                rig.poseLocomotion(dt, speed, runSpeed, time);
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

    public CharacterRig rig() {
        return rig;
    }

    @Override
    public void dispose() {
        rig.model.dispose();
    }
}
