package com.muamn.ashen.text;

/**
 * Turns Arabic text into something a left-to-right glyph renderer can draw.
 *
 * libGDX draws a string one code point at a time, left to right, with no
 * shaping. Arabic needs two things that neither the font loader nor the sprite
 * batch will do:
 *
 * <ol>
 *   <li><b>Contextual forms.</b> Every Arabic letter has up to four shapes -
 *       isolated, initial, medial, final - and which one is correct depends on
 *       whether its neighbours join. Unicode keeps the pre-shaped glyphs in the
 *       Arabic Presentation Forms-B block, so choosing the right one is a table
 *       lookup once the joining context is known.</li>
 *   <li><b>Direction.</b> Arabic runs right to left. Since the renderer will
 *       not reverse anything, the string is reversed here - but only the Arabic
 *       runs. Numbers and Latin words embedded in Arabic still read left to
 *       right, so those runs are reversed back.</li>
 * </ol>
 *
 * This is not a full Unicode bidirectional algorithm. It is the subset that
 * covers Arabic prose with numbers and the occasional Latin word in it, which
 * is exactly what this game's text is. Everything here is pure, so all of it is
 * tested without a font, a GL context or a device.
 */
public final class ArabicShaper {

    private ArabicShaper() {}

    /**
     * The joining behaviour of one letter.
     *
     * {@code DUAL} letters join on both sides; {@code RIGHT} letters accept a
     * join from the previous letter but never pass one on, which is why a word
     * containing one breaks into pieces.
     */
    private enum Joining { NONE, RIGHT, DUAL, TRANSPARENT }

    /** isolated, final, initial, medial forms for one base letter. */
    private static final class Forms {
        final char isolated, fina, initial, medial;
        final Joining joining;

        Forms(char isolated, char fina, char initial, char medial, Joining joining) {
            this.isolated = isolated;
            this.fina = fina;
            this.initial = initial;
            this.medial = medial;
            this.joining = joining;
        }
    }

    private static final java.util.HashMap<Character, Forms> TABLE = new java.util.HashMap<>();

    private static void dual(char base, char iso, char fin, char ini, char med) {
        TABLE.put(base, new Forms(iso, fin, ini, med, Joining.DUAL));
    }

    /** A letter that joins to its right only; its initial and medial are its isolated. */
    private static void right(char base, char iso, char fin) {
        TABLE.put(base, new Forms(iso, fin, iso, fin, Joining.RIGHT));
    }

    static {
        // Hamza and the alef family: right-joining, so they cut a word in two.
        right('ء', 'ﺀ', 'ﺀ');              // hamza (never joins at all)
        right('آ', 'ﺁ', 'ﺂ');              // alef madda
        right('أ', 'ﺃ', 'ﺄ');              // alef hamza above
        right('ؤ', 'ﺅ', 'ﺆ');              // waw hamza
        right('إ', 'ﺇ', 'ﺈ');              // alef hamza below
        dual('ئ', 'ﺉ', 'ﺊ', 'ﺋ', 'ﺌ');   // yeh hamza
        right('ا', 'ﺍ', 'ﺎ');              // alef

        dual('ب', 'ﺏ', 'ﺐ', 'ﺑ', 'ﺒ');   // beh
        right('ة', 'ﺓ', 'ﺔ');              // teh marbuta
        dual('ت', 'ﺕ', 'ﺖ', 'ﺗ', 'ﺘ');   // teh
        dual('ث', 'ﺙ', 'ﺚ', 'ﺛ', 'ﺜ');   // theh
        dual('ج', 'ﺝ', 'ﺞ', 'ﺟ', 'ﺠ');   // jeem
        dual('ح', 'ﺡ', 'ﺢ', 'ﺣ', 'ﺤ');   // hah
        dual('خ', 'ﺥ', 'ﺦ', 'ﺧ', 'ﺨ');   // khah
        right('د', 'ﺩ', 'ﺪ');              // dal
        right('ذ', 'ﺫ', 'ﺬ');              // thal
        right('ر', 'ﺭ', 'ﺮ');              // reh
        right('ز', 'ﺯ', 'ﺰ');              // zain
        dual('س', 'ﺱ', 'ﺲ', 'ﺳ', 'ﺴ');   // seen
        dual('ش', 'ﺵ', 'ﺶ', 'ﺷ', 'ﺸ');   // sheen
        dual('ص', 'ﺹ', 'ﺺ', 'ﺻ', 'ﺼ');   // sad
        dual('ض', 'ﺽ', 'ﺾ', 'ﺿ', 'ﻀ');   // dad
        dual('ط', 'ﻁ', 'ﻂ', 'ﻃ', 'ﻄ');   // tah
        dual('ظ', 'ﻅ', 'ﻆ', 'ﻇ', 'ﻈ');   // zah
        dual('ع', 'ﻉ', 'ﻊ', 'ﻋ', 'ﻌ');   // ain
        dual('غ', 'ﻍ', 'ﻎ', 'ﻏ', 'ﻐ');   // ghain
        dual('ف', 'ﻑ', 'ﻒ', 'ﻓ', 'ﻔ');   // feh
        dual('ق', 'ﻕ', 'ﻖ', 'ﻗ', 'ﻘ');   // qaf
        dual('ك', 'ﻙ', 'ﻚ', 'ﻛ', 'ﻜ');   // kaf
        dual('ل', 'ﻝ', 'ﻞ', 'ﻟ', 'ﻠ');   // lam
        dual('م', 'ﻡ', 'ﻢ', 'ﻣ', 'ﻤ');   // meem
        dual('ن', 'ﻥ', 'ﻦ', 'ﻧ', 'ﻨ');   // noon
        dual('ه', 'ﻩ', 'ﻪ', 'ﻫ', 'ﻬ');   // heh
        right('و', 'ﻭ', 'ﻮ');              // waw
        right('ى', 'ﻯ', 'ﻰ');              // alef maksura
        dual('ي', 'ﻱ', 'ﻲ', 'ﻳ', 'ﻴ');   // yeh

        // Persian and Urdu letters that turn up in loan words.
        dual('پ', 'ﭖ', 'ﭗ', 'ﭘ', 'ﭙ');   // peh
        dual('چ', 'ﭺ', 'ﭻ', 'ﭼ', 'ﭽ');   // tcheh
        dual('ڤ', 'ﭪ', 'ﭫ', 'ﭬ', 'ﭭ');   // veh
        dual('گ', 'ﮒ', 'ﮓ', 'ﮔ', 'ﮕ');   // gaf
        right('ژ', 'ﮊ', 'ﮋ');              // jeh
    }

