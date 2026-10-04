package com.muamn.qareeb.core;

import java.util.List;

/** The UDP broadcast a phone sends every few seconds so the others can find it. */
public final class Announce {
    static final String MAGIC = "QAREEB1";

    public final String id;
    public final String name;
    public final int port;

    public Announce(String id, String name, int port) {
        this.id = id;
        this.name = name;
        this.port = port;
    }

    public String encode() {
        return Wire.join(MAGIC, id, Integer.toString(port), name);
    }

    /** Returns null for anything that is not one of ours. */
    public static Announce parse(String s) {
        List<String> f = Wire.split(s);
        if (f.size() < 4 || !MAGIC.equals(f.get(0))) return null;
        try {
            return new Announce(f.get(1), f.get(3), Integer.parseInt(f.get(2)));
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
