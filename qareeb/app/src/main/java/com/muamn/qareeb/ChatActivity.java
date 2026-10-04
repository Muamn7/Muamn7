package com.muamn.qareeb;

import android.app.ActionBar;
import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.os.Bundle;
import android.view.Gravity;
import android.view.LayoutInflater;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import com.muamn.qareeb.core.ChatMessage;

import java.util.ArrayList;
import java.util.List;

/** One conversation: the group, or a friend. */
public final class ChatActivity extends Activity implements Hub.Listener {
    static final String EXTRA_KEY = "key";
    private static final int MENU_CLEAR = 1;

    private Hub hub;
    private String key;
    private boolean group;
    private ListView list;
    private EditText input;
    private final Adapter adapter = new Adapter();

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(R.layout.activity_chat);
        hub = Hub.get(this);
        list = findViewById(R.id.messages);
        input = findViewById(R.id.input);
        list.setAdapter(adapter);
        list.setOnItemLongClickListener((parent, view, position, id) -> {
            ClipboardManager cb = getSystemService(ClipboardManager.class);
            cb.setPrimaryClip(ClipData.newPlainText("message", adapter.items.get(position).text));
            Toast.makeText(this, R.string.copied, Toast.LENGTH_SHORT).show();
            return true;
        });
        findViewById(R.id.send).setOnClickListener(v -> send());
        ActionBar bar = getActionBar();
        if (bar != null) bar.setDisplayHomeAsUpEnabled(true);
        open(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        open(intent);
    }

    private void open(Intent intent) {
        key = intent.getStringExtra(EXTRA_KEY);
        if (key == null) key = ChatMessage.GROUP;
        group = ChatMessage.GROUP.equals(key);
        // onResume follows both onCreate and onNewIntent, and marks it read there.
        onHubChanged();
    }

    @Override
    protected void onResume() {
        super.onResume();
        hub.addListener(this);
        hub.setOpenConversation(key);
        // Opened from a notification after the app was closed.
        if (!hub.isRunning() && hub.hasName()) ChatService.start(this);
        onHubChanged();
    }

    @Override
    protected void onPause() {
        hub.setOpenConversation(null);
        hub.removeListener(this);
        super.onPause();
    }

    private void send() {
        String text = input.getText().toString();
        if (text.trim().isEmpty()) return;
        hub.send(key, text);
        input.setText("");
        list.post(() -> list.setSelection(adapter.getCount() - 1));
    }

    @Override
    public void onHubChanged() {
        ActionBar bar = getActionBar();
        if (bar != null) {
            bar.setTitle(hub.displayName(key));
            if (group) {
                bar.setSubtitle(getString(R.string.group_online_n, hub.connectedCount()));
            } else {
                bar.setSubtitle(hub.isOnline(key) ? R.string.online : R.string.offline);
            }
        }
        boolean atBottom = list.getLastVisiblePosition() >= adapter.getCount() - 2;
        adapter.items = hub.messages(key);
        adapter.notifyDataSetChanged();
        if (atBottom) list.setSelection(adapter.getCount() - 1);
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, MENU_CLEAR, 0, R.string.clear_chat);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == android.R.id.home) {
            finish();
            return true;
        }
        if (item.getItemId() == MENU_CLEAR) {
            hub.clear(key);
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    private final class Adapter extends BaseAdapter {
        List<ChatMessage> items = new ArrayList<>();

        @Override public int getCount() { return items.size(); }
        @Override public Object getItem(int i) { return items.get(i); }
        @Override public long getItemId(int i) { return i; }

        @Override
        public View getView(int i, View view, ViewGroup parent) {
            if (view == null) {
                view = LayoutInflater.from(ChatActivity.this)
                        .inflate(R.layout.item_message, parent, false);
            }
            ChatMessage m = items.get(i);
            boolean mine = m.fromId.equals(hub.myId());

            // Right-to-left layout: the start side is the right. Friends'
            // messages sit there, yours on the left, mirroring the usual chat.
            LinearLayout row = view.findViewById(R.id.row);
            row.setGravity(mine ? Gravity.END : Gravity.START);
            View bubble = view.findViewById(R.id.bubble);
            bubble.setBackgroundResource(mine ? R.drawable.bubble_mine : R.drawable.bubble_theirs);

            TextView sender = view.findViewById(R.id.sender);
            boolean showSender = group && !mine;
            sender.setVisibility(showSender ? View.VISIBLE : View.GONE);
            if (showSender) {
                sender.setText(m.fromName);
                sender.setTextColor(Ui.colorFor(m.fromId));
            }
            ((TextView) view.findViewById(R.id.text)).setText(m.text);

            String meta = Ui.time(m.time);
            if (mine) {
                if (m.status == ChatMessage.Status.PENDING) meta += "  🕓";
                else meta += group ? "  ✓" : "  ✓✓";
            }
            ((TextView) view.findViewById(R.id.meta)).setText(meta);
            return view;
        }
    }
}