    /**
     * Lam followed by an alef becomes one glyph. It is not optional: the
     * separate letters are simply wrong, and every Arabic reader sees it.
     * Rows are {alef, isolated ligature, final ligature}.
     */
    private static final char[][] LAM_ALEF = {
            {'آ', 'ﻵ', 'ﻶ'},   // lam + alef madda
            {'أ', 'ﻷ', 'ﻸ'},   // lam + alef hamza above
            {'إ', 'ﻹ', 'ﻺ'},   // lam + alef hamza below
            {'ا', 'ﻻ', 'ﻼ'},   // lam + alef
    };

    // ---- public API -------------------------------------------------------

    public static boolean isArabicLetter(char c) {
        return TABLE.containsKey(c);
    }

    /** Marks - fatha, damma, shadda and friends - sit on a letter, not beside it. */
    public static boolean isDiacritic(char c) {
        return (c >= 'ً' && c <= 'ٟ') || c == 'ٰ'
                || (c >= 'ۖ' && c <= 'ۭ');
    }

    /** True if the string contains anything that needs shaping. */
    public static boolean hasArabic(String text) {
        if (text == null) return false;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (isArabicLetter(c) || isDiacritic(c)) return true;
        }
        return false;
    }

    /**
     * Shapes and reorders a string for a left-to-right renderer.
     *
     * Text with no Arabic in it comes back untouched, so this is safe to run
     * over every label in the game whichever language is selected.
     */
    public static String shape(String text) {
        if (!hasArabic(text)) return text;
        return reverseArabicRuns(contextualForms(text));
    }

    // ---- step one: contextual forms ---------------------------------------

    /** Replaces each letter with the presentation form its neighbours call for. */
    static String contextualForms(String text) {
        StringBuilder out = new StringBuilder(text.length());
        int i = 0;
        while (i < text.length()) {
            char c = text.charAt(i);
            Forms forms = TABLE.get(c);
            if (forms == null) {
                // Diacritics are dropped rather than drawn. Positioning a mark
                // over a glyph needs mark-attachment data the bitmap font does
                // not carry, and an unpositioned mark lands in the wrong place -
                // which is worse than a correctly spelled word without it.
                if (!isDiacritic(c)) out.append(c);
                i++;
                continue;
            }

            // Lam-alef, before anything else: the pair becomes one glyph.
            if (c == 'ل' && i + 1 < text.length()) {
                char ligature = lamAlef(text.charAt(nextLetter(text, i)), joinsBackward(text, i));
                if (ligature != 0) {
                    out.append(ligature);
                    i = nextLetter(text, i) + 1;
                    continue;
                }
            }

            boolean before = joinsBackward(text, i);           // previous letter reaches us
            boolean after = joinsForward(text, i, forms);      // we reach the next letter
            if (before && after) out.append(forms.medial);
            else if (before) out.append(forms.fina);
            else if (after) out.append(forms.initial);
            else out.append(forms.isolated);
            i++;
        }
        return out.toString();
    }

    /** Index of the next letter after {@code i}, skipping diacritics. */
    private static int nextLetter(String text, int i) {
        int j = i + 1;
        while (j < text.length() && isDiacritic(text.charAt(j))) j++;
        return j;
    }

    private static char lamAlef(char alef, boolean joinedBefore) {
        for (char[] row : LAM_ALEF) {
            if (row[0] == alef) return joinedBefore ? row[2] : row[1];
        }
        return 0;
    }

    /** True if the letter before this one passes a join along to it. */
    private static boolean joinsBackward(String text, int i) {
        for (int j = i - 1; j >= 0; j--) {
            char c = text.charAt(j);
            if (isDiacritic(c)) continue;
            Forms previous = TABLE.get(c);
            // Only a dual-joining letter reaches forward to the next one.
            return previous != null && previous.joining == Joining.DUAL;
        }
        return false;
    }

    /** True if this letter can reach the next one, and the next one accepts it. */
    private static boolean joinsForward(String text, int i, Forms self) {
        if (self.joining != Joining.DUAL) return false;
        for (int j = i + 1; j < text.length(); j++) {
            char c = text.charAt(j);
            if (isDiacritic(c)) continue;
            // Any Arabic letter accepts a join from its right.
            return TABLE.containsKey(c);
        }
        return false;
    }

    // ---- step two: direction ----------------------------------------------

    /**
     * Reverses the whole string, then un-reverses the runs that are not Arabic.
     *
     * A number inside an Arabic sentence still reads left to right - "5 souls"
     * written backwards as "5" is fine but "125" as "521" is a different number,
     * and that is the kind of bug that survives review because nobody reads the
     * digits.
     */
    static String reverseArabicRuns(String shaped) {
        char[] chars = shaped.toCharArray();
        // Reverse everything.
        for (int a = 0, b = chars.length - 1; a < b; a++, b--) {
            char t = chars[a];
            chars[a] = chars[b];
            chars[b] = t;
        }
        // Then put each left-to-right run back the way round it was.
        int i = 0;
        while (i < chars.length) {
            if (!isLeftToRight(chars[i])) {
                i++;
                continue;
            }
            int start = i;
            while (i < chars.length && isLeftToRight(chars[i])) i++;
            // The spaces on either side belong to the Arabic around the run, not
            // to the run. Dragging them inside moves the gap to the wrong side of
            // the number when the run is reversed back.
            int end = i - 1;
            while (end > start && chars[end] == ' ') end--;
            while (start < end && chars[start] == ' ') start++;
            for (int a = start, b = end; a < b; a++, b--) {
                char t = chars[a];
                chars[a] = chars[b];
                chars[b] = t;
            }
        }
        return new String(chars);
    }

    /**
     * True for characters that keep their own order inside an Arabic sentence:
     * digits, Latin letters, and the spaces and punctuation between them.
     */
    private static boolean isLeftToRight(char c) {
        if (c >= '0' && c <= '9') return true;
        if (c >= 'A' && c <= 'Z') return true;
        if (c >= 'a' && c <= 'z') return true;
        if (c >= 'À' && c <= 'ɏ') return true;   // accented Latin
        return c == '.' || c == ',' || c == ':' || c == '+' || c == '-'
                || c == '/' || c == '%' || c == '\'' || c == ' ';
    }

    /**
     * Mirrors the brackets in a right-to-left string.
     *
     * After reversing, an opening bracket has ended up where a closing one
     * belongs. Nothing else in the punctuation set is directional.
     */
    public static String mirrorBrackets(String text) {
        char[] chars = text.toCharArray();
        for (int i = 0; i < chars.length; i++) {
            switch (chars[i]) {
                case '(': chars[i] = ')'; break;
                case ')': chars[i] = '('; break;
                case '[': chars[i] = ']'; break;
                case ']': chars[i] = '['; break;
                case '{': chars[i] = '}'; break;
                case '}': chars[i] = '{'; break;
                case '<': chars[i] = '>'; break;
                case '>': chars[i] = '<'; break;
                default: break;
            }
        }
        return new String(chars);
    }
}
