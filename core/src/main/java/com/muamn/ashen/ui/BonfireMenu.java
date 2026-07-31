package com.muamn.ashen.ui;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.Input;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.g2d.BitmapFont;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.graphics.glutils.ShapeRenderer;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.Disposable;

import com.muamn.ashen.combat.WeaponDef;
import com.muamn.ashen.entity.Player;
import com.muamn.ashen.entity.Stats;
import com.muamn.ashen.audio.Audio;
import com.muamn.ashen.audio.SoundBank;
import com.muamn.ashen.item.ItemDef;
import com.muamn.ashen.item.ItemLibrary;

/**
 * The menu you get for resting at a bonfire: rest, level up, reinforce.
 *
 * Rows are laid out once and their rectangles kept, so a tap maps to a row with
 * the same arithmetic that drew it - no second layout to keep in sync. Labels
 * are English because the built-in bitmap font has no Arabic glyphs; the font
 * and the RTL layout are Part 4's job.
 */
public class BonfireMenu implements Disposable {

    public enum Page { ROOT, LEVEL_UP, REINFORCE, ITEMS }

    /** What the screen must do when the player picks Rest. */
    public interface RestAction {
        void rest();
    }

    private static final String[] ROOT_ITEMS = {
            "Rest", "Level Up", "Reinforce Weapon", "Items", "Leave"
    };
    private static final String[] ATTRIBUTES = {
            "Vigor", "Endurance", "Strength", "Dexterity", "Intelligence", "Faith"
    };

    private final ItemLibrary items;
    private final Audio audio;

    private final ShapeRenderer shapes = new ShapeRenderer();
    private final SpriteBatch batch = new SpriteBatch();
    private final BitmapFont font = new BitmapFont();

    private boolean open;
    private Page page = Page.ROOT;
    private int cursor;
    private String message = "";
    private float messageTimer;

    /** Row rectangles from the last draw, used to hit-test taps. */
    private float rowX, rowW, rowH, firstRowY;
    private int rowCount;

    private boolean prevTouched;
    private float inputCooldown;

    public BonfireMenu(ItemLibrary items, Audio audio) {
        this.items = items;
        this.audio = audio;
    }

    public boolean isOpen() {
        return open;
    }

    public void open() {
        open(Page.ROOT);
    }

    /** Opens straight onto a page. Used by the UI screenshot harness. */
    public void open(Page startPage) {
        open = true;
        page = startPage;
        cursor = 0;
        message = "";
        // Swallow the press that opened the menu.
        inputCooldown = 0.22f;
        prevTouched = Gdx.input.isTouched();
    }

    public void close() {
        open = false;
        page = Page.ROOT;
        cursor = 0;
    }

    /** @return true while the menu wants to keep the world paused. */
    public boolean update(float dt, Player player, WeaponDef weapon, RestAction onRest) {
        if (!open) return false;
        if (inputCooldown > 0f) inputCooldown -= dt;
        if (messageTimer > 0f) messageTimer -= dt;

        heldCount = player.inventory.ids().size;
        int items = itemCount();
        if (cursor >= items) cursor = items - 1;

        int before = cursor;
        if (pressed(Input.Keys.UP) || pressed(Input.Keys.W)) cursor = Math.floorMod(cursor - 1, items);
        if (pressed(Input.Keys.DOWN) || pressed(Input.Keys.S)) cursor = Math.floorMod(cursor + 1, items);
        if (cursor != before) cue(SoundBank.MENU_MOVE, 1f);

        boolean confirm = pressed(Input.Keys.ENTER) || pressed(Input.Keys.SPACE)
                || pressed(Input.Keys.E);
        boolean back = pressed(Input.Keys.ESCAPE) || pressed(Input.Keys.BACKSPACE)
                || pressed(Input.Keys.Q);

        // Touch: a tap on a row both moves the cursor and confirms it.
        boolean touched = Gdx.input.isTouched();
        if (touched && !prevTouched && inputCooldown <= 0f) {
            int row = rowAt(Gdx.input.getX(), Gdx.graphics.getHeight() - Gdx.input.getY());
            if (row >= 0 && row < items) {
                cursor = row;
                confirm = true;
            } else {
                back = true;
            }
        }
        prevTouched = touched;

        if (inputCooldown > 0f) return true;

        if (back) {
            if (page == Page.ROOT) close();
            else { page = Page.ROOT; cursor = 0; }
            inputCooldown = 0.14f;
            return open;
        }
        if (confirm) {
            activate(player, weapon, onRest);
            inputCooldown = 0.14f;
        }
        return open;
    }

