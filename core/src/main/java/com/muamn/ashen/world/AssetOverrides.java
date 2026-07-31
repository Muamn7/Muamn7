package com.muamn.ashen.world;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.files.FileHandle;
import com.badlogic.gdx.graphics.Texture;
import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.loader.G3dModelLoader;
import com.badlogic.gdx.graphics.g3d.loader.ObjLoader;
import com.badlogic.gdx.utils.UBJsonReader;

/**
 * Optional drop-in replacements for the procedural assets.
 *
 * Everything the game needs is generated at runtime, so it never depends on a
 * download. But art beats code, so each asset first looks for a real file:
 *
 * <pre>
 *   assets/imported/textures/&lt;name&gt;.png
 *   assets/imported/models/&lt;name&gt;.{g3db,g3dj,obj}
 * </pre>
 *
 * If the file is there it wins, with no code change. That keeps the door open
 * for CC0 packs (Kenney, OpenGameArt, Quaternius) or anything exported from
 * Blender, without ever letting a missing file break the build.
 */
public final class AssetOverrides {

    public static final String TEXTURE_DIR = "imported/textures/";
    public static final String MODEL_DIR = "imported/models/";

    private AssetOverrides() {}

    /** @return the imported texture for {@code name}, or null to use the generated one. */
    public static Texture loadTexture(String name) {
        FileHandle f = resolve(TEXTURE_DIR + name + ".png");
        if (f == null) return null;
        try {
            Gdx.app.log("AssetOverrides", "using imported texture: " + f.path());
            return new Texture(f);
        } catch (Exception e) {
            Gdx.app.error("AssetOverrides", "failed to load " + f.path() + " - falling back", e);
            return null;
        }
    }

    /** @return the imported model for {@code name}, or null to use the generated one. */
    public static Model loadModel(String name) {
        String[] exts = {".g3db", ".g3dj", ".obj"};
        for (String ext : exts) {
            FileHandle f = resolve(MODEL_DIR + name + ext);
            if (f == null) continue;
            try {
                Gdx.app.log("AssetOverrides", "using imported model: " + f.path());
                if (ext.equals(".obj")) return new ObjLoader().loadModel(f);
                return new G3dModelLoader(new UBJsonReader()).loadModel(f);
            } catch (Exception e) {
                Gdx.app.error("AssetOverrides", "failed to load " + f.path() + " - falling back", e);
                return null;
            }
        }
        return null;
    }

    /**
     * Looks in the local directory first (so assets can be dropped next to a
     * desktop build without rebuilding) then in the packaged assets.
     */
    private static FileHandle resolve(String path) {
        if (Gdx.files == null) return null;
        try {
            FileHandle local = Gdx.files.local(path);
            if (local.exists() && !local.isDirectory()) return local;
        } catch (Exception ignored) {
            // Local storage is not available on every backend; internal is enough.
        }
        FileHandle internal = Gdx.files.internal(path);
        return internal.exists() && !internal.isDirectory() ? internal : null;
    }
}
