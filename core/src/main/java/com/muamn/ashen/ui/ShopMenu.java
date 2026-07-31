package com.muamn.ashen.ui;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.Input;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.g2d.BitmapFont;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.graphics.glutils.ShapeRenderer;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.utils.Disposable;

import com.muamn.ashen.audio.Audio;
import com.muamn.ashen.audio.SoundBank;
import com.muamn.ashen.entity.Player;
import com.muamn.ashen.item.ItemDef;
import com.muamn.ashen.item.ItemLibrary;
import com.muamn.ashen.npc.NpcDef;

/**
 * A merchant's stock.
 *
 * Same shape as the bonfire menu on purpose - rows laid out once and their
 * rectangles kept, so a tap maps to a row with the arithmetic that drew it.
 * Stock is unlimited: the balance lever that matters is which items a merchant
 * is allowed to carry at all, and that lives in the data, not in a counter.
 */
public class ShopMenu implements Disposable {

    private final ItemLibrary items;
    private final Audio audio;

    private final ShapeRenderer shapes = new ShapeRenderer();
    private final SpriteBatch batch = new SpriteBatch();
    private final BitmapFont font = new BitmapFont();

    private boolean open;
    private NpcDef merchant;
    private int cursor;
    private String message = "";
    private float messageTimer;

    private float rowX, rowW, rowH, firstRowY;
    private int rowCount;

    private boolean prevTouched;
    private float inputCooldown;

    public ShopMenu(ItemLibrary items, Audio audio) {
        this.items = items;
        this.audio = audio;
    }

    public boolean isOpen() {
        return open;
    }

    public void open(NpcDef merchant) {
        this.merchant = merchant;
        this.open = true;
        this.cursor = 0;
        this.message = "";
        // Swallow the press that opened it.
        this.inputCooldown = 0.22f;
        this.prevTouched = Gdx.input.isTouched();
    }

    public void close() {
        open = false;
        merchant = null;
        cursor = 0;
    }

    /** @return true while the shop wants to keep the world paused. */
    public boolean update(float dt, Player player) {
        if (!open || merchant == null) return false;
        if (inputCooldown > 0f) inputCooldown -= dt;
        if (messageTimer > 0f) messageTimer -= dt;

        int rows = rowCount();
        int before = cursor;
        if (pressed(Input.Keys.UP) || pressed(Input.Keys.W)) cursor = Math.floorMod(cursor - 1, rows);
        if (pressed(Input.Keys.DOWN) || pressed(Input.Keys.S)) cursor = Math.floorMod(cursor + 1, rows);
        if (cursor != before && audio != null) audio.play(SoundBank.MENU_MOVE, 1f, 1f);

        boolean confirm = pressed(Input.Keys.ENTER) || pressed(Input.Keys.SPACE)
                || pressed(Input.Keys.E);
        boolean back = pressed(Input.Keys.ESCAPE) || pressed(Input.Keys.BACKSPACE)
                || pressed(Input.Keys.Q);

        boolean touched = Gdx.input.isTouched();
        if (touched && !prevTouched && inputCooldown <= 0f) {
            int row = rowAt(Gdx.input.getX(), Gdx.graphics.getHeight() - Gdx.input.getY());
            if (row >= 0 && row < rows) {
                cursor = row;
                confirm = true;
            } else {
                back = true;
            }
        }
        prevTouched = touched;

        if (inputCooldown > 0f) return true;

        if (back) {
            close();
            return false;
        }
        if (confirm) {
            if (cursor >= merchant.shop.size) close();
            else buy(player, merchant.shop.get(cursor));
            inputCooldown = 0.14f;
        }
        return open;
    }

    private void buy(Player player, NpcDef.Offer offer) {
        ItemDef def = items.get(offer.itemId);
        if (player.stats.souls < offer.price) {
            cue(SoundBank.MENU_DENY);
            toast("Not enough souls");
            return;
        }
        // Check the stack before taking the souls, or a full pack costs money.
        if (player.inventory.add(def, 1) <= 0) {
            cue(SoundBank.MENU_DENY);
            toast("Carrying too many");
            return;
        }
        player.stats.souls -= offer.price;
        if (def.consumable() && player.quickItem.isEmpty()) player.quickItem = def.id;
        cue(SoundBank.PICKUP);
        toast(def.nameEn + " x" + player.inventory.count(def.id));
    }

    private void cue(String id) {
        if (audio != null) audio.play(id, 1f, 1f);
    }

