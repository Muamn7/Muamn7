package com.muamn.qareeb;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
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

import com.muamn.qareeb.core.ChatMessage;

import java.util.ArrayList;
import java.util.List;

/** Who is around, and every conversation so far. */
public final class MainActivity extends Activity implements Hub.Listener {
    private static final int MENU_NAME = 1;
    private static final int MENU_CONNECT = 2;
    private static final int MENU_QUIT = 3;

    private Hub hub;
    private TextView me;
    private TextView address;
    private TextView status;
    private TextView help;
    private final Adapter adapter = new Adapter();

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(R.layout.activity_main);
        hub = Hub.get(this);
        me = findViewById(R.id.me);
        address = findViewById(R.id.address);
        status = findViewById(R.id.status);
        help = findViewById(R.id.help);
        ListView list = findViewById(R.id.list);
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) ->
                startActivity(new Intent(this, ChatActivity.class)
                        .putExtra(ChatActivity.EXTRA_KEY, adapter.items.get(position).key)));

        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
        }

        if (hub.hasName()) ChatService.start(this);
        else askName(true);
    }

    @Override
    protected void onResume() {
        super.onResume();
        hub.addListener(this);
        if (hub.hasName() && !hub.isRunning()) ChatService.start(this);
        onHubChanged();
    }

    @Override
    protected void onPause() {
        hub.removeListener(this);
        super.onPause();
    }

    @Override
    public void onHubChanged() {
        me.setText(getString(R.string.you, hub.myName()));
        List<String> addrs = hub.addresses();
        address.setText(addrs.isEmpty() ? getString(R.string.no_address)
                : getString(R.string.your_address, String.join("  ·  ", addrs)));
        int n = hub.connectedCount();
        status.setText(!hub.isRunning() ? getString(R.string.stopped)
                : n > 0 ? getString(R.string.connected_n, n) : getString(R.string.searching));
        help.setVisibility(hub.peers().isEmpty() ? View.VISIBLE : View.GONE);
        adapter.items = hub.conversations();
        adapter.notifyDataSetChanged();
    }

    // ------------------------------------------------------------------ menu

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, MENU_NAME, 0, R.string.change_name);
        menu.add(0, MENU_CONNECT, 1, R.string.connect_manual);
        menu.add(0, MENU_QUIT, 2, R.string.quit);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        switch (item.getItemId()) {
            case MENU_NAME:
                askName(false);
                return true;
            case MENU_CONNECT:
                askAddress();
                return true;
            case MENU_QUIT:
                ChatService.stop(this);
                finishAndRemoveTask();
                return true;
            default:
                return super.onOptionsItemSelected(item);
        }
    }

    private void askName(boolean firstTime) {
        EditText input = dialogInput(getString(R.string.name_hint), InputType.TYPE_CLASS_TEXT
                | InputType.TYPE_TEXT_FLAG_CAP_WORDS | InputType.TYPE_TEXT_VARIATION_PERSON_NAME);
        input.setText(hub.myName());
        AlertDialog d = new AlertDialog.Builder(this)
                .setTitle(R.string.your_name)
                .setView(padded(input))
                .setCancelable(!firstTime)
                .setPositiveButton(R.string.save, null)
                .create();
        if (!firstTime) d.setButton(AlertDialog.BUTTON_NEGATIVE, getString(R.string.cancel),
                (dialog, which) -> { });
        d.setOnShowListener(x -> d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String name = input.getText().toString().trim();
            if (name.isEmpty()) return; // keep the dialog open until there is a name
            hub.setName(name);
            ChatService.start(this);
            d.dismiss();
        }));
        d.show();
    }

    private void askAddress() {
        EditText input = dialogInput(getString(R.string.connect_manual_hint),
                InputType.TYPE_CLASS_PHONE);
        new AlertDialog.Builder(this)
                .setTitle(R.string.connect_manual)
                .setMessage(R.string.connect_manual_help)
                .setView(padded(input))
                .setPositiveButton(R.string.connect, (d, w) -> {
                    String host = input.getText().toString().trim();
                    if (!host.isEmpty()) hub.connectTo(host);
                })
                .setNegativeButton(R.string.cancel, null)
                .show();
    }

    private EditText dialogInput(String hint, int type) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setInputType(type);
        e.setSingleLine(true);
        return e;
    }

    private View padded(View v) {
        LinearLayout box = new LinearLayout(this);
        int p = (int) (20 * getResources().getDisplayMetrics().density);
        box.setPadding(p, p / 2, p, 0);
        box.addView(v, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return box;
    }

    // ------------------------------------------------------------------ list

    private final class Adapter extends BaseAdapter {
        List<Hub.Conversation> items = new ArrayList<>();

        @Override public int getCount() { return items.size(); }
        @Override public Object getItem(int i) { return items.get(i); }
        @Override public long getItemId(int i) { return i; }

        @Override
        public View getView(int i, View view, ViewGroup parent) {
            if (view == null) {
                view = LayoutInflater.from(MainActivity.this)
                        .inflate(R.layout.item_conversation, parent, false);
            }
            Hub.Conversation c = items.get(i);
            boolean group = ChatMessage.GROUP.equals(c.key);

            TextView avatar = view.findViewById(R.id.avatar);
            avatar.setText(group ? "👥" : Ui.initial(c.title));
            Ui.tint(avatar, group ? getColor(R.color.primary) : Ui.colorFor(c.key));
            View presence = view.findViewById(R.id.presence);
            presence.setVisibility(group ? View.GONE : View.VISIBLE);
            Ui.tint(presence, getColor(c.online ? R.color.online : R.color.offline));

            ((TextView) view.findViewById(R.id.title)).setText(c.title);
            TextView subtitle = view.findViewById(R.id.subtitle);
            TextView time = view.findViewById(R.id.time);
            if (c.last != null) {
                String who = c.last.fromId.equals(hub.myId()) ? getString(R.string.you_prefix)
                        : group ? c.last.fromName + ": " : "";
                subtitle.setText(who + c.last.text.replace('\n', ' '));
                time.setText(Ui.shortTime(c.last.time));
            } else {
                subtitle.setText(group ? getString(R.string.group_sub)
                        : getString(c.online ? R.string.online : R.string.offline));
                time.setText("");
            }
            TextView unread = view.findViewById(R.id.unread);
            unread.setVisibility(c.unread > 0 ? View.VISIBLE : View.INVISIBLE);
            unread.setText(String.valueOf(c.unread));
            return view;
        }
    }
}
