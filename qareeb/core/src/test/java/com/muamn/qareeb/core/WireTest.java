package com.muamn.qareeb.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.List;
import org.junit.jupiter.api.Test;

class WireTest {
    @Test
    void roundTripsAwkwardText() {
        String nasty = "مرحبا\tيا\nأصدقاء \\ back\\slash \\t not-a-tab\r";
        List<String> f = Wire.split(Wire.join("A", nasty, "", "z"));
        assertEquals(List.of("A", nasty, "", "z"), f);
    }

    @Test
    void messageSurvivesStorage() {
        ChatMessage m = ChatMessage.create("me", "محمد", ChatMessage.GROUP, "سطر\nسطر ثاني");
        ChatMessage back = ChatMessage.fromStorageLine(m.toStorageLine());
        assertEquals(m.id, back.id);
        assertEquals(m.text, back.text);
        assertEquals(m.fromName, back.fromName);
        assertEquals(m.time, back.time);
        assertEquals(m.status, back.status);
    }

    @Test
    void announceParsesOnlyOurs() {
        Announce a = Announce.parse(new Announce("abc", "علي", 47800).encode());
        assertEquals("abc", a.id);
        assertEquals("علي", a.name);
        assertEquals(47800, a.port);
        assertNull(Announce.parse("M-SEARCH * HTTP/1.1"));
        assertNull(Announce.parse(Wire.join(Announce.MAGIC, "x", "notaport", "n")));
    }
}
