package com.muamn.qareeb;

import android.content.res.ColorStateList;
import android.text.format.DateUtils;
import android.view.View;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** Small display helpers shared by the two screens. */
final class Ui {
    private static final int[] AVATAR_COLORS = {
            0xFF00897B, 0xFF5E35B1, 0xFFD81B60, 0xFF3949AB,
            0xFFF4511E, 0xFF6D4C41, 0xFF43A047, 0xFF1E88E5,
    };

    private Ui() {}

    /** A stable colour per friend, so the same person always looks the same. */
    static int colorFor(String key) {
        return AVATAR_COLORS[Math.floorMod(key.hashCode(), AVATAR_COLORS.length)];
    }

    static void tint(View v, int color) {
        v.setBackgroundTintList(ColorStateList.valueOf(color));
    }

    static String initial(String name) {
        if (name == null || name.trim().isEmpty()) return "؟";
        return name.trim().substring(0, name.trim().offsetByCodePoints(0, 1));
    }

    static String time(long t) {
        return new SimpleDateFormat("HH:mm", Locale.getDefault()).format(new Date(t));
    }

    /** The time for today, otherwise the date. */
    static String shortTime(long t) {
        if (DateUtils.isToday(t)) return time(t);
        return new SimpleDateFormat("d/M", Locale.getDefault()).format(new Date(t));
    }
}
