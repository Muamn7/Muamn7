package com.muamn.qareeb;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;

import com.muamn.qareeb.core.ChatMessage;
import com.muamn.qareeb.core.MessageStore;
import com.muamn.qareeb.core.Node;
import com.muamn.qareeb.core.Peer;

import java.io.File;
import java.io.IOException;
import java.net.BindException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArraySet;

/**
 * The app's one connection to the network and the history, shared by the
 * service and the screens. Node callbacks arrive on network threads; listeners
 * here are always called on the main thread.
 */
public final class Hub implements Node.Listener {
    public interface Listener {
        void onHubChanged();
    }

    /** One row of the conversation list. */
    public static final class Conversation {
        public final String key;
        public final String title;
        public final ChatMessage last;
        public final boolean online;
        public final int unread;

        Conversation(String key, String title, ChatMessage last, boolean online, int unread) {
            this.key = key;
            this.title = title;
            this.last = last;
            this.online = online;
            this.unread = unread;
        }
    }

    static final String CHANNEL_STATUS = "status";
    static final String CHANNEL_MESSAGES = "messages";

    private static Hub instance;

    private final Context ctx;
    private final SharedPreferences prefs;
    private final String myId;
    private final MessageStore store;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final CopyOnWriteArraySet<Listener> listeners = new CopyOnWriteArraySet<>();
    private final Map<String, Integer> unread = new ConcurrentHashMap<>();
    private volatile Node node;
    private volatile String openConversation;
    private boolean changePosted;

    public static synchronized Hub get(Context c) {
        if (instance == null) instance = new Hub(c.getApplicationContext());
        return instance;
    }

    private Hub(Context ctx) {
        this.ctx = ctx;
        prefs = ctx.getSharedPreferences("qareeb", Context.MODE_PRIVATE);
        String id = prefs.getString("id", null);
        if (id == null) {
            id = UUID.randomUUID().toString().replace("-", "").substring(0, 16);
            prefs.edit().putString("id", id).apply();
        }
        myId = id;
        store = new MessageStore(new File(ctx.getFilesDir(), "messages.txt"), myId);
        createChannels();
    }

    // ------------------------------------------------------------------ identity

    public String myId() {
        return myId;
    }

    public String myName() {
        return prefs.getString("name", "");
    }

    public boolean hasName() {
        return !myName().isEmpty();
    }

    public void setName(String name) {
        prefs.edit().putString("name", name).apply();
        Node n = node;
        if (n != null) n.setName(name);
        fireChanged();
    }

    // ------------------------------------------------------------------ lifecycle

    public synchronized void start() {
        if (node != null) return;
        Node n = new Node(myId, myName(), Node.DEFAULT_TCP_PORT, Node.DEFAULT_UDP_PORT, store, this);
        node = n;
        new Thread(() -> {
            try {
                n.start();
            } catch (BindException e) {
                // The usual port is taken (an old copy still shutting down?).
                // Any port works for discovery; only typing an address needs the usual one.
                Node any = new Node(myId, myName(), 0, Node.DEFAULT_UDP_PORT, store, this);
                try {
                    any.start();
                    node = any;
                } catch (IOException ignored) {
                }
            } catch (IOException ignored) {
            }
            fireChanged();
        }, "qareeb-start").start();
    }

    public synchronized void stop() {
        Node n = node;
        node = null;
        if (n != null) new Thread(n::stop, "qareeb-stop").start();
        store.flush();
        fireChanged();
    }

    public boolean isRunning() {
        Node n = node;
        return n != null && n.isRunning();
    }

    // ------------------------------------------------------------------ messaging

    public void send(String conversation, String text) {
        Node n = node;
        if (n == null || text.trim().isEmpty()) return;
        if (ChatMessage.GROUP.equals(conversation)) n.sendGroup(text);
        else n.sendPrivate(conversation, text);
        fireChanged();
    }

    public void connectTo(String host) {
        Node n = node;
        if (n != null) n.connectTo(host, Node.DEFAULT_TCP_PORT);
    }

    public List<ChatMessage> messages(String conversation) {
        return store.conversation(conversation);
    }

    public void clear(String conversation) {
        store.clearConversation(conversation);
        unread.remove(conversation);
        fireChanged();
    }

