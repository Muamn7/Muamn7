package com.muamn.ashen.text;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Guards the interface string table.
 *
 * A missing translation is invisible until someone plays that far in that
 * language, and then it is a blank label or an English word in the middle of an
 * Arabic menu. These are the checks that turn that into a build failure.
 */
class StringsTest {

    @AfterEach
    void restoreDefault() {
        Strings.setLanguage(Strings.Language.ARABIC);
    }

    @Test
    void everyKeyHasBothLanguages() {
        for (String key : Strings.keys()) {
            String ar = Strings.get(key, Strings.Language.ARABIC);
            String en = Strings.get(key, Strings.Language.ENGLISH);
            assertFalse(ar.trim().isEmpty(), key + " has no Arabic");
            assertFalse(en.trim().isEmpty(), key + " has no English");
            assertFalse(ar.startsWith("["), key + " is missing from the table");
        }
    }

    @Test
    void arabicAndEnglishAreActuallyDifferent() {
        // A key whose two sides are identical is one somebody forgot to fill in.
        for (String key : Strings.keys()) {
            assertNotEquals(Strings.get(key, Strings.Language.ARABIC),
                    Strings.get(key, Strings.Language.ENGLISH),
                    key + " has the same text in both languages");
        }
    }

    @Test
    void everyArabicStringIsActuallyArabic() {
        for (String key : Strings.keys()) {
            String ar = Strings.get(key, Strings.Language.ARABIC);
            assertTrue(ArabicShaper.hasArabic(ar),
                    key + " is listed as Arabic but reads '" + ar + "'");
        }
    }

    @Test
    void everyArabicStringShapesWithoutLeavingRawLetters() {
        // A letter missing from the shaper's table survives as a raw code point,
        // which the atlas may not carry - an invisible word on a menu.
        for (String key : Strings.keys()) {
            String shaped = ArabicShaper.shape(Strings.get(key, Strings.Language.ARABIC));
            for (int i = 0; i < shaped.length(); i++) {
                char c = shaped.charAt(i);
                if (c == ' ' || c < 0x0600) continue;
                assertTrue(c >= 0xFB50,
                        key + " kept an unshaped letter U+" + Integer.toHexString(c));
            }
        }
    }

    @Test
    void labelsAreShortEnoughForAMenuRow() {
        // The panel is a fixed fraction of the screen; a very long label runs off
        // a phone before anybody sees it on a desktop.
        for (String key : Strings.keys()) {
            for (Strings.Language language : Strings.Language.values()) {
                String value = Strings.get(key, language);
                assertTrue(value.length() <= 40,
                        key + " in " + language + " is " + value.length() + " characters");
            }
        }
    }

    @Test
    void anUnknownKeyIsVisibleRatherThanFatal() {
        // A typo should be found in one playthrough, not crash a boss fight.
        assertEquals("[no_such_key]", Strings.get("no_such_key"));
        assertFalse(Strings.has("no_such_key"));
    }

    @Test
    void theLanguageSwitchesBothWaysAndSticks() {
        Strings.setLanguage(Strings.Language.ARABIC);
        assertTrue(Strings.rtl());
        assertEquals(Strings.Language.ENGLISH, Strings.toggle());
        assertFalse(Strings.rtl());
        assertEquals("Rest", Strings.get(Strings.REST));
        assertEquals(Strings.Language.ARABIC, Strings.toggle());
        assertTrue(Strings.rtl());
    }

    @Test
    void anUnknownLanguageCodeFallsBackToArabic() {
        // The save carries a code; an older or corrupt one must not blank the UI.
        assertEquals(Strings.Language.ARABIC, Strings.Language.of("zz"));
        assertEquals(Strings.Language.ARABIC, Strings.Language.of(""));
        assertEquals(Strings.Language.ENGLISH, Strings.Language.of("en"));
        assertEquals(Strings.Language.ENGLISH, Strings.Language.of("EN"));
    }

    /**
     * The bundled Arabic face has no Latin letters in it - not one. A Latin word
     * inside an Arabic string would be routed to the Arabic font and vanish
     * silently, so the shipped Arabic strings must not contain any.
     */
    @Test
    void noArabicStringSmugglesInALatinWord() {
        for (String key : Strings.keys()) {
            String ar = Strings.get(key, Strings.Language.ARABIC);
            for (int i = 0; i < ar.length(); i++) {
                char c = ar.charAt(i);
                boolean latinLetter = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
                assertFalse(latinLetter,
                        key + " has the Latin letter '" + c + "' in its Arabic text");
            }
        }
    }

    @Test
    void theTableIsNotEmpty() {
        assertTrue(Strings.size() >= 40, "only " + Strings.size() + " strings");
    }

    /**
     * The glyph atlas has to carry every character the interface can produce.
     * Rasterising the whole Arabic block covers the JSON content too, but the
     * table is the part that would fail first and most visibly.
     */
    @Test
    void theAtlasCoversEveryCharacterTheTableUses() {
        String atlas = Text.glyphSet();
        for (String key : Strings.keys()) {
            for (Strings.Language language : Strings.Language.values()) {
                String shaped = ArabicShaper.shape(Strings.get(key, language));
                for (int i = 0; i < shaped.length(); i++) {
                    char c = shaped.charAt(i);
                    assertTrue(atlas.indexOf(c) >= 0,
                            key + " needs U+" + Integer.toHexString(c)
                                    + ", which the atlas does not rasterise");
                }
            }
        }
    }
}