    private void activate(Player player, WeaponDef weapon, RestAction onRest) {
        switch (page) {
            case ROOT:
                switch (cursor) {
                    case 0: onRest.rest(); close(); break;
                    case 1: page = Page.LEVEL_UP; cursor = 0; break;
                    case 2: page = Page.REINFORCE; cursor = 0; break;
                    case 3: page = Page.ITEMS; cursor = 0; break;
                    default: close(); break;
                }
                break;
            case ITEMS:
                selectItem(player);
                break;
            case LEVEL_UP:
                if (cursor >= ATTRIBUTES.length) { page = Page.ROOT; cursor = 0; break; }
                levelUp(player.stats, cursor);
                break;
            case REINFORCE:
                if (cursor == 0) reinforce(player, weapon);
                else { page = Page.ROOT; cursor = 0; }
                break;
            default:
                break;
        }
    }

    private void levelUp(Stats stats, int attribute) {
        long cost = Stats.soulsToLevel(stats.level);
        if (stats.souls < cost) {
            cue(SoundBank.MENU_DENY, 1f);
            toast("Not enough souls");
            return;
        }
        stats.souls -= cost;
        stats.level++;
        cue(SoundBank.LEVEL_UP, 1f);
        switch (attribute) {
            case 0: stats.vigor++; break;
            case 1: stats.endurance++; break;
            case 2: stats.strength++; break;
            case 3: stats.dexterity++; break;
            case 4: stats.intelligence++; break;
            default: stats.faith++; break;
        }
        // Raising vigor or endurance must grow the pool and heal by the same
        // amount, not just widen an empty bar.
        float healthBefore = stats.health;
        float staminaBefore = stats.stamina;
        float maxHealthBefore = stats.maxHealth;
        float maxStaminaBefore = stats.maxStamina;
        stats.recalculate();
        stats.health = Math.min(stats.maxHealth,
                healthBefore + (stats.maxHealth - maxHealthBefore));
        stats.stamina = Math.min(stats.maxStamina,
                staminaBefore + (stats.maxStamina - maxStaminaBefore));
        toast("Level " + stats.level);
    }

    private void reinforce(Player player, WeaponDef weapon) {
        Stats stats = player.stats;
        if (weapon.upgrade >= 10) {
            cue(SoundBank.MENU_DENY, 1f);
            toast("Already at +10");
            return;
        }
        String material = reinforceMaterial(weapon.upgrade + 1);
        int need = reinforceMaterialCount(weapon.upgrade + 1);
        if (!player.inventory.has(material, need)) {
            cue(SoundBank.MENU_DENY, 1f);
            toast("Need " + need + "x " + materialLabel(material));
            return;
        }
        long cost = reinforceCost(weapon);
        if (stats.souls < cost) {
            cue(SoundBank.MENU_DENY, 1f);
            toast("Not enough souls");
            return;
        }
        player.inventory.remove(material, need);
        stats.souls -= cost;
        weapon.upgrade++;
        cue(SoundBank.REINFORCE, 1f);
        toast(weapon.nameEn + " +" + weapon.upgrade);
    }

    /** Reinforcement gets steeply more expensive, as it should. */
    public static long reinforceCost(WeaponDef weapon) {
        int next = weapon.upgrade + 1;
        return (long) (180 * Math.pow(next, 1.55) + weapon.physical * next * 0.9);
    }

