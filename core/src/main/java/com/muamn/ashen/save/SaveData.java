package com.muamn.ashen.save;

/**
 * Everything a save file holds.
 *
 * A plain data class with public fields, on purpose: it is the file format, and
 * keeping it dumb means the serialiser never has to guess. Adding a field with a
 * sensible default is backward compatible, because a missing key in an older
 * save just leaves the default in place.
 */
public class SaveData {

    /** Bumped when a change cannot be handled by defaults alone. */
    public int version = 1;

    // ---- attributes ----
    public int level = 1;
    public int vigor = 10;
    public int endurance = 10;
    public int strength = 10;
    public int dexterity = 10;
    public int intelligence = 9;
    public int faith = 9;

    // ---- progression ----
    public long souls;
    public int estusMax = 5;
    public int deaths;
    /** Seconds of play. */
    public float playTime;

    // ---- equipment ----
    public String weaponId = "longsword";
    public int weaponUpgrade;

    // ---- items ----
    /**
     * The inventory, as {@code id:count,id:count}. A string rather than a map
     * because this file is read by a schema-less parser and a flat field is the
     * one shape that survives the item table changing under it.
     */
    public String inventory = "";
    /** Item the use button spends. Empty means the Estus flask. */
    public String quickItem = "";
    /**
     * Ids of placed treasures taken and illusory walls opened, comma-separated.
     * One field for both because they are the same kind of fact: something that
     * happens once and must not come back when the area is rebuilt.
     */
    public String found = "";

    // ---- world ----
    /** Area the player is standing in. */
    public String areaId = "asylum_courtyard";
    /** Area whose bonfire the player last rested at, and respawns to. */
    public String bonfireArea = "asylum_courtyard";
    public String bonfireId = "asylum_courtyard";
    public float bonfireX;
    public float bonfireY;
    public float bonfireZ = -6f;

    /** Souls dropped where you last died, if they have not been recovered. */
    public boolean hasBloodstain;
    public long bloodstainSouls;
    public float bloodstainX;
    public float bloodstainY;
    public float bloodstainZ;
}
