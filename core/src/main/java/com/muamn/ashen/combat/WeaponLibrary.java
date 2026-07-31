package com.muamn.ashen.combat;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.GdxRuntimeException;
import com.badlogic.gdx.utils.JsonReader;
import com.badlogic.gdx.utils.JsonValue;
import com.badlogic.gdx.utils.ObjectMap;

/**
 * Loads the weapons and their movesets from JSON.
 *
 * Frame data is the single biggest lever on how the game feels, and it needs to
 * be tuned by playing rather than by editing Java. Movesets live per weapon
 * class so sixteen weapons need sixteen stat blocks, not sixteen copies of the
 * same six attacks.
 */
public class WeaponLibrary {

    private final ObjectMap<WeaponClass, Moveset> movesets = new ObjectMap<>();
    private final ObjectMap<String, WeaponDef> weapons = new ObjectMap<>();
    private final Array<WeaponDef> ordered = new Array<>();

    public void load() {
        load("data/movesets.json", "data/weapons.json");
    }

    public void load(String movesetPath, String weaponPath) {
        parse(Gdx.files.internal(movesetPath).readString(),
              Gdx.files.internal(weaponPath).readString());
        Gdx.app.log("WeaponLibrary", "loaded " + ordered.size + " weapons across "
                + movesets.size + " classes");
    }

    /**
     * Parses from raw JSON rather than files, so the frame data can be unit
     * tested without standing up a graphics backend.
     */
    public void parse(String movesetJson, String weaponJson) {
        JsonReader reader = new JsonReader();
        parseMovesets(reader.parse(movesetJson));
        parseWeapons(reader.parse(weaponJson));
    }

    private void parseMovesets(JsonValue root) {
        JsonValue node = root.require("movesets");
        for (JsonValue entry = node.child; entry != null; entry = entry.next) {
            WeaponClass cls = WeaponClass.valueOf(entry.name);
            movesets.put(cls, new Moveset(
                    parseChain(entry.require("light"), entry.name + ".light"),
                    parseChain(entry.require("heavy"), entry.name + ".heavy"),
                    parseAttack(entry.require("running"), entry.name + ".running"),
                    parseAttack(entry.require("rolling"), entry.name + ".rolling")));
        }
    }

    private AttackDef[] parseChain(JsonValue array, String id) {
        AttackDef[] out = new AttackDef[array.size];
        int i = 0;
        for (JsonValue a = array.child; a != null; a = a.next, i++) {
            out[i] = parseAttack(a, id + i);
        }
        return out;
    }

    private AttackDef parseAttack(JsonValue v, String id) {
        return new AttackDef(id,
                AttackDef.Motion.valueOf(v.getString("motion")),
                v.getFloat("windup"), v.getFloat("active"), v.getFloat("recovery"),
                v.getFloat("damage"), v.getFloat("poise"), v.getFloat("stamina"),
                v.getFloat("reach"), v.getFloat("arc"), v.getFloat("step", 0f));
    }

    private void parseWeapons(JsonValue root) {
        for (JsonValue w = root.require("weapons").child; w != null; w = w.next) {
            WeaponDef def = new WeaponDef();
            def.id = w.require("id").asString();
            def.nameAr = w.getString("nameAr", def.id);
            def.nameEn = w.getString("nameEn", def.id);
            def.weaponClass = WeaponClass.valueOf(w.require("class").asString());
            def.moveset = movesets.get(def.weaponClass);
            if (def.moveset == null) {
                throw new GdxRuntimeException("no moveset for class " + def.weaponClass
                        + " needed by weapon " + def.id);
            }

            def.weight = w.getFloat("weight", 1f);
            def.physical = w.getFloat("physical", 60f);
            def.critical = w.getFloat("critical", 100f);
            def.guardAbsorb = w.getFloat("guardAbsorb", 0.35f);
            def.stability = w.getFloat("stability", 0.25f);

            JsonValue req = w.get("requirement");
            if (req != null) {
                def.reqStrength = req.getInt("strength", 0);
                def.reqDexterity = req.getInt("dexterity", 0);
                def.reqIntelligence = req.getInt("intelligence", 0);
                def.reqFaith = req.getInt("faith", 0);
            }

            JsonValue scaling = w.get("scaling");
            if (scaling != null) {
                def.scaleStrength = grade(scaling.getString("strength", "-"));
                def.scaleDexterity = grade(scaling.getString("dexterity", "-"));
                def.scaleIntelligence = grade(scaling.getString("intelligence", "-"));
                def.scaleFaith = grade(scaling.getString("faith", "-"));
            }

            JsonValue model = w.get("model");
            if (model != null) {
                def.modelKind = WeaponDef.ModelKind.valueOf(model.getString("kind", "SWORD"));
                def.length = model.getFloat("length", 1f);
                def.width = model.getFloat("width", 0.09f);
                def.thickness = model.getFloat("thickness", 0.02f);
                def.guardWidth = model.getFloat("guard", 0.28f);
                def.curve = model.getFloat("curve", 0f);
                def.headWidth = model.getFloat("headWidth", 0.24f);
                def.headDepth = model.getFloat("headDepth", 0.14f);
                def.headRadius = model.getFloat("headRadius", 0.10f);
                def.headLength = model.getFloat("headLength", 0.28f);
                def.haft = model.getFloat("haft", 0.04f);
                def.bladeMaterial = model.getString("blade", "steel");
                def.gripMaterial = model.getString("grip", "leather");
            }

            weapons.put(def.id, def);
            ordered.add(def);
        }
    }

    private static Scaling grade(String letter) {
        if (letter == null || letter.isEmpty() || letter.equals("-")) return Scaling.NONE;
        return Scaling.valueOf(letter.toUpperCase());
    }

    public WeaponDef get(String id) {
        WeaponDef def = weapons.get(id);
        if (def == null) throw new GdxRuntimeException("unknown weapon: " + id);
        return def;
    }

    public boolean has(String id) {
        return weapons.containsKey(id);
    }

    /** All weapons, in the order they appear in the JSON. */
    public Array<WeaponDef> all() {
        return ordered;
    }

    public int size() {
        return ordered.size;
    }
}