    /**
     * Which material a given upgrade step needs.
     *
     * Souls alone would make reinforcement a grinding problem: kill anything for
     * long enough and every weapon reaches +10. Gating the tiers behind materials
     * that only the right enemies drop, and putting the last one on the final
     * boss, means the upgrade path is something you find rather than something
     * you wait for.
     */
    public static String reinforceMaterial(int nextLevel) {
        if (nextLevel <= 3) return "ember_shard";
        if (nextLevel <= 6) return "ember_lump";
        if (nextLevel <= 9) return "ember_core";
        return "ember_heart";
    }

    /** How many of that material. Rises within each tier, resets at the next. */
    public static int reinforceMaterialCount(int nextLevel) {
        if (nextLevel >= 10) return 1;
        return ((nextLevel - 1) % 3) + 1;
    }

    /** Short label for the toast, so the message fits on a phone. */
    private static String materialLabel(String materialId) {
        switch (materialId) {
            case "ember_shard": return "Shard";
            case "ember_lump":  return "Lump";
            case "ember_core":  return "Core";
            default:            return "Heart";
        }
    }

    /**
     * Picking a consumable puts it in the quick slot. Picking a material just
     * reads it out - there is nothing to do with a shard here but spend it on
     * the page above.
     */
    private void selectItem(Player player) {
        Array<String> held = player.inventory.ids();
        if (cursor >= held.size) { page = Page.ROOT; cursor = 0; return; }
        ItemDef def = items.get(held.get(cursor));
        if (def.consumable()) {
            player.quickItem = def.id;
            cue(SoundBank.PICKUP, 0.7f);
            toast(def.nameEn + " ready");
        } else {
            toast(def.descEn);
        }
    }

    /** Menu sounds, skipped entirely when there is no audio. */
    private void cue(String id, float volume) {
        if (audio != null) audio.play(id, volume, 1f);
    }

    private void toast(String text) {
        message = text;
        messageTimer = 2f;
    }

    private int itemCount() {
        switch (page) {
            case LEVEL_UP:  return ATTRIBUTES.length + 1;   // attributes plus Back
            case REINFORCE: return 2;                       // Reinforce plus Back
            case ITEMS:     return heldCount + 1;           // what is carried plus Back
            default:        return ROOT_ITEMS.length;
        }
    }

    /**
     * How many item rows the ITEMS page has. Captured when the page is entered
     * and when it is drawn, so the cursor cannot point past the list if an item
     * is consumed while the page is open.
     */
    private int heldCount;

    private boolean pressed(int key) {
        return Gdx.input.isKeyJustPressed(key);
    }

    /** Which row a screen point falls on, or -1. */
    private int rowAt(float x, float y) {
        if (rowCount <= 0) return -1;
        if (x < rowX || x > rowX + rowW) return -1;
        for (int i = 0; i < rowCount; i++) {
            float top = firstRowY - i * rowH;
            if (y <= top && y >= top - rowH) return i;
        }
        return -1;
    }

