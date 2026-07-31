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
     * Reorders a right-to-left string for a renderer that only draws forwards.
     *
     * A number inside an Arabic sentence still reads left to right - "125"
     * reversed to "521" is a different number, and that is the kind of bug that
     * survives review because nobody reads the digits.
     *
     * The subtlety is punctuation. A colon or a bracket has no direction of its
     * own; it belongs to whatever sits either side of it. So the runs are worked
     * out in logical order, before anything moves: a neutral joins a
     * left-to-right run only when it is enclosed by strong left-to-right
     * characters on both sides. Deciding this after reversing - which is what an
     * earlier version did - orphans the punctuation at the run's edges, and
     * "الأرواح: 0" comes out with the colon on the wrong side of the count.
     */
    static String reverseArabicRuns(String shaped) {
        int n = shaped.length();
        boolean[] ltr = new boolean[n];
        for (int i = 0; i < n; i++) ltr[i] = isStrongLtr(shaped.charAt(i));

        // A neutral belongs to a left-to-right run only if one surrounds it.
        for (int i = 0; i < n; i++) {
            if (ltr[i] || !isNeutral(shaped.charAt(i))) continue;
            int j = i;
            while (j < n && isNeutral(shaped.charAt(j)) && !ltr[j]) j++;
            // At the edges of the string a neutral run has only one neighbour,
            // so it takes that one's direction. That is what keeps the closing
            // bracket of a trailing "(0)" with the number rather than stranding
            // it, mirrored, at the far end of the row.
            boolean strongBefore = i > 0 ? ltr[i - 1] : (j < n && ltr[j]);
            boolean strongAfter = j < n ? ltr[j] : (i > 0 && ltr[i - 1]);
            if (strongBefore && strongAfter) {
                for (int k = i; k < j; k++) ltr[k] = true;
            }
            i = j - 1;
        }

        // Walk backwards, emitting each left-to-right run forwards.
        StringBuilder out = new StringBuilder(n);
        int i = n - 1;
        while (i >= 0) {
            if (!ltr[i]) {
                // Brackets in right-to-left context point the other way.
                out.append(mirrorOf(shaped.charAt(i)));
                i--;
                continue;
            }
            int start = i;
            while (start > 0 && ltr[start - 1]) start--;
            out.append(shaped, start, i + 1);
            i = start - 1;
        }
        return out.toString();
    }

    /** Digits and Latin letters, which carry a direction of their own. */
    private static boolean isStrongLtr(char c) {
        if (c >= '0' && c <= '9') return true;
        if (c >= 'A' && c <= 'Z') return true;
        if (c >= 'a' && c <= 'z') return true;
        return c >= '\u00C0' && c <= '\u024F';   // accented Latin
    }

    /** Punctuation and spaces, which take their direction from their neighbours. */
    private static boolean isNeutral(char c) {
        return c == ' ' || c == '.' || c == ',' || c == ':' || c == ';'
                || c == '+' || c == '-' || c == '/' || c == '%' || c == '\''
                || c == '(' || c == ')' || c == '[' || c == ']' || c == '#'
                || c == '!' || c == '?' || c == '"';
    }

    /**
     * The mirror of a bracket, for one sitting in right-to-left context.
     *
     * Reordering moves an opening bracket to where a closing one belongs, so it
     * has to change shape as well as position. Nothing else in the punctuation
     * set is directional.
     */
    static char mirrorOf(char c) {
        switch (c) {
            case '(': return ')';
            case ')': return '(';
            case '[': return ']';
            case ']': return '[';
            case '{': return '}';
            case '}': return '{';
            case '<': return '>';
            case '>': return '<';
            default:  return c;
        }
    }

    /** Mirrors every bracket in a string. Exposed for tests. */
    public static String mirrorBrackets(String text) {
        char[] chars = text.toCharArray();
        for (int i = 0; i < chars.length; i++) chars[i] = mirrorOf(chars[i]);
        return new String(chars);
    }
}
