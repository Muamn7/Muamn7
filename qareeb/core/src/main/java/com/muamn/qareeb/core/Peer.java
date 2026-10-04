package com.muamn.qareeb.core;

/** A friend's phone, as last seen on the network. Immutable snapshot. */
public final class Peer {
    public final String id;
    public final String name;
    public final String host;
    public final int port;
    public final boolean connected;

    public Peer(String id, String name, String host, int port, boolean connected) {
        this.id = id;
        this.name = name;
        this.host = host;
        this.port = port;
        this.connected = connected;
    }
}
