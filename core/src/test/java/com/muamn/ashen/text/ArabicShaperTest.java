package com.muamn.ashen.text;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The shaper, tested character by character.
 *
 * Arabic rendering fails silently: the words are all there, in the right order,
 * spelled correctly, and simply look wrong to anyone who reads the language.
 * There is no exception and no missing glyph box to notice. So every rule gets
 * an explicit case here, written against known-correct output rather than
 * against whatever the code happens to produce.
 */
class ArabicShaperTest {

    // ---- joining behaviour ------------------------------------------------

    @Test
    void aLoneLetterTakesItsIsolatedForm() {
        assertEquals("ﺏ", ArabicShaper.contextualForms("ب"));
        assertEquals("ﻩ", ArabicShaper.contextualForms("ه"));
    }

    @Test
    void aDualJoiningLetterTakesEachOfItsFourForms() {
        // beh alone, then beh-beh-beh: isolated, then initial + medial + final.
        assertEquals("ﺏ", ArabicShaper.contextualForms("ب"));
        assertEquals("ﺑﺒﺐ", ArabicShaper.contextualForms("ببب"));
    }

    @Test
    void aRightJoiningLetterBreaksTheWord() {
        // Dal accepts a join from the right but passes none on, so the letter
        // after it starts a new shape run. This is the rule most often got wrong.
        String out = ArabicShaper.contextualForms("بدب");
        assertEquals(3, out.length());
        assertEquals('ﺑ', out.charAt(0), "beh should be initial - it reaches dal");
        assertEquals('ﺪ', out.charAt(1), "dal should be final - it was joined to");
        assertEquals('ﺏ', out.charAt(2), "the beh after dal is isolated, not final");
    }

    @Test
    void alefNeverPassesAJoinOn() {
        String out = ArabicShaper.contextualForms("باب");
        assertEquals('ﺑ', out.charAt(0), "beh initial");
        assertEquals('ﺎ', out.charAt(1), "alef final");
        assertEquals('ﺏ', out.charAt(2), "the second beh stands alone");
    }

    @Test
    void aRealWordShapesCorrectly() {
        // "كتاب" (book): kaf initial, teh medial, alef final, beh isolated.
        assertEquals("ﻛﺘﺎﺏ", ArabicShaper.contextualForms("كتاب"));
    }

    @Test
    void wordsAreShapedIndependentlyAcrossASpace() {
        String out = ArabicShaper.contextualForms("بب بب");
        assertEquals('ﺑ', out.charAt(0), "first word: initial");
        assertEquals('ﺐ', out.charAt(1), "first word: final");
        assertEquals(' ', out.charAt(2));
        assertEquals('ﺑ', out.charAt(3), "a space starts a new run");
        assertEquals('ﺐ', out.charAt(4));
    }

    // ---- lam-alef ---------------------------------------------------------

    @Test
    void lamAlefBecomesOneGlyph() {
        assertEquals("ﻻ", ArabicShaper.contextualForms("لا"),
                "lam followed by alef is a single ligature, never two letters");
    }

    @Test
    void lamAlefTakesItsFinalFormWhenJoinedFromTheRight() {
        // beh + lam + alef: the ligature is joined to, so it is the final form.
        String out = ArabicShaper.contextualForms("بلا");
        assertEquals(2, out.length(), "three letters become two glyphs");
        assertEquals('ﺑ', out.charAt(0));
        assertEquals('ﻼ', out.charAt(1));
    }

    @Test
    void eachAlefVariantHasItsOwnLigature() {
        assertEquals("ﻵ", ArabicShaper.contextualForms("لآ"));
        assertEquals("ﻷ", ArabicShaper.contextualForms("لأ"));
        assertEquals("ﻹ", ArabicShaper.contextualForms("لإ"));
        assertEquals("ﻻ", ArabicShaper.contextualForms("لا"));
    }

    @Test
    void lamFollowedBySomethingElseIsStillJustLam() {
        String out = ArabicShaper.contextualForms("لب");
        assertEquals(2, out.length());
        assertEquals('ﻟ', out.charAt(0), "lam initial");
    }

    // ---- diacritics -------------------------------------------------------

    @Test
    void diacriticsAreDroppedRatherThanMisplaced() {
        // A mark the renderer cannot position lands beside the letter instead of
        // over it, which reads as a typo. Dropping it reads as unvocalised text.
        assertEquals(ArabicShaper.contextualForms("كتاب"),
                ArabicShaper.contextualForms("كِتَاب"));
    }

