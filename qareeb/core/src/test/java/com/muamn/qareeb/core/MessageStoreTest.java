package com.muamn.qareeb.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.File;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class MessageStoreTest {
    @TempDir
    Path dir;

    @Test
    void ignoresDuplicates() {
        MessageStore s = new MessageStore(null, "me");
        ChatMessage m = ChatMessage.create("other", "o", ChatMessage.GROUP, "hi");
        assertTrue(s.add(m));
        assertFalse(s.add(m));
        assertEquals(1, s.conversation(ChatMessage.GROUP).size());
    }

    @Test
    void historySurvivesRestart() {
        File f = dir.resolve("history.txt").toFile();
        MessageStore s = new MessageStore(f, "me");
        ChatMessage priv = ChatMessage.create("me", "أنا", "friend", "سر");
        s.add(priv);
        s.add(ChatMessage.create("friend", "صديق", ChatMessage.GROUP, "للجميع"));
        s.markDelivered(priv.id, "friend");
        s.flush();

        MessageStore again = new MessageStore(f, "me");
        List<ChatMessage> conv = again.conversation("friend");
        assertEquals(1, conv.size());
        assertEquals(ChatMessage.Status.DELIVERED, conv.get(0).status);
        assertEquals(1, again.conversation(ChatMessage.GROUP).size());
        assertEquals("صديق", again.lastKnownName("friend"));
    }

    @Test
    void onlyTheRecipientCanAcknowledge() {
        MessageStore s = new MessageStore(null, "me");
        ChatMessage m = ChatMessage.create("me", "me", "bob", "hi");
        s.add(m);
        assertFalse(s.markDelivered(m.id, "mallory"));
        assertEquals(1, s.pendingFor("bob").size());
        assertTrue(s.markDelivered(m.id, "bob"));
        assertTrue(s.pendingFor("bob").isEmpty());
    }

    @Test
    void recentGroupIsOldestFirstAndSkipsPrivate() {
        MessageStore s = new MessageStore(null, "me");
        for (int i = 0; i < 5; i++) {
            s.add(ChatMessage.create("x", "x", ChatMessage.GROUP, "g" + i));
            s.add(ChatMessage.create("x", "x", "me", "p" + i));
        }
        List<ChatMessage> r = s.recentGroup(3);
        assertEquals(List.of("g2", "g3", "g4"), r.stream().map(m -> m.text).toList());
    }
}