    public void render(Player player, WeaponDef weapon) {
        if (!open) return;

        int screenW = Gdx.graphics.getWidth();
        int screenH = Gdx.graphics.getHeight();
        float scale = MathUtils.clamp(screenW / 960f, 0.85f, 2.2f);

        rowW = MathUtils.clamp(screenW * 0.44f, 300f, 620f);
        rowH = 34f * scale;
        rowX = (screenW - rowW) * 0.5f;
        rowCount = itemCount();
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
        for (int i = 0; i < rowCount; i++) {
            if (i != cursor) continue;
            shapes.setColor(0.42f, 0.31f, 0.13f, 0.75f);
            shapes.rect(rowX, firstRowY - i * rowH - rowH + 5f, rowW, rowH - 6f);
        }
        shapes.end();

        shapes.begin(ShapeRenderer.ShapeType.Line);
        shapes.setColor(0.55f, 0.47f, 0.32f, 0.85f);
        shapes.rect(rowX - 22f * scale, panelY, rowW + 44f * scale, panelH);
        shapes.end();

        batch.begin();
        font.getData().setScale(scale);
        font.setColor(0.92f, 0.86f, 0.68f, 1f);
        font.draw(batch, title(player, weapon), rowX, panelY + panelH - 22f * scale);

        font.setColor(0.88f, 0.84f, 0.76f, 1f);
        for (int i = 0; i < rowCount; i++) {
            float y = firstRowY - i * rowH - 8f * scale;
            font.draw(batch, label(i, player, weapon), rowX + 14f * scale, y);
            String right = rightLabel(i, player, weapon);
            if (right != null) {
                font.draw(batch, right, rowX + rowW - 14f * scale - right.length() * 9f * scale, y);
            }
        }

        font.setColor(0.75f, 0.70f, 0.58f, 1f);
        String souls = "Souls: " + player.stats.souls;
        font.draw(batch, souls, rowX, panelY + 30f * scale);
        if (messageTimer > 0f) {
            font.setColor(0.92f, 0.72f, 0.34f, MathUtils.clamp(messageTimer, 0f, 1f));
            font.draw(batch, message, rowX + rowW - 14f * scale - message.length() * 9f * scale,
                    panelY + 30f * scale);
        }
        font.setColor(0.86f, 0.83f, 0.76f, 1f);
        font.getData().setScale(1f);
        batch.end();
    }

    private String title(Player player, WeaponDef weapon) {
        switch (page) {
            case LEVEL_UP:  return "LEVEL UP   -   next costs "
                    + Stats.soulsToLevel(player.stats.level);
            case REINFORCE: return "REINFORCE   -   " + weapon.nameEn + " +" + weapon.upgrade;
            case ITEMS:     return "ITEMS   -   pick one for the quick slot";
            default:        return "BONFIRE";
        }
    }

    private String label(int index, Player player, WeaponDef weapon) {
        switch (page) {
            case LEVEL_UP:
                return index < ATTRIBUTES.length ? ATTRIBUTES[index] : "Back";
            case REINFORCE:
                if (index == 0) {
                    if (weapon.upgrade >= 10) return "Fully reinforced";
                    int next = weapon.upgrade + 1;
                    return "To +" + next + "   " + reinforceMaterialCount(next)
                            + "x " + materialLabel(reinforceMaterial(next));
                }
                return "Back";
            case ITEMS: {
                Array<String> held = player.inventory.ids();
                if (index >= held.size) return held.size == 0 ? "Carrying nothing" : "Back";
                ItemDef def = items.get(held.get(index));
                return (def.id.equals(player.quickItem) ? "* " : "  ") + def.nameEn;
            }
            default:
                return ROOT_ITEMS[index];
        }
    }

    private String rightLabel(int index, Player player, WeaponDef weapon) {
        Stats s = player.stats;
        switch (page) {
            case LEVEL_UP:
                if (index >= ATTRIBUTES.length) return null;
                int[] values = {s.vigor, s.endurance, s.strength,
                        s.dexterity, s.intelligence, s.faith};
                return Integer.toString(values[index]);
            case REINFORCE:
                if (index == 0 && weapon.upgrade < 10) {
                    int next = weapon.upgrade + 1;
                    String material = reinforceMaterial(next);
                    // Show what is carried against what is needed, so a refusal
                    // to reinforce is explained before it happens.
                    return reinforceCost(weapon) + "   ("
                            + player.inventory.count(material) + "/"
                            + reinforceMaterialCount(next) + ")";
                }
                return null;
            case ITEMS: {
                Array<String> held = player.inventory.ids();
                if (index >= held.size) return null;
                return "x" + player.inventory.count(held.get(index));
            }
            default:
                if (index == 1) return "Lv " + s.level;
                return null;
        }
    }

    @Override
    public void dispose() {
        shapes.dispose();
        batch.dispose();
        font.dispose();
    }
}
