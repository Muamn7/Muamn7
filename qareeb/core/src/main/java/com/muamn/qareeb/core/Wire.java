package com.muamn.qareeb.core;

import java.util.ArrayList;
import java.util.List;

/**
 * The line format shared by the TCP protocol, the UDP announcement and the
 * history file: fields separated by tabs, one record per line. Tabs, newlines
 * and backslashes inside a field are escaped, so a message can carry any text.
 */
public final class Wire {
    private Wire() {}

    public static String join(String... fields) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < fields.length; i++) {
            if (i > 0) sb.append('\t');
            escape(fields[i] == null ? "" : fields[i], sb);
        }
        return sb.toString();
    }

    public static List<String> split(String line) {
        List<String> out = new ArrayList<>();
        StringBuilder cur = new StringBuilder();
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (c == '\t') {
                out.add(cur.toString());
                cur.setLength(0);
            } else if (c == '\\' && i + 1 < line.length()) {
                char n = line.charAt(++i);
                switch (n) {
                    case 't': cur.append('\t'); break;
                    case 'n': cur.append('\n'); break;
                    case 'r': cur.append('\r'); break;
                    default: cur.append(n);
                }
            } else {
                cur.append(c);
            }
        }
        out.add(cur.toString());
        return out;
    }

    private static void escape(String s, StringBuilder sb) {
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '\\': sb.append("\\\\"); break;
                case '\t': sb.append("\\t"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                default: sb.append(c);
            }
        }
    }
}
