package com.muamn.qareeb.core;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * One phone on the local network. No server and no internet: every phone runs
 * a Node, they find each other with UDP broadcasts, and each pair keeps one TCP
 * connection open.
 *
 * <ul>
 *   <li>Group messages are passed on to every other friend this phone is
 *   connected to, so they reach phones that cannot see each other directly.
 *   A newcomer is sent the recent group history and catches up.</li>
 *   <li>Private messages go only to the friend they are for. Until that friend
 *   acknowledges one it stays pending on the sender's phone and is sent again
 *   the next time the two meet.</li>
 * </ul>
 *
 * Listener callbacks arrive on network threads.
 */
public final class Node {
    public static final int DEFAULT_TCP_PORT = 47800;
    public static final int DEFAULT_UDP_PORT = 47801;
    public static final int MAX_TEXT = 4000;

    static final String PROTOCOL = "1";
    static final int HISTORY_SYNC = 200;
    static final long TICK_MS = 2000;
    static final long PEER_TTL_MS = 10_000;
    /** How long the larger id waits for the smaller one to dial before dialling itself. */
    static final long DIAL_GRACE_MS = 6000;
    static final int CONNECT_TIMEOUT_MS = 4000;
    static final int READ_TIMEOUT_MS = 20_000;

    public interface Listener {
        void onMessage(ChatMessage m);

        /** A sent message changed from pending to delivered. */
        void onStatusChanged();

        void onPeersChanged();
    }

    private final String myId;
    private volatile String myName;
    private final int wantedTcpPort;
    private final int udpPort;
    private final MessageStore store;
    private final Listener listener;

    private final ExecutorService pool = Executors.newCachedThreadPool(daemon("qareeb-net"));
    private final ScheduledExecutorService timer =
            Executors.newSingleThreadScheduledExecutor(daemon("qareeb-tick"));
    private final Object linkLock = new Object();
    private final Map<String, Conn> links = new ConcurrentHashMap<>();
    private final Set<Conn> conns = ConcurrentHashMap.newKeySet();
    private final Map<String, PeerInfo> peers = new ConcurrentHashMap<>();
    private final Set<String> dialing = ConcurrentHashMap.newKeySet();
    /** Addresses typed in by hand ("host:port") and the friend found there, "" until known. */
    private final Map<String, String> manual = new ConcurrentHashMap<>();
    private final Set<InetSocketAddress> extraTargets = ConcurrentHashMap.newKeySet();

    private volatile boolean running;
    private ServerSocket server;
    private DatagramSocket udp;

    /**
     * @param tcpPort port to accept friends on, 0 for any free port.
     * @param udpPort port for discovery broadcasts, 0 to turn discovery off.
     */
    public Node(String myId, String myName, int tcpPort, int udpPort,
                MessageStore store, Listener listener) {
        this.myId = myId;
        this.myName = myName;
        this.wantedTcpPort = tcpPort;
        this.udpPort = udpPort;
        this.store = store;
        this.listener = listener;
    }

    // ------------------------------------------------------------------ lifecycle

    public synchronized void start() throws IOException {
        if (running) return;
        server = new ServerSocket();
        server.setReuseAddress(true);
        server.bind(new InetSocketAddress(wantedTcpPort));
        running = true;
        pool.execute(this::acceptLoop);
        if (udpPort > 0) {
            try {
                DatagramSocket s = new DatagramSocket(null);
                s.setReuseAddress(true);
                s.setBroadcast(true);
                s.bind(new InetSocketAddress(udpPort));
                udp = s;
                pool.execute(this::discoveryLoop);
            } catch (SocketException e) {
                // Discovery is a convenience; connecting by address still works.
                udp = null;
            }
        }
        timer.scheduleWithFixedDelay(this::tick, 0, TICK_MS, TimeUnit.MILLISECONDS);
    }

    public synchronized void stop() {
        if (!running) return;
        running = false;
        closeQuietly(server);
        if (udp != null) udp.close();
        for (Conn c : conns) c.close();
        timer.shutdownNow();
        pool.shutdownNow();
    }

    public boolean isRunning() {
        return running;
    }

    public boolean discoveryAvailable() {
        return udp != null;
    }

    public int tcpPort() {
        ServerSocket s = server;
        return s == null ? wantedTcpPort : s.getLocalPort();
    }

    public String id() {
        return myId;
    }

