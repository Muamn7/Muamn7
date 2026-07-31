package com.muamn.ashen.save;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.files.FileHandle;
import com.badlogic.gdx.utils.Json;
import com.badlogic.gdx.utils.JsonWriter;

/**
 * Reads and writes the save file.
 *
 * Two rules, both learned from games that get this wrong:
 *
 * A corrupt or unreadable save must never stop the game from starting. If the
 * file cannot be parsed, it is moved aside and a fresh game begins - losing
 * progress is bad, but a game that will not launch is worse, and keeping the bad
 * file means it can still be recovered by hand.
 *
 * Writes go to a temporary file which is then swapped in. A save interrupted
 * halfway - the phone being killed by the OS mid-write is entirely normal -
 * leaves the previous save intact rather than a truncated one.
 */
public class SaveGame {

    private static final String FILE = "ashen-save.json";
    private static final String TEMP = "ashen-save.json.tmp";
    private static final String BROKEN = "ashen-save.json.broken";

    private final Json json = new Json();

    public SaveGame() {
        json.setOutputType(JsonWriter.OutputType.json);
        json.setUsePrototypes(false);
    }

    private FileHandle file(String name) {
        return Gdx.files.local(name);
    }

    public boolean exists() {
        try {
            return file(FILE).exists();
        } catch (Exception e) {
            return false;
        }
    }

    /** @return the stored save, or a fresh one if there is none or it is broken. */
    public SaveData load() {
        try {
            FileHandle handle = file(FILE);
            if (!handle.exists()) return new SaveData();
            SaveData data = json.fromJson(SaveData.class, handle.readString("UTF-8"));
            if (data == null) throw new IllegalStateException("empty save");
            Gdx.app.log("SaveGame", "loaded save: level " + data.level
                    + ", " + data.souls + " souls, " + data.weaponId + " +" + data.weaponUpgrade);
            return data;
        } catch (Exception e) {
            Gdx.app.error("SaveGame", "save unreadable - starting fresh, keeping the file as "
                    + BROKEN, e);
            quarantine();
            return new SaveData();
        }
    }

    /** Writes atomically. Returns false if the save could not be written. */
    public boolean save(SaveData data) {
        try {
            FileHandle temp = file(TEMP);
            temp.writeString(json.prettyPrint(data), false, "UTF-8");
            FileHandle target = file(FILE);
            if (target.exists()) target.delete();
            temp.moveTo(target);
            return true;
        } catch (Exception e) {
            Gdx.app.error("SaveGame", "could not write save", e);
            return false;
        }
    }

    public void delete() {
        try {
            FileHandle handle = file(FILE);
            if (handle.exists()) handle.delete();
        } catch (Exception e) {
            Gdx.app.error("SaveGame", "could not delete save", e);
        }
    }

    private void quarantine() {
        try {
            FileHandle handle = file(FILE);
            if (!handle.exists()) return;
            FileHandle broken = file(BROKEN);
            if (broken.exists()) broken.delete();
            handle.moveTo(broken);
        } catch (Exception ignored) {
            // Best effort: if we cannot even move it aside, a fresh game still starts.
        }
    }
}
