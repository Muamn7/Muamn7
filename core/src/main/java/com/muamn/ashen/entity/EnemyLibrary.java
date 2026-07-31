package com.muamn.ashen.entity;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.GdxRuntimeException;
import com.badlogic.gdx.utils.JsonReader;
import com.badlogic.gdx.utils.JsonValue;
import com.badlogic.gdx.utils.ObjectMap;

/**
 * Loads the bestiary and the boss roster from JSON.
 *
 * Bosses share the enemy schema and add phases, so one loader reads both files
 * and one code path spawns either. That keeps a boss from being a special kind
 * of object - it is an enemy whose numbers happen to be frightening.
 */
public class EnemyLibrary {

    private final ObjectMap<String, EnemyDef> byId = new ObjectMap<>();
    private final Array<EnemyDef> enemies = new Array<>();
    private final Array<EnemyDef> bosses = new Array<>();

    public void load() {
        load("data/enemies.json", "data/bosses.json");
    }

    public void load(String enemyPath, String bossPath) {
        parse(Gdx.files.internal(enemyPath).readString(),
              Gdx.files.internal(bossPath).readString());
        Gdx.app.log("EnemyLibrary", "loaded " + enemies.size + " enemies and "
                + bosses.size + " bosses");
    }

    /** Parses from raw JSON, so the bestiary can be unit tested without a backend. */
    public void parse(String enemyJson, String bossJson) {
        JsonReader reader = new JsonReader();
        parseList(reader.parse(enemyJson).require("enemies"), false);
        if (bossJson != null) parseList(reader.parse(bossJson).require("bosses"), true);
    }

    private void parseList(JsonValue array, boolean boss) {
        for (JsonValue v = array.child; v != null; v = v.next) {
            EnemyDef def = parseEnemy(v, boss);
            if (byId.containsKey(def.id)) {
                throw new GdxRuntimeException("duplicate enemy id: " + def.id);
            }
            byId.put(def.id, def);
            (boss ? bosses : enemies).add(def);
        }
    }

    private EnemyDef parseEnemy(JsonValue v, boolean boss) {
        EnemyDef def = new EnemyDef();
        def.id = v.require("id").asString();
        def.nameAr = v.getString("nameAr", def.id);
        def.nameEn = v.getString("nameEn", def.id);
        def.boss = boss;

        def.health = v.getFloat("health", def.health);
        def.souls = v.getLong("souls", def.souls);
        def.poise = v.getFloat("poise", def.poise);
        def.absorption = v.getFloat("absorption", def.absorption);
        def.strength = v.getInt("strength", def.strength);
        def.dexterity = v.getInt("dexterity", def.dexterity);

        def.radius = v.getFloat("radius", def.radius);
        def.height = v.getFloat("height", def.height);

        def.walkSpeed = v.getFloat("walkSpeed", def.walkSpeed);
        def.runSpeed = v.getFloat("runSpeed", def.runSpeed);
        def.turnSpeed = v.getFloat("turnSpeed", def.turnSpeed);
        def.stepScale = v.getFloat("stepScale", def.stepScale);

        def.aggroRange = v.getFloat("aggroRange", def.aggroRange);
        def.leashRange = v.getFloat("leashRange", def.leashRange);
        def.alertDelay = v.getFloat("alertDelay", def.alertDelay);
        def.circleTime = v.getFloat("circleTime", def.circleTime);
        def.recoverTime = v.getFloat("recoverTime", def.recoverTime);
        def.heavyChance = v.getFloat("heavyChance", def.heavyChance);

        def.weaponId = v.getString("weapon", def.weaponId);

        JsonValue thresholds = v.get("phases");
        if (thresholds != null && thresholds.isArray()) {
            def.phaseThresholds = thresholds.asFloatArray();
        }
        JsonValue aggression = v.get("phaseAggression");
        if (aggression != null && aggression.isArray()) {
            def.phaseAggression = aggression.asFloatArray();
        }

        JsonValue body = v.get("body");
        if (body != null) def.body = parseBody(body);
        return def;
    }

    private BodyDef parseBody(JsonValue v) {
        BodyDef body = new BodyDef();
        body.kind = BodyDef.Kind.valueOf(v.getString("kind", "HUMANOID"));
        body.preset = v.getString("preset", body.preset);
        body.model = v.getString("model", null);

        body.scale = v.getFloat("scale", 1f);
        body.bulk = v.getFloat("bulk", 1f);
        body.hunch = v.getFloat("hunch", 0f);
        body.armLength = v.getFloat("armLength", 1f);
        body.legPairs = v.getInt("legPairs", -1);

        body.armor = v.getString("armor", null);
        body.cloth = v.getString("cloth", null);
        body.skin = v.getString("skin", null);
        body.trim = v.getString("trim", null);
        if (v.has("helmet")) body.helmet = v.getBoolean("helmet");
        if (v.has("tabard")) body.tabard = v.getBoolean("tabard");
        if (v.has("pauldrons")) body.pauldrons = v.getBoolean("pauldrons");

        body.bodyMaterial = v.getString("bodyMaterial", null);
        body.limbMaterial = v.getString("limbMaterial", null);
        body.detailMaterial = v.getString("detailMaterial", null);

        String tint = v.getString("tint", null);
        if (tint != null) body.tint.set(Color.valueOf(tint));
        return body;
    }

    public EnemyDef get(String id) {
        EnemyDef def = byId.get(id);
        if (def == null) throw new GdxRuntimeException("unknown enemy: " + id);
        return def;
    }

    public boolean has(String id) {
        return byId.containsKey(id);
    }

    /** Ordinary enemies, in file order. */
    public Array<EnemyDef> all() {
        return enemies;
    }

    /** Bosses, in file order. */
    public Array<EnemyDef> allBosses() {
        return bosses;
    }

    public int size() {
        return enemies.size;
    }

    public int bossCount() {
        return bosses.size;
    }
}
