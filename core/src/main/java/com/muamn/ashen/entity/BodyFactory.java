package com.muamn.ashen.entity;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.g3d.Model;

import com.muamn.ashen.world.AssetOverrides;
import com.muamn.ashen.world.TextureFactory;

/**
 * Turns a {@link BodyDef} into something drawable.
 *
 * The one guarantee this makes is that it always returns a visual. An imported
 * model that is missing, unreadable or has no animations falls back to the
 * procedural body the def would otherwise have used, so a level can never fail
 * to populate because an optional asset is absent.
 */
public final class BodyFactory {

    private BodyFactory() {}

    public static EnemyVisual create(BodyDef def, TextureFactory textures, float runSpeed) {
        if (def.kind == BodyDef.Kind.IMPORTED && def.model != null) {
            Model imported = AssetOverrides.loadModel(def.model);
            if (imported != null && imported.animations.size > 0) {
                return new AnimatedVisual(imported, def.scale);
            }
            if (imported != null) imported.dispose();
            Gdx.app.log("BodyFactory", "imported model '" + def.model
                    + "' unusable - falling back to a procedural body");
        }

        if (def.kind == BodyDef.Kind.CREATURE) {
            CreatureSpec spec = def.toCreature();
            return new CreatureVisual(new CreatureRig(
                    CreatureFactory.build(spec, textures), spec));
        }

        HumanoidSpec spec = def.toHumanoid();
        return new RigVisual(new CharacterRig(
                HumanoidFactory.build(spec, textures), spec), runSpeed);
    }
}