    @Test
    void aDiacriticDoesNotBreakTheJoinAroundIt() {
        // beh + fatha + beh must still shape as initial + final, not as two
        // isolated letters with a hole between them.
        assertEquals("ﺑﺐ", ArabicShaper.contextualForms("بَب"));
    }

    // ---- direction --------------------------------------------------------

    @Test
    void arabicIsReversedForALeftToRightRenderer() {
        // Three distinct Arabic letters come back in the opposite order.
        assertEquals("جبا", ArabicShaper.reverseArabicRuns("ابج"));
    }

    @Test
    void aPurelyLatinStringComesBackUnchanged() {
        // Everything is one left-to-right run, so the reverse cancels itself out.
        assertEquals("abc", ArabicShaper.reverseArabicRuns("abc"));
    }

    @Test
    void numbersKeepTheirOwnOrderInsideArabic() {
        // The whole string flips, but 125 must not become 521.
        String out = ArabicShaper.reverseArabicRuns("ب125ب");
        assertEquals("ب125ب", out);
    }

    @Test
    void aLatinWordInsideArabicStaysReadable() {
        String out = ArabicShaper.reverseArabicRuns("بب Estus بب");
        assertTrue(out.contains("Estus"), "the Latin run came out as: " + out);
    }

    @Test
    void aTrailingSpaceStaysWithTheArabicNotTheNumber() {
        // Reversing " 12" as a run would drag the space inside the number.
        String out = ArabicShaper.reverseArabicRuns("ب 12 ب");
        assertEquals("ب 12 ب", out);
    }

    // ---- the whole pipeline ------------------------------------------------

    @Test
    void latinOnlyTextIsUntouched() {
        // Every label in the game goes through shape(), whichever language is on.
        assertEquals("Reinforce Weapon", ArabicShaper.shape("Reinforce Weapon"));
        assertEquals("Souls: 1250", ArabicShaper.shape("Souls: 1250"));
        assertEquals("", ArabicShaper.shape(""));
    }

    @Test
    void nullIsSafe() {
        assertFalse(ArabicShaper.hasArabic(null));
    }

    @Test
    void shapingChangesArabicAndProducesNoRawLetters() {
        String source = "ساحة المصح";
        String shaped = ArabicShaper.shape(source);
        assertNotEquals(source, shaped);
        for (int i = 0; i < shaped.length(); i++) {
            char c = shaped.charAt(i);
            if (c == ' ') continue;
            assertTrue(c >= 'ﭐ' && c <= '﻿',
                    "an unshaped letter survived: " + Integer.toHexString(c));
        }
    }

    @Test
    void everyLetterInTheGamesOwnTextShapes() {
        // If a letter used in the shipped strings is missing from the table it
        // comes out as a raw code point, which the bitmap font may not carry.
        String everything = "ساحة المصح بلدة الرماد السور المكسور معبد الأعماق"
                + " فارس الرماد الملك الهيكلي مسخ الهاوية"
                + " خبز محروق رماد مهدئ جذر يابس صمغ الجمر عظم العودة"
                + " شظية جمر كتلة جمر قلب جمر قلب الرماد الأول"
                + " حارسة الرماد البائع المتجول حفار القبور حارس السور ناسك الأعماق";
        for (int i = 0; i < everything.length(); i++) {
            char c = everything.charAt(i);
            if (c == ' ') continue;
            assertTrue(ArabicShaper.isArabicLetter(c) || ArabicShaper.isDiacritic(c),
                    "no shape for '" + c + "' (U+" + Integer.toHexString(c) + ")");
        }
    }

    @Test
    void shapingIsIdempotentOnAlreadyShapedText() {
        // Presentation forms are not in the table, so a second pass must not
        // mangle them - the UI can shape the same label twice without noticing.
        String once = ArabicShaper.contextualForms("كتاب");
        assertEquals(once, ArabicShaper.contextualForms(once));
    }

    @Test
    void bracketsAreMirroredForRightToLeft() {
        assertEquals(")x(", ArabicShaper.mirrorBrackets("(x)"));
        assertEquals("][", ArabicShaper.mirrorBrackets("[]"));
        assertEquals("abc", ArabicShaper.mirrorBrackets("abc"));
    }

    @Test
    void hasArabicOnlyFiresOnArabic() {
        assertTrue(ArabicShaper.hasArabic("نار"));
        assertTrue(ArabicShaper.hasArabic("Estus نار"));
        assertFalse(ArabicShaper.hasArabic("Estus Flask"));
        assertFalse(ArabicShaper.hasArabic("12345"));
    }
}
