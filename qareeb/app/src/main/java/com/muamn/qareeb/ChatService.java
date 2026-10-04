package com.muamn.qareeb;

import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.drawable.Icon;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.IBinder;

/**
 * Keeps the app alive with the screen off, so messages arrive while the phone is
 * in a pocket. Holds the Wi-Fi awake and a multicast lock, without which many
 * phones silently drop the discovery broadcasts.
 */
public final class ChatService extends Service implements Hub.Listener {
    private static final int NOTIFICATION_ID = 0x51A2EEB;
    private static final String ACTION_STOP = "com.muamn.qareeb.STOP";

    private Hub hub;
    private WifiManager.MulticastLock multicastLock;
    private WifiManager.WifiLock wifiLock;

    public static void start(Context c) {
        c.startForegroundService(new Intent(c, ChatService.class));
    }

    public static void stop(Context c) {
        c.startService(new Intent(c, ChatService.class).setAction(ACTION_STOP));
    }

    @Override
    public void onCreate() {
        super.onCreate();
        hub = Hub.get(this);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, buildNotification(),
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);
        } else {
            startForeground(NOTIFICATION_ID, buildNotification());
        }

        WifiManager wifi = getApplicationContext().getSystemService(WifiManager.class);
        multicastLock = wifi.createMulticastLock("qareeb");
        multicastLock.setReferenceCounted(false);
        multicastLock.acquire();
        wifiLock = createWifiLock(wifi);
        wifiLock.setReferenceCounted(false);
        wifiLock.acquire();

        hub.addListener(this);
        hub.start();
    }

    @SuppressWarnings("deprecation")
    private static WifiManager.WifiLock createWifiLock(WifiManager wifi) {
        return wifi.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "qareeb");
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            hub.stop();
            stopForeground(STOP_FOREGROUND_REMOVE);
            stopSelf();
            return START_NOT_STICKY;
        }
        hub.start();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        hub.removeListener(this);
        if (multicastLock != null && multicastLock.isHeld()) multicastLock.release();
        if (wifiLock != null && wifiLock.isHeld()) wifiLock.release();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onHubChanged() {
        if (!hub.isRunning()) return;
        getSystemService(NotificationManager.class).notify(NOTIFICATION_ID, buildNotification());
    }

    private Notification buildNotification() {
        PendingIntent open = PendingIntent.getActivity(this, 0,
                new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop = PendingIntent.getService(this, 1,
                new Intent(this, ChatService.class).setAction(ACTION_STOP),
                PendingIntent.FLAG_IMMUTABLE);
        int n = hub == null ? 0 : hub.connectedCount();
        String status = n > 0 ? getString(R.string.connected_n, n) : getString(R.string.searching);
        return new Notification.Builder(this, Hub.CHANNEL_STATUS)
                .setSmallIcon(R.drawable.ic_send)
                .setContentTitle(status)
                .setContentText(getString(R.string.running))
                .setContentIntent(open)
                .setOngoing(true)
                .addAction(new Notification.Action.Builder(
                        (Icon) null, getString(R.string.quit), stop).build())
                .build();
    }
}