    /** The chat on screen right now; its messages are not counted as unread or notified. */
    public void setOpenConversation(String key) {
        openConversation = key;
        if (key != null) {
            unread.remove(key);
            ctx.getSystemService(NotificationManager.class).cancel(key.hashCode());
            fireChanged();
        }
    }

    // ------------------------------------------------------------------ queries

    public List<Peer> peers() {
        Node n = node;
        return n == null ? new ArrayList<>() : n.peers();
    }

    public int connectedCount() {
        int c = 0;
        for (Peer p : peers()) if (p.connected) c++;
        return c;
    }

    public boolean isOnline(String peerId) {
        Node n = node;
        return n != null && n.isConnected(peerId);
    }

    public String displayName(String key) {
        if (ChatMessage.GROUP.equals(key)) return ctx.getString(R.string.group);
        for (Peer p : peers()) if (p.id.equals(key) && p.name != null) return p.name;
        String known = store.lastKnownName(key);
        return known != null ? known : ctx.getString(R.string.friend);
    }

    /** The group first, then friends nearby, then everyone else you have talked to. */
    public List<Conversation> conversations() {
        Map<String, ChatMessage> last = store.lastByConversation();
        List<Conversation> out = new ArrayList<>();
        out.add(new Conversation(ChatMessage.GROUP, ctx.getString(R.string.group),
                last.get(ChatMessage.GROUP), connectedCount() > 0,
                unreadFor(ChatMessage.GROUP)));
        List<String> seen = new ArrayList<>();
        for (Peer p : peers()) {
            seen.add(p.id);
            out.add(new Conversation(p.id, p.name, last.get(p.id), p.connected, unreadFor(p.id)));
        }
        for (Map.Entry<String, ChatMessage> e : last.entrySet()) {
            String key = e.getKey();
            if (ChatMessage.GROUP.equals(key) || seen.contains(key)) continue;
            out.add(new Conversation(key, displayName(key), e.getValue(), false, unreadFor(key)));
        }
        return out;
    }

    private int unreadFor(String key) {
        Integer n = unread.get(key);
        return n == null ? 0 : n;
    }

    public List<String> addresses() {
        return Node.localAddresses();
    }

    // ------------------------------------------------------------------ listeners

    public void addListener(Listener l) {
        listeners.add(l);
    }

    public void removeListener(Listener l) {
        listeners.remove(l);
    }

    /** Coalesces a burst of changes (a history sync is hundreds) into one redraw. */
    private void fireChanged() {
        synchronized (this) {
            if (changePosted) return;
            changePosted = true;
        }
        main.postDelayed(() -> {
            synchronized (this) {
                changePosted = false;
            }
            for (Listener l : listeners) l.onHubChanged();
        }, 50);
    }

    @Override
    public void onMessage(ChatMessage m) {
        String key = m.conversationFor(myId);
        if (!key.equals(openConversation)) {
            unread.merge(key, 1, Integer::sum);
            notifyMessage(key, m);
        }
        fireChanged();
    }

    @Override
    public void onStatusChanged() {
        fireChanged();
    }

    @Override
    public void onPeersChanged() {
        fireChanged();
    }

    // ------------------------------------------------------------------ notifications

    private void createChannels() {
        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL_STATUS,
                ctx.getString(R.string.channel_status), NotificationManager.IMPORTANCE_MIN));
        nm.createNotificationChannel(new NotificationChannel(CHANNEL_MESSAGES,
                ctx.getString(R.string.channel_messages), NotificationManager.IMPORTANCE_HIGH));
    }

    private void notifyMessage(String key, ChatMessage m) {
        Intent open = new Intent(ctx, ChatActivity.class)
                .putExtra(ChatActivity.EXTRA_KEY, key)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent pi = PendingIntent.getActivity(ctx, key.hashCode(), open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String title = m.isGroup() ? ctx.getString(R.string.group) + " · " + m.fromName : m.fromName;
        int count = unreadFor(key);
        Notification n = new Notification.Builder(ctx, CHANNEL_MESSAGES)
                .setSmallIcon(R.drawable.ic_send)
                .setContentTitle(title)
                .setContentText(m.text)
                .setStyle(new Notification.BigTextStyle().bigText(m.text))
                .setNumber(count)
                .setContentIntent(pi)
                .setAutoCancel(true)
                .build();
        try {
            ctx.getSystemService(NotificationManager.class).notify(key.hashCode(), n);
        } catch (SecurityException ignored) {
            // Notification permission refused: the unread badge still shows it.
        }
    }
}
