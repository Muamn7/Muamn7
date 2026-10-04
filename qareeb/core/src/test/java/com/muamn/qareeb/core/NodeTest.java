package com.muamn.qareeb.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.BooleanSupplier;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

/** Real nodes talking over real sockets on localhost. */
class NodeTest {
    private final List<Node> started = new ArrayList<>();

    static final class Phone implements Node.Listener {
        final MessageStore store;
        final Node node;
        final List<ChatMessage> received = new CopyOnWriteArrayList<>();

        Phone(String id, int udpPort) {
            store = new MessageStore(null, id);
            node = new Node(id, "name-" + id, 0, udpPort, store, this);
        }

        @Override public void onMessage(ChatMessage m) { received.add(m); }
        @Override public void onStatusChanged() { }
        @Override public void onPeersChanged() { }

        List<String> texts() {
            return received.stream().map(m -> m.text).toList();
        }
    }

    private Phone phone(String id) throws Exception {
        return phone(id, 0);
    }

    private Phone phone(String id, int udpPort) throws Exception {
        Phone p = new Phone(id, udpPort);
        p.node.start();
        started.add(p.node);
        return p;
    }

    @AfterEach
    void stopAll() {
        for (Node n : started) n.stop();
    }

    private static void link(Phone from, Phone to) {
        from.node.connectTo("127.0.0.1", to.node.tcpPort());
        await(() -> from.node.isConnected(to.node.id()) && to.node.isConnected(from.node.id()));
    }

    private static void await(BooleanSupplier ok) {
        long end = System.currentTimeMillis() + 10_000;
        while (!ok.getAsBoolean()) {
            if (System.currentTimeMillis() > end) throw new AssertionError("timed out");
            try {
                Thread.sleep(20);
            } catch (InterruptedException e) {
                throw new RuntimeException(e);
            }
        }
    }

    @Test
    void groupAndPrivateMessagesArriveWithReceipts() throws Exception {
        Phone a = phone("a"), b = phone("b");
        link(a, b);

        a.node.sendGroup("مرحبا يا شباب");
        ChatMessage priv = a.node.sendPrivate("b", "هذه لك وحدك");

        await(() -> b.received.size() == 2);
        assertEquals(List.of("مرحبا يا شباب", "هذه لك وحدك"), b.texts());
        assertEquals("name-a", b.received.get(0).fromName);
        await(() -> priv.status == ChatMessage.Status.DELIVERED);
    }

    @Test
    void privateMessageWaitsUntilTheFriendShowsUp() throws Exception {
        Phone a = phone("a"), b = phone("b");
        ChatMessage m = a.node.sendPrivate("b", "سأراك لاحقا");
        Thread.sleep(200);
        assertEquals(ChatMessage.Status.PENDING, m.status);

        link(b, a);
        await(() -> b.texts().contains("سأراك لاحقا"));
        await(() -> m.status == ChatMessage.Status.DELIVERED);
        assertEquals(1, b.received.size());
    }

    @Test
    void groupMessagesHopAcrossAFriendButPrivateOnesDoNot() throws Exception {
        Phone a = phone("a"), b = phone("b"), c = phone("c");
        link(a, b);
        link(c, b); // a and c cannot see each other

        a.node.sendGroup("للجميع");
        a.node.sendPrivate("c", "سر");
        await(() -> c.texts().contains("للجميع"));
        Thread.sleep(300);
        assertEquals(List.of("للجميع"), c.texts());
        assertEquals(1, b.received.size());
        assertTrue(b.store.conversation("c").isEmpty(), "b must not keep a's private message");
    }

    @Test
    void newcomerCatchesUpOnTheGroup() throws Exception {
        Phone a = phone("a"), b = phone("b");
        link(a, b);
        a.node.sendGroup("one");
        Thread.sleep(5);
        b.node.sendGroup("two");
        await(() -> a.received.size() == 1 && b.received.size() == 1);

        Phone c = phone("c");
        link(c, b);
        await(() -> c.received.size() == 2);
        assertEquals(List.of("one", "two"), c.texts());
    }

    @Test
    void messageWrittenAloneIsSentWhenSomeoneArrives() throws Exception {
        Phone a = phone("a"), b = phone("b");
        ChatMessage m = a.node.sendGroup("anyone?");
        assertEquals(ChatMessage.Status.PENDING, m.status);
        link(b, a);
        await(() -> b.texts().contains("anyone?"));
        await(() -> m.status == ChatMessage.Status.DELIVERED);
    }

    @Test
    void bothDiallingEachOtherEndsWithOneConnection() throws Exception {
        Phone a = phone("a"), b = phone("b");
        a.node.connectTo("127.0.0.1", b.node.tcpPort());
        b.node.connectTo("127.0.0.1", a.node.tcpPort());
        await(() -> a.node.isConnected("b") && b.node.isConnected("a"));
        Thread.sleep(500);

        a.node.sendGroup("once");
        await(() -> b.received.size() == 1);
        Thread.sleep(300);
        assertEquals(1, b.received.size());
    }

    @Test
    void friendsFindEachOtherWithoutTypingAnything() throws Exception {
        int ua = freeUdpPort(), ub = freeUdpPort();
        Phone a = phone("a", ua), b = phone("b", ub);
        // Loopback has no broadcast address, so point each at the other directly.
        a.node.addDiscoveryTarget(new InetSocketAddress("127.0.0.1", ub));
        b.node.addDiscoveryTarget(new InetSocketAddress("127.0.0.1", ua));

        await(() -> a.node.isConnected("b") && b.node.isConnected("a"));
        assertEquals("name-b", a.node.peers().get(0).name);
    }

    @Test
    void renameReachesFriends() throws Exception {
        Phone a = phone("a"), b = phone("b");
        link(a, b);
        a.node.setName("أبو علي");
        await(() -> !b.node.peers().isEmpty() && "أبو علي".equals(b.node.peers().get(0).name));
    }

    @Test
    void dialMyselfIsHarmless() throws Exception {
        Phone a = phone("a");
        a.node.connectTo("127.0.0.1", a.node.tcpPort());
        Thread.sleep(500);
        assertTrue(a.node.peers().isEmpty());
    }

    private static int freeUdpPort() throws Exception {
        try (DatagramSocket s = new DatagramSocket(0)) {
            return s.getLocalPort();
        }
    }
}
