package com.muamn.qareeb.core;

import java.util.List;
import java.util.UUID;

/** One message, either to the whole group ({@link #GROUP}) or to one friend. */
public final class ChatMessage {
    public static final String GROUP = "*";

    public enum Status { PENDING, DELIVERED, RECEIVED }

    public final String id;
    public final String fromId;
    public final String fromName;
    public final String toId;
    public final String text;
    public final long time;
    public volatile Status status;

    public ChatMessage(String id, String fromId, String fromName, String toId,
                       String text, long time, Status status) {
        this.id = id;
        this.fromId = fromId;
        this.fromName = fromName;
        this.toId = toId;
        this.text = text;
        this.time = time;
        this.status = status;
    }

    public static ChatMessage create(String fromId, String fromName, String toId, String text) {
        return new ChatMessage(UUID.randomUUID().toString(), fromId, fromName, toId, text,
                System.currentTimeMillis(), Status.PENDING);
    }

    public boolean isGroup() {
        return GROUP.equals(toId);
    }

    /** The conversation this message belongs to, seen from {@code myId}. */
    public String conversationFor(String myId) {
        if (isGroup()) return GROUP;
        return fromId.equals(myId) ? toId : fromId;
    }

    /** Fields as they travel on the wire; the status is local and not sent. */
    String[] wireFields() {
        return new String[]{id, fromId, fromName, toId, Long.toString(time), text};
    }

    static ChatMessage fromWire(List<String> f, int start, Status status) {
        if (f.size() < start + 6) throw new IllegalArgumentException("short message");
        return new ChatMessage(f.get(start), f.get(start + 1), f.get(start + 2), f.get(start + 3),
                f.get(start + 5), Long.parseLong(f.get(start + 4)), status);
    }

    /** One line of the history file. */
    public String toStorageLine() {
        String[] w = wireFields();
        String[] all = new String[w.length + 1];
        all[0] = status.name();
        System.arraycopy(w, 0, all, 1, w.length);
        return Wire.join(all);
    }

    public static ChatMessage fromStorageLine(String line) {
        List<String> f = Wire.split(line);
        return fromWire(f, 1, Status.valueOf(f.get(0)));
    }
}
