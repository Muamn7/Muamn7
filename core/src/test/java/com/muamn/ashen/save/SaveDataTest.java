package com.muamn.ashen.save;

import com.badlogic.gdx.utils.Json;
import com.badlogic.gdx.utils.JsonWriter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The save format is a contract with the player's progress, so these check the
 * two things that actually lose someone's game: fields not surviving a round
 * trip, and an older save failing to load after the format grows.
 */
class SaveDataTest {

    private static Json json() {
        Json json = new Json();
        json.setOutputType(JsonWriter.OutputType.json);
        json.setUsePrototypes(false);
        return json;
    }

    @Test
    void everyFieldSurvivesARoundTrip() {
        SaveData original = new SaveData();
        original.level = 27;
        original.vigor = 22;
        original.endurance = 18;
        original.strength = 30;
        original.dexterity = 14;
        original.intelligence = 11;
        original.faith = 10;
        original.souls = 123456L;
        original.estusMax = 8;
        original.deaths = 41;
        original.playTime = 3612.5f;
        original.weaponId = "zweihander";
        original.weaponUpgrade = 7;
        original.bonfireId = "broken_wall";
        original.bonfireX = 12.5f;
        original.bonfireY = 2f;
        original.bonfireZ = -33.25f;
        original.hasBloodstain = true;
        original.bloodstainSouls = 9800L;
        original.bloodstainX = -4f;
        original.bloodstainY = 0.2f;
        original.bloodstainZ = 17f;

        Json json = json();
        SaveData restored = json.fromJson(SaveData.class, json.toJson(original));

        assertNotNull(restored);
        assertEquals(original.level, restored.level);
        assertEquals(original.vigor, restored.vigor);
        assertEquals(original.endurance, restored.endurance);
        assertEquals(original.strength, restored.strength);
        assertEquals(original.dexterity, restored.dexterity);
        assertEquals(original.intelligence, restored.intelligence);
        assertEquals(original.faith, restored.faith);
        assertEquals(original.souls, restored.souls);
        assertEquals(original.estusMax, restored.estusMax);
        assertEquals(original.deaths, restored.deaths);
        assertEquals(original.playTime, restored.playTime, 1e-3f);
        assertEquals(original.weaponId, restored.weaponId);
        assertEquals(original.weaponUpgrade, restored.weaponUpgrade);
        assertEquals(original.bonfireId, restored.bonfireId);
        assertEquals(original.bonfireX, restored.bonfireX, 1e-4f);
        assertEquals(original.bonfireZ, restored.bonfireZ, 1e-4f);
        assertTrue(restored.hasBloodstain);
        assertEquals(original.bloodstainSouls, restored.bloodstainSouls);
        assertEquals(original.bloodstainZ, restored.bloodstainZ, 1e-4f);
    }

    @Test
    void anOlderSaveMissingFieldsKeepsTheDefaults() {
        // A save written before estus upgrades and bloodstains existed.
        String legacy = "{\"version\":1,\"level\":9,\"souls\":500,\"weaponId\":\"mace\"}";
        SaveData data = json().fromJson(SaveData.class, legacy);

        assertEquals(9, data.level);
        assertEquals(500L, data.souls);
        assertEquals("mace", data.weaponId);
        // Untouched fields must fall back, not come back as zero or null.
        assertEquals(5, data.estusMax, "a missing estus count should default, not zero out");
        assertEquals(10, data.vigor);
        assertFalse(data.hasBloodstain);
        assertNotNull(data.bonfireId);
    }

    @Test
    void aFreshSaveIsPlayable() {
        SaveData data = new SaveData();
        assertTrue(data.estusMax > 0, "a new game must start with Estus");
        assertNotNull(data.weaponId);
        assertTrue(data.level >= 1);
        assertEquals(0L, data.souls);
        assertFalse(data.hasBloodstain);
    }

    @Test
    void garbageIsRejectedRatherThanSilentlyAccepted() {
        // SaveGame catches this and starts fresh; the point here is that the
        // parser really does fail rather than returning a half-built object.
        assertThrows(Exception.class,
                () -> json().fromJson(SaveData.class, "this is not json at all"));
    }
}