    public String name() {
        return myName;
    }

    // ------------------------------------------------------------------ public API

    public void setName(String name) {
        myName = name;
        String hello = helloLine();
        for (Conn c : links.values()) c.send(hello);
    }

    public ChatMessage sendGroup(String text) {
        ChatMessage m = ChatMessage.create(myId, myName, ChatMessage.GROUP, clip(text));
        // Group messages have no receipts; "sent" means at least one friend got it.
        // One written with nobody around goes out with the history sync later.
        if (!links.isEmpty()) m.status = ChatMessage.Status.DELIVERED;
        store.add(m);
        String line = msgLine(m);
        for (Conn c : links.values()) c.send(line);
        return m;
    }

    public ChatMessage sendPrivate(String peerId, String text) {
        ChatMessage m = ChatMessage.create(myId, myName, peerId, clip(text));
        store.add(m);
        Conn c = links.get(peerId);
        if (c != null) c.send(msgLine(m));
        return m;
    }

    /** Connects to a friend by address, for networks where broadcasts do not get through. */
    public void connectTo(String host, int port) {
        String h = host.trim();
        manual.putIfAbsent(h + ":" + port, "");
        dial(h, port);
    }

    public boolean isConnected(String peerId) {
        return links.containsKey(peerId);
    }

    /** Friends connected now or heard from recently, connected first. */
    public List<Peer> peers() {
        long now = System.currentTimeMillis();
        List<Peer> out = new ArrayList<>();
        for (PeerInfo p : peers.values()) {
            boolean connected = links.containsKey(p.id);
            if (connected || now - p.lastAnnounce < PEER_TTL_MS) {
                out.add(new Peer(p.id, p.name, p.host, p.port, connected));
            }
        }
        out.sort((a, b) -> a.connected != b.connected ? (a.connected ? -1 : 1)
                : String.valueOf(a.name).compareTo(String.valueOf(b.name)));
        return out;
    }