    private void toast(String text) {
        message = text;
        messageTimer = 2f;
    }

    /** Stock plus the Leave row. */
    private int rowCount() {
        return merchant == null ? 1 : merchant.shop.size + 1;
    }

    private boolean pressed(int key) {
        return Gdx.input.isKeyJustPressed(key);
    }

    private int rowAt(float x, float y) {
        if (rowCount <= 0) return -1;
        if (x < rowX || x > rowX + rowW) return -1;
        for (int i = 0; i < rowCount; i++) {
            float top = firstRowY - i * rowH;
            if (y <= top && y >= top - rowH) return i;
        }
        return -1;
    }

    public void render(Player player) {
        if (!open || merchant == null) return;

        int screenW = Gdx.graphics.getWidth();
        int screenH = Gdx.graphics.getHeight();
        float scale = MathUtils.clamp(screenW / 960f, 0.85f, 2.2f);

        rowW = MathUtils.clamp(screenW * 0.50f, 320f, 660f);
        rowH = 34f * scale;
        rowX = (screenW - rowW) * 0.5f;
        rowCount = rowCount();
        float panelH = rowH * rowCount + 96f * scale;
        float panelY = (screenH - panelH) * 0.5f;
        firstRowY = panelY + panelH - 64f * scale;

        Gdx.gl.glEnable(GL20.GL_BLEND);
        Gdx.gl.glBlendFunc(GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA);

        shapes.getProjectionMatrix().setToOrtho2D(0f, 0f, screenW, screenH);
        batch.getProjectionMatrix().setToOrtho2D(0f, 0f, screenW, screenH);

        shapes.begin(ShapeRenderer.ShapeType.Filled);
        shapes.setColor(0f, 0f, 0f, 0.62f);
        shapes.rect(0f, 0f, screenW, screenH);
        shapes.setColor(0.06f, 0.05f, 0.05f, 0.94f);
        shapes.rect(rowX - 22f * scale, panelY, rowW + 44f * scale, panelH);
        shapes.setColor(0.42f, 0.31f, 0.13f, 0.75f);
        shapes.rect(rowX, firstRowY - cursor * rowH - rowH + 5f, rowW, rowH - 6f);
        shapes.end();

        shapes.begin(ShapeRenderer.ShapeType.Line);
        shapes.setColor(0.55f, 0.47f, 0.32f, 0.85f);
        shapes.rect(rowX - 22f * scale, panelY, rowW + 44f * scale, panelH);
        shapes.end();

        batch.begin();
        font.getData().setScale(scale);
        font.setColor(0.92f, 0.86f, 0.68f, 1f);
        font.draw(batch, merchant.nameEn.toUpperCase(), rowX, panelY + panelH - 22f * scale);

        for (int i = 0; i < rowCount; i++) {
            float y = firstRowY - i * rowH - 8f * scale;
            if (i >= merchant.shop.size) {
                font.setColor(0.88f, 0.84f, 0.76f, 1f);
                font.draw(batch, "Leave", rowX + 14f * scale, y);
                continue;
            }
            NpcDef.Offer offer = merchant.shop.get(i);
            ItemDef def = items.get(offer.itemId);
            boolean affordable = player.stats.souls >= offer.price;
            // Greying out what cannot be bought answers the question before the
            // player has to press the button to ask it.
            if (affordable) font.setColor(0.88f, 0.84f, 0.76f, 1f);
            else font.setColor(0.48f, 0.45f, 0.42f, 1f);
            font.draw(batch, def.nameEn, rowX + 14f * scale, y);

            String right = offer.price + "   (" + player.inventory.count(def.id) + ")";
            font.draw(batch, right,
                    rowX + rowW - 14f * scale - right.length() * 9f * scale, y);
        }

        font.setColor(0.75f, 0.70f, 0.58f, 1f);
        font.draw(batch, "Souls: " + player.stats.souls, rowX, panelY + 30f * scale);
        if (messageTimer > 0f) {
            font.setColor(0.92f, 0.72f, 0.34f, MathUtils.clamp(messageTimer, 0f, 1f));
            font.draw(batch, message,
                    rowX + rowW - 14f * scale - message.length() * 9f * scale,
                    panelY + 30f * scale);
        }
        font.setColor(0.86f, 0.83f, 0.76f, 1f);
        font.getData().setScale(1f);
        batch.end();
    }

    @Override
    public void dispose() {
        shapes.dispose();
        batch.dispose();
        font.dispose();
    }
}
