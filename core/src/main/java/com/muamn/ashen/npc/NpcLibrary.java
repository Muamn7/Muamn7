package com.muamn.ashen.npc;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.GdxRuntimeException;
import com.badlogic.gdx.utils.JsonReader;
import com.badlogic.gdx.utils.JsonValue;
import com.badlogic.gdx.utils.ObjectMap;

import com.muamn.ashen.entity.BodyDef;

/** Loads the people from {@code assets/data/npcs.json}. */
public class NpcLibrary {

    private final ObjectMap<String, NpcDef> byId = new ObjectMap<>();
    private final Array<NpcDef> npcs = new Array<>();

    public void load() {
        load("data/npcs.json");
    }

    public void load(String path) {
        parse(Gdx.files.internal(path).readString());
        Gdx.app.log("NpcLibrary", "loaded " + npcs.size + " characters");
    }

    /** Parses raw JSON, so the table can be unit tested without a backend. */
    public void parse(String json) {
        JsonValue array = new JsonReader().parse(json).require("npcs");
        for (JsonValue v = array.child; v != null; v = v.next) {
            NpcDef def = parseNpc(v);
            if (byId.containsKey(def.id)) {
                throw new GdxRuntimeException("duplicate npc id: " + def.id);
            }
            byId.put(def.id, def);
            npcs.add(def);
        }
    }

    private NpcDef parseNpc(JsonValue v) {
        NpcDef def = new NpcDef();
        def.id = v.require("id").asString();
        def.nameAr = v.getString("nameAr", def.id);
        def.nameEn = v.getString("nameEn", def.id);
        def.area = v.require("area").asString();
        def.x = v.getFloat("x", 0f);
        def.z = v.getFloat("z", 0f);
        def.facing = v.getFloat("facing", 0f);

        JsonValue body = v.get("body");
        if (body != null) def.body = BodyDef.parse(body);

        JsonValue lines = v.get("lines");
        if (lines != null && lines.isArray()) {
            for (JsonValue l = lines.child; l != null; l = l.next) {
                def.lines.add(new NpcDef.Line(
                        l.getString("ar", ""), l.getString("en", "")));
            }
        }

        JsonValue shop = v.get("shop");
        if (shop != null && shop.isArray()) {
            for (JsonValue o = shop.child; o != null; o = o.next) {
                def.shop.add(new NpcDef.Offer(
                        o.require("item").asString(), o.getLong("price", 100L)));
            }
        }
        return def;
    }

    public NpcDef get(String id) {
        NpcDef def = byId.get(id);
        if (def == null) throw new GdxRuntimeException("unknown npc: " + id);
        return def;
    }

    public boolean has(String id) {
        return byId.containsKey(id);
    }

    public Array<NpcDef> all() {
        return npcs;
    }

    /** Everyone standing in one area. */
    public Array<NpcDef> inArea(String areaId, Array<NpcDef> out) {
        out.clear();
        for (NpcDef def : npcs) {
            if (def.area.equals(areaId)) out.add(def);
        }
        return out;
    }

    public int size() {
        return npcs.size;
    }
}
