package com.muamn.ashen.entity;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.graphics.g3d.model.Animation;
import com.badlogic.gdx.graphics.g3d.utils.AnimationController;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.ObjectMap;

import com.muamn.ashen.combat.AttackDef;

/**
 * Draws an enemy with an imported rig and its exported animations.
 *
 * Animation names come from whatever tool exported the model, so they are
 * matched by substring rather than assumed: the rig in this project ships clips
 * called {@code SC_SC_Idle} and {@code SC_SC_Jab}, and hard-coding those strings
 * would mean the next imported creature needs new code. Anything unmatched falls
 * back to the idle clip, so a partially-animated model still works.
 */
public class AnimatedVisual implements EnemyVisual {

    /** Candidate name fragments per pose, best match first. */
    private static final ObjectMap<Pose, String[]> WANTED = new ObjectMap<>();

    static {
        WANTED.put(Pose.IDLE, new String[]{"idle", "wait", "stand"});
        WANTED.put(Pose.MOVE, new String[]{"stepforward", "walk", "run", "step", "move"});
        WANTED.put(Pose.ATTACK, new String[]{"jab", "attack", "strike", "swing", "sweep"});
        WANTED.put(Pose.STAGGER, new String[]{"flinch", "hit", "stagger", "damage"});
        WANTED.put(Pose.DEAD, new String[]{"death", "die", "fall_from", "jump_down"});
    }

    private final Model model;
    private final ModelInstance instance;
    private final AnimationController animator;
    private final ObjectMap<Pose, String> clips = new ObjectMap<>();
    /** Heavier attacks pick this instead, when the rig has a second attack clip. */
    private String heavyAttackClip;

    private final float scale;
    private Pose current;
    private String currentClip;

    public AnimatedVisual(Model model, float scale) {
        this.model = model;
        this.scale = scale;
        this.instance = new ModelInstance(model);
        this.animator = new AnimationController(instance);

        for (ObjectMap.Entry<Pose, String[]> entry : WANTED) {
            String found = match(entry.value);
            if (found != null) clips.put(entry.key, found);
        }
        heavyAttackClip = match(new String[]{"chargestrike", "sweep", "heavy", "slam"});

        if (!clips.containsKey(Pose.IDLE) && model.animations.size > 0) {
            clips.put(Pose.IDLE, model.animations.first().id);
        }
        Gdx.app.log("AnimatedVisual", "clips " + clips.toString());
    }

    private String match(String[] fragments) {
        for (String fragment : fragments) {
            for (Animation a : model.animations) {
                if (a.id.toLowerCase().contains(fragment)) return a.id;
            }
        }
        return null;
    }

    @Override
    public void update(float dt, Pose pose, float speed, float stateTime,
                       AttackDef attack, float attackT) {
        String want = clips.get(pose);
        if (pose == Pose.ATTACK && attack != null && heavyAttackClip != null
                && attack.damage > 1.2f) {
            want = heavyAttackClip;
        }
        if (want == null) want = clips.get(Pose.IDLE);

        if (want != null && !want.equals(currentClip)) {
            currentClip = want;
            // Death plays once and holds; everything else loops.
            int loops = pose == Pose.DEAD ? 1 : -1;
            // A short blend hides the fact that these clips were never authored
            // to follow one another.
            animator.animate(want, loops, speedFor(pose, attack, speed), null, 0.15f);
        }
        current = pose;
        animator.update(dt);
    }

    /**
     * Retimes a clip so it matches the gameplay it represents: a walk cycle
     * follows actual ground speed, and an attack clip is stretched to the
     * attack's real duration so the visible swing lines up with the hitbox.
     */
    private float speedFor(Pose pose, AttackDef attack, float speed) {
        if (pose == Pose.ATTACK && attack != null && currentClip != null) {
            Animation a = model.getAnimation(currentClip);
            if (a != null && a.duration > 0.05f) {
                return Math.max(0.25f, a.duration / attack.duration());
            }
        }
        if (pose == Pose.MOVE) return Math.max(0.5f, speed / 2.2f);
        return 1f;
    }

    @Override
    public void place(Vector3 feetPosition, float facingDeg) {
        instance.transform.setToTranslation(feetPosition);
        // The imported rig faces -Z in glTF convention; the game's headings
        // treat +Z as forward, so add half a turn.
        instance.transform.rotate(Vector3.Y, facingDeg + 180f);
        if (scale != 1f) instance.transform.scale(scale, scale, scale);
    }

    @Override
    public ModelInstance instance() {
        return instance;
    }

    public Pose currentPose() {
        return current;
    }

    @Override
    public void dispose() {
        model.dispose();
    }
}