    /** This phone's IPv4 addresses, to show friends who need to connect by hand. */
    public static List<String> localAddresses() {
        List<String> out = new ArrayList<>();
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (a instanceof Inet4Address) out.add(a.getHostAddress());
                }
            }
        } catch (SocketException ignored) {
        }
        return out;
    }

    /** Sends announcements to this address as well. For tests on one machine. */
    void addDiscoveryTarget(InetSocketAddress target) {
        extraTargets.add(target);
    }

    // ------------------------------------------------------------------ periodic work

    private void tick() {
        try {
            if (udp != null) announce();
            long now = System.currentTimeMillis();
            for (Conn c : links.values()) c.send("PING");
            for (PeerInfo p : peers.values()) {
                if (links.containsKey(p.id)) {
                    p.waitingSince = 0;
                    continue;
                }
                if (p.host == null || now - p.lastAnnounce > PEER_TTL_MS) continue;
                if (p.waitingSince == 0) p.waitingSince = now;
                // Only the smaller id dials, so a pair does not open two
                // connections at once. If its broadcasts never reach us (a
                // hotspot often drops them in one direction) we dial anyway.
                if (myId.compareTo(p.id) < 0 || now - p.waitingSince > DIAL_GRACE_MS) {
                    dial(p.host, p.port);
                }
            }
            for (Map.Entry<String, String> e : manual.entrySet()) {
                String id = e.getValue();
                if (!id.isEmpty() && links.containsKey(id)) continue;
                String key = e.getKey();
                int colon = key.lastIndexOf(':');
                dial(key.substring(0, colon), Integer.parseInt(key.substring(colon + 1)));
            }
        } catch (RuntimeException ignored) {
            // Never let one bad round stop the timer.
        }
    }

    private void announce() {
        byte[] data = new Announce(myId, myName, tcpPort()).encode()
                .getBytes(StandardCharsets.UTF_8);
        for (InetSocketAddress target : discoveryTargets()) {
            try {
                udp.send(new DatagramPacket(data, data.length, target));
            } catch (IOException ignored) {
            }
        }
    }

    private Set<InetSocketAddress> discoveryTargets() {
        Set<InetSocketAddress> out = new LinkedHashSet<>(extraTargets);
        try {
            out.add(new InetSocketAddress(InetAddress.getByName("255.255.255.255"), udpPort));
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                // The limited broadcast above is not routed out of every
                // interface (an Android hotspot's in particular), so each
                // subnet's own broadcast address is tried as well.
                for (InterfaceAddress ia : ni.getInterfaceAddresses()) {
                    if (ia.getBroadcast() != null) {
                        out.add(new InetSocketAddress(ia.getBroadcast(), udpPort));
                    }
                }
            }
        } catch (IOException ignored) {
        }
        return out;
    }

    // ------------------------------------------------------------------ sockets

    private void acceptLoop() {
        while (running) {
            try {
                startConn(server.accept(), false, null);
            } catch (IOException e) {
                if (!running) return;
            }
        }
    }

    private void discoveryLoop() {
        byte[] buf = new byte[2048];
        while (running) {
            DatagramPacket pk = new DatagramPacket(buf, buf.length);
            try {
                udp.receive(pk);
            } catch (IOException e) {
                if (!running) return;
                continue;
            }
            Announce a = Announce.parse(
                    new String(pk.getData(), 0, pk.getLength(), StandardCharsets.UTF_8));
            if (a == null || a.id.equals(myId)) continue;
            PeerInfo p = peers.computeIfAbsent(a.id, PeerInfo::new);
            String host = pk.getAddress().getHostAddress();
            boolean changed = !a.name.equals(p.name) || !host.equals(p.host)
                    || System.currentTimeMillis() - p.lastAnnounce > PEER_TTL_MS;
            p.name = a.name;
            p.host = host;
            p.port = a.port;
            p.lastAnnounce = System.currentTimeMillis();
            if (changed) listener.onPeersChanged();
        }
    }

    /**
     * Opens a connection unless one to this address is already being made. The
     * address doubles as the key of a hand-typed entry in {@link #manual}, so
     * the HELLO that comes back can record which friend lives there.
     */
    private void dial(String host, int port) {
        if (!running) return;
        String key = host + ":" + port;
        if (!dialing.add(key)) return;
        pool.execute(() -> {
            Socket s = new Socket();
            try {
                s.connect(new InetSocketAddress(host, port), CONNECT_TIMEOUT_MS);
                startConn(s, true, key);
            } catch (IOException | RuntimeException e) {
                closeQuietly(s);
                dialing.remove(key);
            }
        });
    }

    private void startConn(Socket s, boolean outbound, String dialKey) throws IOException {
        if (!running) {
            s.close();
            return;
        }
        s.setSoTimeout(READ_TIMEOUT_MS);
        s.setTcpNoDelay(true);
        Conn c = new Conn(s, outbound, dialKey);
        conns.add(c);
        c.send(helloLine());
        pool.execute(c::writeLoop);
        pool.execute(c::readLoop);
    }

    // ------------------------------------------------------------------ protocol

    private String helloLine() {
        return Wire.join("HELLO", PROTOCOL, myId, myName, Integer.toString(tcpPort()));
    }

    private static String msgLine(ChatMessage m) {
        String[] w = m.wireFields();
        String[] all = new String[w.length + 1];
        all[0] = "MSG";
        System.arraycopy(w, 0, all, 1, w.length);
        return Wire.join(all);
    }

    private void handle(Conn c, String line) {
        List<String> f = Wire.split(line);
        switch (f.get(0)) {
            case "HELLO":
                onHello(c, f);
                break;
            case "MSG":
                if (c.peerId != null) {
                    onMessage(c, ChatMessage.fromWire(f, 1, ChatMessage.Status.RECEIVED));
                }
                break;
            case "ACK":
                if (c.peerId != null && f.size() > 1 && store.markDelivered(f.get(1), c.peerId)) {
                    listener.onStatusChanged();
                }
                break;
            default:
                // PING, or something from a newer version we do not understand.
        }
    }

    private void onHello(Conn c, List<String> f) {
        if (f.size() < 5) return;
        String id = f.get(2);
        if (id.equals(myId) || id.isEmpty()) {
            // Dialled ourselves through one of our own addresses. If it was
            // typed in by hand, forget it rather than retrying it forever.
            if (c.dialKey != null) manual.remove(c.dialKey);
            c.close();
            return;
        }
        PeerInfo p = peers.computeIfAbsent(id, PeerInfo::new);
        p.name = f.get(3);
        p.host = c.socket.getInetAddress().getHostAddress();
        try {
            p.port = Integer.parseInt(f.get(4));
        } catch (NumberFormatException ignored) {
        }
        if (c.dialKey != null) {
            dialing.remove(c.dialKey);
            manual.replace(c.dialKey, "", id);
        }
        if (c.peerId != null) { // a friend who renamed themselves
            listener.onPeersChanged();
            return;
        }

        synchronized (linkLock) {
            Conn existing = links.get(id);
            if (existing != null && !existing.closed) {
                // Two connections to the same friend. Both phones keep the one
                // the smaller id opened, so they agree on which to drop.
                boolean keepNew = existing.outbound != c.outbound && openedBySmaller(c, id);
                if (!keepNew) {
                    c.close();
                    return;
                }
                c.peerId = id;
                links.put(id, c);
                existing.close();
            } else {
                c.peerId = id;
                links.put(id, c);
            }
        }

        for (ChatMessage m : store.pendingFor(id)) c.send(msgLine(m));
        for (ChatMessage m : store.recentGroup(HISTORY_SYNC)) c.send(msgLine(m));
        boolean sent = store.markGroupSent();
        listener.onPeersChanged();
        if (sent) listener.onStatusChanged();
    }

    private boolean openedBySmaller(Conn c, String peerId) {
        return c.outbound ? myId.compareTo(peerId) < 0 : peerId.compareTo(myId) < 0;
    }

    private void onMessage(Conn from, ChatMessage m) {
        if (m.isGroup()) {
            if (store.add(m)) {
                listener.onMessage(m);
                String line = msgLine(m);
                for (Conn c : links.values()) if (c != from) c.send(line);
            }
        } else if (m.toId.equals(myId) && m.fromId.equals(from.peerId)) {
            if (store.add(m)) listener.onMessage(m);
            // Acknowledge repeats too: our last receipt may have been lost.
            from.send(Wire.join("ACK", m.id));
        }
        // Private messages for someone else are never relayed or kept.
    }

    // ------------------------------------------------------------------ helpers

    private static String clip(String text) {
        String t = text.trim();
        return t.length() > MAX_TEXT ? t.substring(0, MAX_TEXT) : t;
    }

    private static void closeQuietly(java.io.Closeable c) {
        if (c == null) return;
        try {
            c.close();
        } catch (IOException ignored) {
        }
    }

    private static java.util.concurrent.ThreadFactory daemon(String name) {
        return r -> {
            Thread t = new Thread(r, name);
            t.setDaemon(true);
            return t;
        };
    }

    private static final class PeerInfo {
        final String id;
        volatile String name;
        volatile String host;
        volatile int port;
        volatile long lastAnnounce;
        volatile long waitingSince;

        PeerInfo(String id) {
            this.id = id;
        }
    }

    private final class Conn {
        final Socket socket;
        final boolean outbound;
        final String dialKey;
        final BlockingQueue<String> out = new LinkedBlockingQueue<>();
        volatile String peerId;
        volatile boolean closed;

        Conn(Socket socket, boolean outbound, String dialKey) {
            this.socket = socket;
            this.outbound = outbound;
            this.dialKey = dialKey;
        }

        /** Queues a line; the writer thread sends it, so callers never block on the network. */
        void send(String line) {
            if (!closed) out.offer(line);
        }

        void writeLoop() {
            try {
                Writer w = new BufferedWriter(new OutputStreamWriter(
                        socket.getOutputStream(), StandardCharsets.UTF_8));
                while (!closed) {
                    String line = out.poll(1, TimeUnit.SECONDS);
                    if (line == null) continue;
                    w.write(line);
                    w.write('\n');
                    if (out.isEmpty()) w.flush();
                }
            } catch (IOException | InterruptedException ignored) {
            } finally {
                close();
            }
        }

        void readLoop() {
            try {
                BufferedReader r = new BufferedReader(new InputStreamReader(
                        socket.getInputStream(), StandardCharsets.UTF_8));
                String line;
                while (!closed && (line = r.readLine()) != null) {
                    try {
                        handle(this, line);
                    } catch (RuntimeException ignored) {
                        // A malformed line costs that line, not the connection.
                    }
                }
            } catch (IOException ignored) {
                // Includes the read timeout: no PING for a while means the friend left.
            } finally {
                close();
            }
        }

        void close() {
            if (closed) return;
            closed = true;
            closeQuietly(socket);
            conns.remove(this);
            if (dialKey != null) dialing.remove(dialKey);
            if (peerId != null && links.remove(peerId, this)) listener.onPeersChanged();
        }
    }
}
