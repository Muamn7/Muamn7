package com.muamn.ashen.item;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.GdxRuntimeException;
import com.badlogic.gdx.utils.JsonReader;
import com.badlogic.gdx.utils.JsonValue;
import com.badlogic.gdx.utils.ObjectMap;

/** Loads the item table from JSON. */
public class ItemLibrary {

    private final ObjectMap<String, ItemDef> byId = new ObjectMap<>();
    private final Array<ItemDef> items = new Array<>();

    public void load() {
        load("data/items.json");
    }

    public void load(String path) {
        parse(Gdx.files.internal(path).readString());
        Gdx.app.log("ItemLibrary", "loaded " + items.size + " items");
    }

    /** Parses raw JSON, so the table can be unit tested without a backend. */
    public void parse(String json) {
        JsonValue array = new JsonReader().parse(json).require("items");
        for (JsonValue v = array.child; v != null; v = v.next) {
            ItemDef def = parseItem(v);
            if (byId.containsKey(def.id)) {
                throw new GdxRuntimeException("duplicate item id: " + def.id);
            }
            byId.put(def.id, def);
            items.add(def);
        }
    }

    private ItemDef parseItem(JsonValue v) {
        ItemDef def = new ItemDef();
        def.id = v.require("id").asString();
        def.nameAr = v.getString("nameAr", def.id);
        def.nameEn = v.getString("nameEn", def.id);
        def.descAr = v.getString("descAr", "");
        def.descEn = v.getString("descEn", "");
        def.kind = ItemDef.Kind.valueOf(v.getString("kind", "CONSUMABLE"));
        def.effect = ItemDef.Effect.valueOf(v.getString("effect", "NONE"));
        def.power = v.getFloat("power", 0f);
        def.duration = v.getFloat("duration", 0f);
        def.maxStack = v.getInt("maxStack", def.maxStack);
        def.glow = v.getString("glow", def.glow);
        return def;
    }

    public ItemDef get(String id) {
        ItemDef def = byId.get(id);
        if (def == null) throw new GdxRuntimeException("unknown item: " + id);
        return def;
    }

    public boolean has(String id) {
        return byId.containsKey(id);
    }

    /** Every item, in file order. */
    public Array<ItemDef> all() {
        return items;
    }

    public int size() {
        return items.size;
    }
}
