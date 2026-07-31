package com.muamn.ashen.text;

import com.badlogic.gdx.utils.ObjectMap;

/**
 * Every word the interface says, in both languages.
 *
 * A table in code rather than another JSON file. The keys are compile-time
 * constants used from exactly one place each, so a typo is a missing string at
 * build time rather than a blank label at run time - and there is a test that
 * walks the table and fails if either language is missing an entry.
 *
 * Item, enemy and area names are not here. Those already carry {@code nameAr}
 * and {@code nameEn} in their own JSON, next to the numbers they belong with,
 * and copying them into a second table would only create two places to forget.
 */
public final class Strings {

    public enum Language {
        ARABIC("ar", "العربية", true),
        ENGLISH("en", "English", false);

        public final String code;
        public final String ownName;
        /** True for a language that reads right to left. */
        public final boolean rtl;

        Language(String code, String ownName, boolean rtl) {
            this.code = code;
            this.ownName = ownName;
            this.rtl = rtl;
        }

        public static Language of(String code) {
            for (Language language : values()) {
                if (language.code.equalsIgnoreCase(code)) return language;
            }
            return ARABIC;
        }
    }

    /** Arabic by default: it is the language this game was asked for. */
    private static Language current = Language.ARABIC;

    private Strings() {}

    public static Language language() {
        return current;
    }

    public static void setLanguage(Language language) {
        current = language == null ? Language.ARABIC : language;
    }

    public static boolean rtl() {
        return current.rtl;
    }

    /** Switches to the other language and returns the new one. */
    public static Language toggle() {
        current = current == Language.ARABIC ? Language.ENGLISH : Language.ARABIC;
        return current;
    }

    // ---- keys -------------------------------------------------------------

    public static final String BONFIRE = "bonfire";
    public static final String REST = "rest";
    public static final String LEVEL_UP = "level_up";
    public static final String REINFORCE = "reinforce";
    public static final String ITEMS = "items";
    public static final String LEAVE = "leave";
    public static final String BACK = "back";

    public static final String VIGOR = "vigor";
    public static final String ENDURANCE = "endurance";
    public static final String STRENGTH = "strength";
    public static final String DEXTERITY = "dexterity";
    public static final String INTELLIGENCE = "intelligence";
    public static final String FAITH = "faith";

    public static final String SOULS = "souls";
    public static final String LEVEL = "level";
    public static final String NEXT_COSTS = "next_costs";
    public static final String NOT_ENOUGH_SOULS = "not_enough_souls";
    public static final String NEED_MATERIAL = "need_material";
    public static final String FULLY_REINFORCED = "fully_reinforced";
    public static final String TO_PLUS = "to_plus";
    public static final String CARRYING_NOTHING = "carrying_nothing";
    public static final String CARRYING_TOO_MANY = "carrying_too_many";
    public static final String READY = "ready";
    public static final String RESTED = "rested";
    public static final String PICK_QUICK_ITEM = "pick_quick_item";

    public static final String ESTUS = "estus";
    public static final String BUFF = "buff";
    public static final String YOU_DIED = "you_died";
    public static final String GREAT_SOUL = "great_soul";
    public static final String RECOVERED = "recovered";
    public static final String PHASE = "phase";
    public static final String TALK_TO = "talk_to";
    public static final String TRADE = "trade";
    public static final String NOT_HERE = "not_here";
    public static final String HOMEWARD = "homeward";
    public static final String WALL_REVEALED = "wall_revealed";
    public static final String CONTINUE = "continue";

    public static final String SHARD = "shard";
    public static final String LUMP = "lump";
    public static final String CORE = "core";
    public static final String HEART = "heart";

    // ---- the table --------------------------------------------------------

    private static final ObjectMap<String, String[]> TABLE = new ObjectMap<>();

    /** {@code put(key, arabic, english)}. */
    private static void put(String key, String ar, String en) {
        TABLE.put(key, new String[]{ar, en});
    }

    static {
        put(BONFIRE, "نار المخيّم", "BONFIRE");
        put(REST, "استرح", "Rest");
        put(LEVEL_UP, "ارفع المستوى", "Level Up");
        put(REINFORCE, "قوِّ السلاح", "Reinforce Weapon");
        put(ITEMS, "العناصر", "Items");
        put(LEAVE, "غادر", "Leave");
        put(BACK, "رجوع", "Back");

        put(VIGOR, "الحيوية", "Vigor");
        put(ENDURANCE, "التحمّل", "Endurance");
        put(STRENGTH, "القوة", "Strength");
        put(DEXTERITY, "الرشاقة", "Dexterity");
        put(INTELLIGENCE, "الذكاء", "Intelligence");
        put(FAITH, "الإيمان", "Faith");

        put(SOULS, "الأرواح", "Souls");
        put(LEVEL, "المستوى", "Level");
        put(NEXT_COSTS, "التالي يكلّف", "next costs");
        put(NOT_ENOUGH_SOULS, "أرواح غير كافية", "Not enough souls");
        put(NEED_MATERIAL, "تحتاج", "Need");
        put(FULLY_REINFORCED, "بلغ أقصاه", "Fully reinforced");
        put(TO_PLUS, "إلى", "To");
        put(CARRYING_NOTHING, "لا تحمل شيئًا", "Carrying nothing");
        put(CARRYING_TOO_MANY, "تحمل الكثير", "Carrying too many");
        put(READY, "جاهز", "ready");
        put(RESTED, "استرحت", "Rested");
        put(PICK_QUICK_ITEM, "اختر عنصرًا للخانة السريعة", "pick one for the quick slot");

        put(ESTUS, "القارورة", "Estus");
        put(BUFF, "طلاء", "BUFF");
        put(YOU_DIED, "لقد متّ", "YOU DIED");
        put(GREAT_SOUL, "تحرّرت روح عظيمة", "GREAT SOUL RELEASED");
        put(RECOVERED, "استعدت", "Recovered");
        put(PHASE, "الطور", "PHASE");
        put(TALK_TO, "تحدّث إلى", "Talk to");
        put(TRADE, "تاجر", "trade");
        put(NOT_HERE, "ليس هنا", "Not here");
        put(HOMEWARD, "عودة", "Homeward");
        put(WALL_REVEALED, "لم يكن الجدار هناك", "The wall was not there");
        put(CONTINUE, "تابع", "continue");

        put(SHARD, "شظية", "Shard");
        put(LUMP, "كتلة", "Lump");
        put(CORE, "قلب", "Core");
        put(HEART, "قلب الرماد", "Heart");
    }

    /**
     * The string for a key in the current language.
     *
     * An unknown key comes back as the key itself in brackets rather than as
     * null or an exception - a label reading {@code [reinfroce]} on screen is
     * found in one playthrough, and a crash in the middle of a boss fight is not
     * a reasonable price for a typo.
     */
    public static String get(String key) {
        String[] entry = TABLE.get(key);
        if (entry == null) return "[" + key + "]";
        return entry[current == Language.ARABIC ? 0 : 1];
    }

    /** The string for a key in a named language, for tests and for the options row. */
    public static String get(String key, Language language) {
        String[] entry = TABLE.get(key);
        if (entry == null) return "[" + key + "]";
        return entry[language == Language.ARABIC ? 0 : 1];
    }

    public static boolean has(String key) {
        return TABLE.containsKey(key);
    }

    /** Every key in the table. Used by the test that checks both languages. */
    public static Iterable<String> keys() {
        return TABLE.keys().toArray();
    }

    public static int size() {
        return TABLE.size;
    }
}
