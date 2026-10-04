package com.muamn.qareeb.core;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Every message this phone has sent or received, kept in memory and mirrored to
 * a file so the history survives a restart. Writes happen on a background
 * thread, so callers on the UI thread never touch the disk.
 */
public final class MessageStore {
    static final int MAX_MESSAGES = 3000;

    private final File file;
    private final String myId;
    private final List<ChatMessage> messages = new ArrayList<>();
    private final Set<String> ids = new HashSet<>();
    private final ExecutorService writer;
    private boolean writeQueued;

    /** @param file where to keep the history, or null to keep it in memory only. */
    public MessageStore(File file, String myId) {
        this.file = file;
        this.myId = myId;
        this.writer = file == null ? null : Executors.newSingleThreadExecutor(r -> {
            Thread t = new Thread(r, "qareeb-store");
            t.setDaemon(true);
            return t;
        });
        load();
    }

    public String myId() {
        return myId;
    }

    /** Adds a message unless it is already known. Returns true if it was new. */
    public synchronized boolean add(ChatMessage m) {
        if (!ids.add(m.id)) return false;
        // Kept in the order they were written, not the order they arrived: a
        // history sync delivers older messages after newer ones.
        int at = messages.size();
        while (at > 0 && messages.get(at - 1).time > m.time) at--;
        messages.add(at, m);
        while (messages.size() > MAX_MESSAGES) ids.remove(messages.remove(0).id);
        persist();
        return true;
    }

    public synchronized boolean contains(String id) {
        return ids.contains(id);
    }

    /**
     * Marks a private message delivered when {@code byPeer}, its recipient,
     * acknowledges it. A receipt from anyone else is ignored.
     */
    public synchronized boolean markDelivered(String id, String byPeer) {
        for (int i = messages.size() - 1; i >= 0; i--) {
            ChatMessage m = messages.get(i);
            if (m.id.equals(id)) {
                if (m.status != ChatMessage.Status.PENDING || !m.toId.equals(byPeer)) return false;
                m.status = ChatMessage.Status.DELIVERED;
                persist();
                return true;
            }
        }
        return false;
    }

    /** Marks this phone's unsent group messages as sent, after a history sync carried them. */
    public synchronized boolean markGroupSent() {
        boolean changed = false;
        for (ChatMessage m : messages) {
            if (m.isGroup() && m.fromId.equals(myId) && m.status == ChatMessage.Status.PENDING) {
                m.status = ChatMessage.Status.DELIVERED;
                changed = true;
            }
        }
        if (changed) persist();
        return changed;
    }

    public synchronized List<ChatMessage> conversation(String key) {
        List<ChatMessage> out = new ArrayList<>();
        for (ChatMessage m : messages) if (m.conversationFor(myId).equals(key)) out.add(m);
        return out;
    }

    /** Private messages this phone sent to {@code peerId} that have not been acknowledged. */
    public synchronized List<ChatMessage> pendingFor(String peerId) {
        List<ChatMessage> out = new ArrayList<>();
        for (ChatMessage m : messages) {
            if (!m.isGroup() && m.fromId.equals(myId) && m.toId.equals(peerId)
                    && m.status == ChatMessage.Status.PENDING) {
                out.add(m);
            }
        }
        return out;
    }

    /** The last {@code n} group messages, oldest first: what a newcomer is sent to catch up. */
    public synchronized List<ChatMessage> recentGroup(int n) {
        List<ChatMessage> out = new ArrayList<>();
        for (int i = messages.size() - 1; i >= 0 && out.size() < n; i--) {
            if (messages.get(i).isGroup()) out.add(0, messages.get(i));
        }
        return out;
    }

    /** The newest message of every conversation, newest conversation first. */
    public synchronized Map<String, ChatMessage> lastByConversation() {
        Map<String, ChatMessage> last = new LinkedHashMap<>();
        for (int i = messages.size() - 1; i >= 0; i--) {
            ChatMessage m = messages.get(i);
            last.putIfAbsent(m.conversationFor(myId), m);
        }
        return last;
    }

    /** The name a friend used most recently, as remembered from their messages. */
    public synchronized String lastKnownName(String peerId) {
        for (int i = messages.size() - 1; i >= 0; i--) {
            ChatMessage m = messages.get(i);
            if (m.fromId.equals(peerId)) return m.fromName;
        }
        return null;
    }

    public synchronized void clearConversation(String key) {
        // The ids stay in the set, so a friend re-sending the group history does
        // not bring the cleared messages straight back.
        messages.removeIf(m -> m.conversationFor(myId).equals(key));
        persist();
    }

    /** Blocks until pending writes reach the disk. For tests and shutdown. */
    public void flush() {
        if (writer == null) return;
        try {
            writer.submit(() -> { }).get();
        } catch (Exception ignored) {
        }
    }

    private void persist() {
        if (writer == null || writeQueued) return;
        writeQueued = true;
        writer.execute(this::writeNow);
    }

    private void writeNow() {
        List<String> lines;
        synchronized (this) {
            writeQueued = false;
            lines = new ArrayList<>(messages.size());
            for (ChatMessage m : messages) lines.add(m.toStorageLine());
        }
        File tmp = new File(file.getPath() + ".tmp");
        try (BufferedWriter w = new BufferedWriter(new OutputStreamWriter(
                new FileOutputStream(tmp), StandardCharsets.UTF_8))) {
            for (String l : lines) {
                w.write(l);
                w.write('\n');
            }
        } catch (IOException e) {
            return;
        }
        if (!tmp.renameTo(file)) {
            file.delete();
            tmp.renameTo(file);
        }
    }

    private void load() {
        if (file == null || !file.exists()) return;
        try (BufferedReader r = new BufferedReader(new InputStreamReader(
                new FileInputStream(file), StandardCharsets.UTF_8))) {
            String line;
            while ((line = r.readLine()) != null) {
                if (line.isEmpty()) continue;
                try {
                    ChatMessage m = ChatMessage.fromStorageLine(line);
                    if (ids.add(m.id)) messages.add(m);
                } catch (RuntimeException ignored) {
                    // A torn last line from a crash mid-write: skip it.
                }
            }
        } catch (IOException ignored) {
        }
    }
}
