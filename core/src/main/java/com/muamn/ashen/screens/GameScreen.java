package com.muamn.ashen.screens;

import com.badlogic.gdx.Application;
import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.Input;
import com.badlogic.gdx.ScreenAdapter;
import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Matrix4;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Array;

import com.muamn.ashen.AshenGame;
import com.muamn.ashen.Config;
import com.muamn.ashen.audio.Audio;
import com.muamn.ashen.audio.SoundBank;
import com.muamn.ashen.camera.OrbitCamera;
import com.muamn.ashen.combat.Combatant;
import com.muamn.ashen.combat.WeaponDef;
import com.muamn.ashen.combat.WeaponFactory;
import com.muamn.ashen.entity.BodyFactory;
import com.muamn.ashen.entity.CharacterRig;
import com.muamn.ashen.entity.Enemy;
import com.muamn.ashen.entity.EnemyDef;
import com.muamn.ashen.entity.EnemyVisual;
import com.muamn.ashen.entity.HumanoidFactory;
import com.muamn.ashen.entity.HumanoidSpec;
import com.muamn.ashen.entity.Player;
import com.muamn.ashen.entity.RigVisual;
import com.muamn.ashen.input.ControlState;
import com.muamn.ashen.item.ItemDef;
import com.muamn.ashen.item.LootTable;
import com.muamn.ashen.npc.Npc;
import com.muamn.ashen.npc.NpcDef;
import com.muamn.ashen.input.DesktopControls;
import com.muamn.ashen.input.TouchControls;
import com.muamn.ashen.render.RetroRenderer;
import com.muamn.ashen.render.RetroShader;
import com.muamn.ashen.save.SaveData;
import com.muamn.ashen.save.SaveGame;
import com.muamn.ashen.ui.BonfireMenu;
import com.muamn.ashen.ui.DialogueBox;
import com.muamn.ashen.ui.ShopMenu;
import com.muamn.ashen.ui.Hud;
import com.muamn.ashen.world.BossArena;
import com.muamn.ashen.world.Level;
import com.muamn.ashen.world.Pickup;
import com.muamn.ashen.world.Areas;
import com.muamn.ashen.world.Portal;

/**
 * The playable screen: level, player, enemies, camera, HUD.
 *
 * Simulation runs on a fixed 60Hz step regardless of display refresh rate. A
 * game built on i-frames and attack windows cannot have its timing shift when
 * the frame rate does - a roll has to clear the same attack on a 120Hz tablet
 * as it does on a phone struggling at 40.
 */
public class GameScreen extends ScreenAdapter {

    /** Seconds of black before respawning at the bonfire. */
    private static final float DEATH_FADE = 3.2f;
    /** How close the player must be to a bonfire to rest at it. */
    private static final float BONFIRE_RANGE = 2.6f;
    private static final float ESTUS_HEAL_FRACTION = 0.42f;
    /** Starting Estus charges. Upgrading the flask raises this in Part 3. */
    private static final int ESTUS_CHARGES = 5;

    private final AshenGame game;

    private RetroRenderer renderer;
    private OrbitCamera camera;
    private Level level;
    private Player player;
    private Hud hud;

    private final ControlState controls = new ControlState();
    private DesktopControls desktopControls;
    private TouchControls touchControls;

    private final Array<ModelInstance> renderList = new Array<>();
    private final Array<Enemy> enemies = new Array<>();
    private final Array<Combatant> combatants = new Array<>();

    // ---- loot ----
    private final Array<Pickup> pickups = new Array<>();
    private final Array<LootTable.Drop> rolled = new Array<>();
    private Model pickupModel;
    /**
     * Drop rolls. Seeded from the clock rather than fixed: a deterministic seed
     * would let a player reload to reroll a drop, which is the one thing loot
     * randomness must not allow.
     */
    private final java.util.Random loot = new java.util.Random();

    // ---- player weapon ----
    private WeaponDef weapon;
    private Model weaponModel;
    private ModelInstance weaponInstance;
    private int weaponIndex;
    private final Matrix4 weaponTransform = new Matrix4();

    // ---- progression ----
    private int estus = ESTUS_CHARGES;
    private int estusMax = ESTUS_CHARGES;
    private float lastSavedAt;
    private float deathTimer;
    private final Vector3 bonfire = new Vector3(0f, 0f, -6f);
    private final Vector3 bloodstain = new Vector3();
    private long bloodstainSouls;
    private boolean hasBloodstain;
    private String toast = "";
    private float toastTimer;

    // ---- people ----
    private final Array<Npc> npcs = new Array<>();
    private final Array<NpcDef> npcDefs = new Array<>();
    private DialogueBox dialogue;
    private ShopMenu shop;
    /** Who the player is mid-conversation with, or null. */
    private Npc talkingTo;

    private final SaveGame saveGame = new SaveGame();
    private SaveData save;
    private BonfireMenu menu;

    /** The boss fight in progress, and the arena it belongs to. */
    private BossArena activeArena;
    private Enemy activeBoss;
    private float bossBannerTimer;

    /** Area currently loaded, and the area the bonfire we respawn to is in. */
    private String currentArea = Areas.ASYLUM;
    private String bonfireArea = Areas.ASYLUM;
    /** Set when a portal has been taken; the swap happens outside the step loop. */
    private Portal pendingPortal;
    private float areaBannerTimer;

    private Enemy lockedEnemy;
    private final Vector3 lockPoint = new Vector3();
    private final Vector3 tmp = new Vector3();

    private float accumulator;
    private float elapsed;
    private boolean autopilotRolled;

    public GameScreen(AshenGame game) {
        this.game = game;
    }

    @Override
    public void show() {
        renderer = new RetroRenderer();
        renderer.onDisplayResize(Gdx.graphics.getWidth(), Gdx.graphics.getHeight());

        save = saveGame.load();
        currentArea = Areas.exists(save.areaId) ? save.areaId : Areas.ASYLUM;
        if (game.startArea != null && Areas.exists(game.startArea)) {
            currentArea = game.startArea;
            save.bonfireArea = "";
        }
        level = Areas.build(currentArea, game.textures);
        applyLevelMood();

        HumanoidSpec spec = HumanoidSpec.knight();
        CharacterRig rig = new CharacterRig(
                HumanoidFactory.build(spec, game.textures, "player"), spec);

        weaponIndex = indexOfWeapon(save.weaponId);
        weapon = game.weapons.all().get(weaponIndex);
        weapon.upgrade = MathUtils.clamp(save.weaponUpgrade, 0, 10);

        player = new Player(rig, weapon);
        player.audio = game.audio;
        applySave(save);
        equip(weapon);

        bonfireArea = Areas.exists(save.bonfireArea) ? save.bonfireArea : Areas.ASYLUM;
        bonfire.set(save.bonfireX, save.bonfireY, save.bonfireZ);
        // Start at the bonfire if we saved in this area, otherwise at the area's
        // own entrance - a save can name a bonfire that lives somewhere else.
        if (bonfireArea.equals(currentArea)) {
            player.spawn(bonfire.x, bonfire.y + 0.2f, bonfire.z + 2f, 180f);
        } else {
            player.spawn(level.spawn.x, level.spawn.y, level.spawn.z, level.spawnFacing);
        }
        areaBannerTimer = 3f;
        if (game.spawnAt != null) {
            String[] parts = game.spawnAt.split(",");
            player.spawn(Float.parseFloat(parts[0].trim()), 0.4f,
                    Float.parseFloat(parts[1].trim()), 0f);
        }

        spawnEnemies();

        camera = new OrbitCamera(renderer.aspectRatio());
        camera.distance = game.cameraDistance;
        camera.yaw = level.spawnFacing + 180f + game.cameraYawOffset;
        camera.snapTo(player.body.position);

        hud = new Hud();
        hud.resize(Gdx.graphics.getWidth(), Gdx.graphics.getHeight());
        hud.showDebug = game.debugOverlay;

        pickupModel = Pickup.buildModel(game.textures);
        menu = new BonfireMenu(game.items, game.audio);
        dialogue = new DialogueBox();
        shop = new ShopMenu(game.items, game.audio);
        spawnNpcs();
        if (game.openMenuOnStart) menu.open(game.menuPage);
        if (game.talkTo != null) openConversationById(game.talkTo);

        // The ambience starts with the world, not with the first area change.
        game.audio.setListener(player.body.position);
        game.audio.playMusic(SoundBank.AMBIENCE_WIND);

        if (isTouchPlatform()) {
            touchControls = new TouchControls();
            touchControls.updateProjection(Gdx.graphics.getWidth(), Gdx.graphics.getHeight());
        } else {
            desktopControls = new DesktopControls();
            Gdx.input.setCursorCatched(true);
        }
    }

    /**
     * Swaps to another area.
     *
     * Areas are rebuilt rather than kept in memory: a phone has no room for four
     * levels at once, and rebuilding one is a few milliseconds of box-stacking.
     * Everything that belongs to the player - stats, souls, weapon, Estus -
     * survives; everything that belongs to the area is thrown away and remade.
     */
    private void enterArea(String areaId, Vector3 at, float facing) {
        endBossFight(false);
        for (Enemy enemy : enemies) enemy.visual.dispose();
        enemies.clear();
        // Loot dropped in the area you are leaving is gone. Carrying it across
        // would mean an item lying in a place it was never dropped.
        pickups.clear();
        endConversation();
        for (Npc npc : npcs) npc.dispose();
        npcs.clear();
        clearLockOn();

        if (level != null) level.dispose();
        currentArea = areaId;
        level = Areas.build(areaId, game.textures);
        applyLevelMood();

        player.spawn(at.x, at.y, at.z, facing);
        spawnEnemies();
        spawnNpcs();
        // Swing the camera round behind the arrival facing. Keeping the old yaw
        // would drop the player into a new area looking back the way they came.
        camera.yaw = facing + 180f;
        camera.snapTo(player.body.position);
        areaBannerTimer = 3f;
        game.audio.play(SoundBank.AREA_CHANGE, 0.8f, 1f);
        game.audio.playMusic(SoundBank.AMBIENCE_WIND);

        // Arriving somewhere new is a checkpoint worth keeping.
        writeSave();
    }

    /** Takes a portal the player is standing in, if any. */
    private void checkPortals() {
        if (pendingPortal != null) return;
        for (Portal portal : level.portals) {
            if (!portal.contains(player.body.position)) continue;
            if (portal.requiresInteract && !controls.interactPressed) continue;
            pendingPortal = portal;
            return;
        }
    }

    /** The portal under the player, for the on-screen prompt. */
    private Portal portalPrompt() {
        for (Portal portal : level.portals) {
            if (portal.contains(player.body.position)) return portal;
        }
        return null;
    }

    private int indexOfWeapon(String id) {
        Array<WeaponDef> all = game.weapons.all();
        for (int i = 0; i < all.size; i++) {
            if (all.get(i).id.equals(id)) return i;
        }
        return 0;
    }

    /** Pours a save into the live player. */
    private void applySave(SaveData data) {
        player.stats.level = data.level;
        player.stats.vigor = data.vigor;
        player.stats.endurance = data.endurance;
        player.stats.strength = data.strength;
        player.stats.dexterity = data.dexterity;
        player.stats.intelligence = data.intelligence;
        player.stats.faith = data.faith;
        player.stats.recalculate();
        player.stats.health = player.stats.maxHealth;
        player.stats.stamina = player.stats.maxStamina;
        player.stats.souls = data.souls;

        estusMax = Math.max(1, data.estusMax);
        estus = estusMax;

        player.inventory.decode(data.inventory, game.items);
        // An armed item that is no longer carried, or no longer exists, falls
        // back to the flask rather than leaving a dead button.
        player.quickItem = player.inventory.has(data.quickItem, 1) ? data.quickItem : "";

        hasBloodstain = data.hasBloodstain;
        bloodstainSouls = data.bloodstainSouls;
        bloodstain.set(data.bloodstainX, data.bloodstainY, data.bloodstainZ);
    }

    /** Copies the live state back into the save and writes it. */
    private void writeSave() {
        if (save == null) return;
        save.level = player.stats.level;
        save.vigor = player.stats.vigor;
        save.endurance = player.stats.endurance;
        save.strength = player.stats.strength;
        save.dexterity = player.stats.dexterity;
        save.intelligence = player.stats.intelligence;
        save.faith = player.stats.faith;
        save.souls = player.stats.souls;
        save.estusMax = estusMax;
        save.playTime += elapsed - lastSavedAt;
        lastSavedAt = elapsed;

        save.weaponId = weapon.id;
        save.weaponUpgrade = weapon.upgrade;

        save.inventory = player.inventory.encode();
        save.quickItem = player.quickItem;

        save.areaId = currentArea;
        save.bonfireArea = bonfireArea;
        save.bonfireId = bonfireArea;
        save.bonfireX = bonfire.x;
        save.bonfireY = bonfire.y;
        save.bonfireZ = bonfire.z;

        save.hasBloodstain = hasBloodstain;
        save.bloodstainSouls = bloodstainSouls;
        save.bloodstainX = bloodstain.x;
        save.bloodstainY = bloodstain.y;
        save.bloodstainZ = bloodstain.z;

        saveGame.save(save);
    }

    /** Builds the model for a weapon and hands it to the player. */
    private void equip(WeaponDef def) {
        if (weaponModel != null) weaponModel.dispose();
        weapon = def;
        weaponModel = WeaponFactory.build(def, game.textures);
        weaponInstance = new ModelInstance(weaponModel);
        player.setWeapon(def);
    }

    private void spawnEnemies() {
        for (Level.Spawn spawn : level.spawns) {
            addEnemy(game.bestiary.get(spawn.enemyId), spawn.x, spawn.z, spawn.facing);
        }
        refreshCombatants();
    }

    private void refreshCombatants() {
        combatants.clear();
        combatants.add(player);
        for (Enemy e : enemies) combatants.add(e);
        player.setTargets(combatants);
    }

    private Enemy addEnemy(EnemyDef def, float x, float z, float facing) {
        EnemyVisual visual = BodyFactory.create(def.body, game.textures, def.runSpeed);
        Enemy enemy = new Enemy(def, visual, game.weapons.get(def.weaponId));
        enemy.audio = game.audio;
        enemy.spawn(x, 0.2f, z, facing);
        enemy.setTarget(player);
        enemies.add(enemy);
        return enemy;
    }

    private boolean isTouchPlatform() {
        if (game.forceTouchControls) return true;
        Application.ApplicationType type = Gdx.app.getType();
        return type == Application.ApplicationType.Android || type == Application.ApplicationType.iOS;
    }

    private void applyLevelMood() {
        RetroShader.Environment env = renderer.env();
        env.fogColor.set(level.fogColor);
        env.ambient.set(level.ambient);
        env.lightColor.set(level.lightColor);
        env.lightDir.set(level.lightDir).nor();
        env.fogNear = level.fogNear;
        env.fogFar = level.fogFar;
    }

    @Override
    public void render(float delta) {
        float dt = Math.min(delta, Config.MAX_FRAME_TIME);
        elapsed += dt;
        if (toastTimer > 0f) toastTimer -= dt;

        // Menus own input and freeze the world while they are up. Shop first:
        // it is opened from a conversation and has to be the one that closes.
        if (shop.isOpen()) {
            if (!shop.update(dt, player)) endConversation();
            frozenFrame(dt);
            return;
        }
        if (dialogue.isOpen()) {
            updateConversation(dt);
            frozenFrame(dt);
            return;
        }
        if (menu.isOpen()) {
            menu.update(dt, player, weapon, this::rest);
            frozenFrame(dt);
            return;
        }

        gatherInput(dt);

        // Fixed-step simulation with a frame-time cap, so a stall cannot make the
        // player tunnel through a wall by simulating a huge step.
        accumulator += dt;
        int steps = 0;
        while (accumulator >= Config.FIXED_STEP && steps < 8) {
            simulate(Config.FIXED_STEP);
            accumulator -= Config.FIXED_STEP;
            steps++;
        }
        if (steps == 8) accumulator = 0f;

        // Swap areas outside the fixed-step loop, so no substep runs against a
        // level that is halfway through being replaced.
        if (pendingPortal != null) {
            Portal portal = pendingPortal;
            pendingPortal = null;
            enterArea(portal.targetArea, portal.targetPosition, portal.targetFacing);
        }
        if (areaBannerTimer > 0f) areaBannerTimer -= dt;

        camera.update(player.body.position, level.collision, dt);
        hud.update(player.stats, dt);
        for (Npc npc : npcs) npc.update(dt);

        renderScene();
        renderHud();
        if (touchControls != null) touchControls.render();

        controls.clearEdges();
    }

    /** Draws a frame with the world paused behind whatever menu is up. */
    private void frozenFrame(float dt) {
        controls.reset();
        camera.update(player.body.position, level.collision, dt);
        hud.update(player.stats, dt);
        renderScene();
        renderHud();
    }

    private void renderHud() {
        if (menu.isOpen()) {
            hud.render(player.stats);
            menu.render(player, weapon);
            return;
        }
        if (shop.isOpen()) {
            hud.render(player.stats);
            shop.render(player);
            return;
        }
        if (dialogue.isOpen()) {
            hud.render(player.stats);
            dialogue.render();
            return;
        }
        if (hud.showDebug) {
            hud.setDebugLine(String.format(
                    "fps %d | %s | %s +%d | spd %.1f | souls %d | estus %d | enemies %d",
                    Gdx.graphics.getFramesPerSecond(), player.getState(),
                    weapon.nameEn, weapon.upgrade, player.groundSpeed(),
                    player.stats.souls, estus, aliveEnemies())
                    + " | " + currentArea);
        }
        hud.render(player.stats);
        if (player.quickItem.isEmpty()) {
            hud.quickSlot("Estus", estus, player.buffRemaining());
        } else {
            hud.quickSlot(game.items.get(player.quickItem).nameEn,
                    player.inventory.count(player.quickItem), player.buffRemaining());
        }
        if (activeBoss != null && !activeBoss.dead()) {
            hud.bossBar(activeBoss.def.nameEn, activeBoss.stats.healthFraction(),
                    activeBoss.getPhase(), activeBoss.phaseCount());
            if (bossBannerTimer > 0f) {
                bossBannerTimer -= Gdx.graphics.getDeltaTime();
                hud.centreText(activeBoss.def.nameEn.toUpperCase(),
                        Math.min(1f, bossBannerTimer), 2.4f);
            }
        } else if (lockedEnemy != null && !lockedEnemy.dead()) {
            hud.enemyBar(lockedEnemy.def.nameEn, lockedEnemy.stats.healthFraction());
        }
        if (toastTimer > 0f) hud.toast(toast, Math.min(1f, toastTimer));

        Npc near = npcInReach();
        if (near != null && activeArena == null) {
            hud.prompt("Talk to " + near.def.nameEn + "   [E]");
        }

        if (areaBannerTimer > 0f && activeBoss == null) {
            hud.areaTitle(level.nameEn, Math.min(1f, areaBannerTimer));
        }
        Portal prompt = portalPrompt();
        if (prompt != null && activeArena == null) {
            hud.prompt(prompt.requiresInteract
                    ? prompt.labelEn + "   [E]" : prompt.labelEn);
        }

        if (player.dead()) {
            float t = MathUtils.clamp(deathTimer / DEATH_FADE, 0f, 1f);
            hud.overlay(0f, 0f, 0f, Math.min(0.82f, t * 1.6f));
            hud.centreText("YOU DIED", Math.min(1f, t * 2.2f), 3.2f);
        }
    }

    private void renderScene() {
        renderer.beginScene(level.fogColor.r, level.fogColor.g, level.fogColor.b);
        level.renderables(renderList);
        renderList.add(player.rig.instance);
        if (weaponInstance != null) {
            player.rig.weaponTransform(weaponTransform);
            weaponInstance.transform.set(weaponTransform);
            renderList.add(weaponInstance);
        }
        for (Enemy enemy : enemies) renderList.add(enemy.visual.instance());
        for (Npc npc : npcs) renderList.add(npc.visual.instance());
        for (Pickup pickup : pickups) renderList.add(pickup.instance);
        renderer.renderScene(camera.camera, renderList);
        renderer.endScene();
        renderer.present();
    }

    private int aliveEnemies() {
        int n = 0;
        for (Enemy e : enemies) if (!e.dead()) n++;
        return n;
    }

    private void gatherInput(float dt) {
        if (game.autopilot) {
            driveAutopilot();
            return;
        }
        if (desktopControls != null) {
            desktopControls.update(controls);
            // Escape releases the mouse rather than quitting, so the window stays usable.
            if (controls.pausePressed) {
                Gdx.input.setCursorCatched(!Gdx.input.isCursorCatched());
            }
            if (Gdx.input.isKeyJustPressed(Input.Keys.F3)) hud.showDebug = !hud.showDebug;
            // Weapon and upgrade cycling, for trying the armoury out.
            if (Gdx.input.isKeyJustPressed(Input.Keys.TAB)) cycleWeapon(1);
            if (Gdx.input.isKeyJustPressed(Input.Keys.GRAVE)) cycleWeapon(-1);
            if (Gdx.input.isKeyJustPressed(Input.Keys.EQUALS)) upgradeWeapon(1);
            if (Gdx.input.isKeyJustPressed(Input.Keys.MINUS)) upgradeWeapon(-1);
        }
        if (touchControls != null) touchControls.update(controls, dt);
    }

    private void cycleWeapon(int direction) {
        Array<WeaponDef> all = game.weapons.all();
        weaponIndex = Math.floorMod(weaponIndex + direction, all.size);
        equip(all.get(weaponIndex));
        showToast(weapon.displayName(false) + "  (" + weapon.weaponClass + ")");
    }

    private void upgradeWeapon(int delta) {
        weapon.upgrade = MathUtils.clamp(weapon.upgrade + delta, 0, 10);
        showToast(weapon.displayName(false));
    }

    private void showToast(String text) {
        toast = text;
        toastTimer = 2.2f;
    }

    /**
     * A fixed input script: sprint forward, sweep the camera, roll, and attack.
     * Enough to exercise locomotion, the collision resolver and the combat
     * pipeline without a human at the controls.
     */
    private void driveAutopilot() {
        float t = elapsed;

        // Hunt the nearest live enemy so the smoke test actually exercises
        // approach, lock-on, swinging, taking hits and dying - a script that only
        // wanders proves the renderer works and nothing else.
        Enemy quarry = null;
        float best = Float.MAX_VALUE;
        for (Enemy enemy : enemies) {
            if (enemy.dead()) continue;
            float d = enemy.body.position.dst(player.body.position);
            if (d < best) { best = d; quarry = enemy; }
        }

        if (quarry != null) {
            tmp.set(quarry.body.position).sub(player.body.position);
            tmp.y = 0f;
            float heading = MathUtils.atan2(tmp.x, tmp.z) * MathUtils.radiansToDegrees;
            // Steer the camera behind the player's intended heading, then walk
            // straight ahead - the same thing a human does.
            float want = heading + 180f;
            float turn = ((want - camera.yaw) % 360f + 540f) % 360f - 180f;
            controls.look.add(MathUtils.clamp(turn, -6f, 6f), 0f);
            controls.move.set(0f, 1f);
            controls.sprintHeld = best > 6f;

            if (lockedEnemy == null && best < Config.CAM_LOCK_RANGE) {
                controls.lockOnPressed = true;
            }
            if (best < 2.6f) {
                controls.attackLightPressed |= (t % 0.9f) < 0.02f;
                controls.attackHeavyPressed |= (t % 3.7f) < 0.02f;
                controls.guardHeld = (t % 5f) > 4f;
            }
        } else {
            controls.move.set(MathUtils.sinDeg(t * 47f) * 0.55f, 1f);
            controls.sprintHeld = (t % 6f) < 3.5f;
            controls.look.add(MathUtils.sin(t * 0.7f) * 0.9f, 0f);
        }

        // Roll on a fixed cadence regardless, to keep exercising i-frames.
        float phase = t % 4f;
        boolean rollNow = phase >= 3.9f;
        controls.rollPressed |= rollNow && !autopilotRolled;
        autopilotRolled = rollNow;
    }

    private void simulate(float dt) {
        game.audio.setListener(player.body.position);
        camera.applyLook(controls.look.x, controls.look.y);
        // Look deltas are consumed by the first substep; later substeps get zero.
        controls.look.setZero();

        if (areaBannerTimer > 0f && activeBoss == null) {
            hud.areaTitle(level.nameEn, Math.min(1f, areaBannerTimer));
        }
        Portal prompt = portalPrompt();
        if (prompt != null && activeArena == null) {
            hud.prompt(prompt.requiresInteract
                    ? prompt.labelEn + "   [E]" : prompt.labelEn);
        }

        if (player.dead()) {
            deathTimer += dt;
            player.update(controls, level.collision, camera.yaw, null, dt);
            for (Enemy enemy : enemies) enemy.update(level.collision, dt);
            if (deathTimer >= DEATH_FADE) respawn();
            return;
        }

        if (controls.lockOnPressed) toggleLockOn();
        if (lockedEnemy != null && (lockedEnemy.dead() || tooFarToLock(lockedEnemy))) {
            clearLockOn();
        }

        if (controls.cycleItemPressed) cycleQuickItem();
        if (controls.usePressed) useQuickItem();
        if (controls.interactPressed) {
            Npc near = npcInReach();
            if (near != null) startConversation(near);
            else tryRest();
        }

        Vector3 lockTarget = null;
        if (lockedEnemy != null) {
            lockedEnemy.hitCenter(lockPoint);
            lockTarget = lockPoint;
        }

        player.update(controls, level.collision, camera.yaw, lockTarget, dt);

        for (Enemy enemy : enemies) {
            enemy.update(level.collision, dt);
            long reward = enemy.claimSouls();
            if (reward > 0) {
                player.stats.souls += reward;
                showToast("+" + reward);
                game.audio.play(SoundBank.SOULS, 0.7f, Audio.vary(0.05f));
                dropLoot(enemy);
            }
        }

        updatePickups(dt);

        updateBossFight(dt);
        collectBloodstain();
        // Portals are disabled mid-boss: the arena is sealed for a reason.
        if (activeArena == null) checkPortals();

        // Falling out of the world should never be unrecoverable.
        if (player.body.position.y < -25f) {
            player.spawn(level.spawn.x, level.spawn.y, level.spawn.z, level.spawnFacing);
            camera.snapTo(player.body.position);
        }
    }

    /**
     * Fog gates, arena sealing and the boss itself.
     *
     * The barrier goes up the moment the fight starts and comes down the moment
     * it ends - a boss you can walk away from is not a boss, and one you cannot
     * leave after killing is a bug.
     */
    private void updateBossFight(float dt) {
        for (BossArena arena : level.arenas) {
            arena.update(dt);
            if (arena.isCleared() || arena.isActive()) continue;
            if (arena.checkEntry(player.body.position)) beginBossFight(arena);
        }

        if (activeArena == null) return;

        if (activeBoss != null && activeBoss.dead()) {
            endBossFight(true);
            return;
        }
        // Dying mid-fight resets the encounter, same as the genre.
        if (player.dead()) endBossFight(false);
    }

    private void beginBossFight(BossArena arena) {
        activeArena = arena;
        activeBoss = addEnemy(game.bestiary.get(arena.bossId),
                arena.bossSpawn.x, arena.bossSpawn.z, 180f);
        refreshCombatants();
        // Seal the arena by layering its barrier onto the level collision.
        level.collision.setOverlay(arena.barrier());
        bossBannerTimer = 3.2f;
        clearLockOn();
        game.audio.play(SoundBank.FOG_GATE, 0.8f, 1f);
        game.audio.play(SoundBank.BOSS_ROAR, 1f, 1f);
        game.audio.playMusic(SoundBank.MUSIC_BOSS);
    }

    private void endBossFight(boolean defeated) {
        if (activeArena == null) return;
        level.collision.setOverlay(null);
        if (defeated) {
            activeArena.clear();
            showToast("GREAT SOUL RELEASED");
        } else {
            // The player died: reset the gate so the fight can be taken again.
            activeArena.markDormant();
            if (activeBoss != null) {
                enemies.removeValue(activeBoss, true);
                activeBoss.visual.dispose();
                refreshCombatants();
            }
        }
        activeArena = null;
        activeBoss = null;
        bossBannerTimer = 0f;
        // Back to wind. The bed is what tells the player the fight is over, well
        // before the health bar has finished draining off the screen.
        game.audio.playMusic(SoundBank.AMBIENCE_WIND);
    }

    private boolean tooFarToLock(Enemy enemy) {
        return enemy.body.position.dst(player.body.position) > Config.CAM_LOCK_RANGE * 1.35f;
    }

    /** Locks on to the nearest live enemy in front of the camera, or releases. */
    private void toggleLockOn() {
        if (lockedEnemy != null) {
            clearLockOn();
            return;
        }
        Enemy best = null;
        float bestScore = Float.MAX_VALUE;
        for (Enemy enemy : enemies) {
            if (enemy.dead()) continue;
            tmp.set(enemy.body.position).sub(player.body.position);
            float distance = tmp.len();
            if (distance > Config.CAM_LOCK_RANGE) continue;
            // Prefer targets near the middle of the screen, not just the closest.
            float heading = MathUtils.atan2(tmp.x, tmp.z) * MathUtils.radiansToDegrees;
            float offAxis = Math.abs(((heading - camera.groundYaw()) % 360f + 540f) % 360f - 180f);
            float score = distance + offAxis * 0.08f;
            if (score < bestScore) {
                bestScore = score;
                best = enemy;
            }
        }
        if (best != null) {
            lockedEnemy = best;
            best.hitCenter(lockPoint);
            camera.setLockTarget(lockPoint);
        }
    }

    private void clearLockOn() {
        lockedEnemy = null;
        camera.setLockTarget(null);
    }

    private void drinkEstus() {
        if (estus <= 0 || player.stats.health >= player.stats.maxHealth) return;
        estus--;
        game.audio.play(SoundBank.DRINK, 0.85f, 1f);
        player.stats.heal(player.stats.maxHealth * ESTUS_HEAL_FRACTION);
        showToast("Estus " + estus + "/" + estusMax);
    }

    // ---- loot -------------------------------------------------------------

    /**
     * Rolls what an enemy dropped and puts it on the ground.
     *
     * Drops land beside the corpse rather than going straight into the pack, so
     * a kill on a ledge can still cost you the reward. Fanning them out means a
     * three-item table is three shards you can see, not one on top of another.
     */
    private void dropLoot(Enemy enemy) {
        rolled.clear();
        enemy.def.loot.roll(this.loot, rolled);
        if (rolled.size == 0) return;

        Vector3 at = enemy.body.position;
        for (int i = 0; i < rolled.size; i++) {
            LootTable.Drop drop = rolled.get(i);
            if (!game.items.has(drop.itemId)) continue;
            float angle = i * 360f / Math.max(1, rolled.size) + 25f;
            float spread = rolled.size == 1 ? 0f : 0.55f;
            Pickup pickup = new Pickup(drop.itemId, drop.count,
                    at.x + MathUtils.cosDeg(angle) * spread, at.y,
                    at.z + MathUtils.sinDeg(angle) * spread, pickupModel);
            pickup.tint(com.badlogic.gdx.graphics.Color.valueOf(
                    game.items.get(drop.itemId).glow));
            pickups.add(pickup);
        }
    }

    private void updatePickups(float dt) {
        for (int i = pickups.size - 1; i >= 0; i--) {
            Pickup pickup = pickups.get(i);
            pickup.update(dt);
            if (!pickup.inReach(player.body.position)) continue;

            ItemDef def = game.items.get(pickup.itemId);
            int taken = player.inventory.add(def, pickup.count);
            if (taken <= 0) {
                // Full stack. Leave it lying there rather than silently binning it.
                continue;
            }
            // Picking anything up when the quick slot is empty arms it, so the
            // first consumable found is usable without opening a menu.
            if (def.consumable() && player.quickItem.isEmpty()) player.quickItem = def.id;
            showToast(def.nameEn + (taken > 1 ? " x" + taken : ""));
            game.audio.play(SoundBank.PICKUP, 0.8f, Audio.vary(0.06f));
            pickups.removeIndex(i);
        }
    }

    // ---- items ------------------------------------------------------------

    /** Steps the quick slot through the consumables being carried. */
    private void cycleQuickItem() {
        Array<String> held = player.inventory.ids();
        int start = held.indexOf(player.quickItem, false);
        for (int step = 1; step <= held.size; step++) {
            String id = held.get(Math.floorMod(start + step, held.size));
            if (!game.items.get(id).consumable()) continue;
            player.quickItem = id;
            showToast(game.items.get(id).nameEn
                    + " x" + player.inventory.count(id));
            return;
        }
        // Nothing else to switch to: fall back to the flask.
        player.quickItem = "";
        showToast("Estus " + estus + "/" + estusMax);
    }

    /**
     * Spends the quick slot. An empty slot, or one holding something no longer
     * carried, drinks Estus - the use button must never do nothing.
     */
    private void useQuickItem() {
        String id = player.quickItem;
        if (id.isEmpty() || !player.inventory.has(id, 1)) {
            player.quickItem = "";
            drinkEstus();
            return;
        }
        ItemDef def = game.items.get(id);
        if (!def.consumable() || !applyItem(def)) return;
        player.inventory.remove(id, 1);
        if (!player.inventory.has(id, 1)) player.quickItem = "";
    }

    /** @return false if the item would have done nothing, so it is not spent. */
    private boolean applyItem(ItemDef def) {
        switch (def.effect) {
            case HEAL:
                if (player.stats.health >= player.stats.maxHealth) return false;
                player.stats.heal(def.power);
                showToast(def.nameEn);
                return true;
            case STAMINA:
                if (player.stats.stamina >= player.stats.maxStamina) return false;
                player.stats.stamina = Math.min(player.stats.maxStamina,
                        player.stats.stamina + def.power);
                showToast(def.nameEn);
                return true;
            case BUFF:
                player.applyBuff(def.power, def.duration);
                showToast(def.nameEn + " +" + Math.round(def.power));
                return true;
            case SOULS:
                player.stats.souls += (long) def.power;
                showToast("+" + Math.round(def.power));
                return true;
            case FLASK:
                estusMax += (int) def.power;
                estus += (int) def.power;
                showToast("Estus " + estus + "/" + estusMax);
                writeSave();
                return true;
            case HOMEWARD:
                if (activeArena != null) {
                    // The arena is sealed. A bone out of a boss fight would be an
                    // escape hatch, and the whole point of the fog gate is that
                    // there is not one.
                    showToast("Not here");
                    return false;
                }
                goHome();
                return true;
            default:
                return false;
        }
    }

    /** Homeward bone: back to the bonfire, wherever in the world it is. */
    private void goHome() {
        if (!bonfireArea.equals(currentArea)) {
            tmp.set(bonfire.x, bonfire.y + 0.2f, bonfire.z + 2f);
            enterArea(bonfireArea, tmp, 180f);
        } else {
            player.spawn(bonfire.x, bonfire.y + 0.2f, bonfire.z + 2f, 180f);
            camera.yaw = 0f;
            camera.snapTo(player.body.position);
        }
        showToast("Homeward");
        writeSave();
    }

    // ---- people -----------------------------------------------------------

    private void spawnNpcs() {
        game.npcs.inArea(currentArea, npcDefs);
        for (NpcDef def : npcDefs) {
            npcs.add(new Npc(def, BodyFactory.create(def.body, game.textures, 3f)));
        }
    }

    /** The character close enough to talk to, or null. */
    private Npc npcInReach() {
        for (Npc npc : npcs) {
            if (npc.inRange(player.body.position)) return npc;
        }
        return null;
    }

    /** Screenshot harness: drops straight into a named character's conversation. */
    private void openConversationById(String npcId) {
        for (Npc npc : npcs) {
            if (!npc.def.id.equals(npcId)) continue;
            if (game.openShopOnStart && npc.def.isMerchant()) {
                talkingTo = npc;
                shop.open(npc.def);
            } else {
                startConversation(npc);
            }
            return;
        }
    }

    private void startConversation(Npc npc) {
        talkingTo = npc;
        showLine(npc);
    }

    private void showLine(Npc npc) {
        NpcDef.Line line = npc.currentLine();
        if (line == null) {
            openShopOrLeave(npc);
            return;
        }
        String hint = npc.saidEverything()
                ? (npc.def.isMerchant() ? "[E] trade" : "[E] leave")
                : "[E]";
        dialogue.show(npc.def.nameEn, line.en, hint);
    }

    /**
     * Advances the conversation.
     *
     * The first press finishes the line being typed out; only a press against a
     * fully-shown line moves on. A player who reads faster than the reveal
     * should never lose a sentence for pressing on time.
     */
    private void updateConversation(float dt) {
        dialogue.update(dt);
        boolean advance = Gdx.input.isKeyJustPressed(Input.Keys.E)
                || Gdx.input.isKeyJustPressed(Input.Keys.ENTER)
                || Gdx.input.isKeyJustPressed(Input.Keys.SPACE)
                || justTapped();
        if (Gdx.input.isKeyJustPressed(Input.Keys.ESCAPE)) {
            endConversation();
            return;
        }
        if (!advance) return;
        if (!dialogue.isFullyRevealed()) {
            dialogue.revealAll();
            return;
        }
        if (talkingTo == null) {
            endConversation();
            return;
        }
        if (talkingTo.advance()) {
            showLine(talkingTo);
            if (game.audio != null) game.audio.play(SoundBank.MENU_MOVE, 0.6f, 0.85f);
        } else {
            openShopOrLeave(talkingTo);
        }
    }

    private void openShopOrLeave(Npc npc) {
        if (npc.def.isMerchant()) {
            dialogue.close();
            shop.open(npc.def);
        } else {
            endConversation();
        }
    }

    private void endConversation() {
        dialogue.close();
        shop.close();
        talkingTo = null;
        // Swallow the press that closed it, so the same tap does not immediately
        // reopen the conversation on the next frame.
        controls.reset();
    }

    /** A fresh screen tap, used to advance dialogue on a phone. */
    private boolean justTapped() {
        boolean touched = Gdx.input.isTouched();
        boolean tapped = touched && !dialogueWasTouched;
        dialogueWasTouched = touched;
        return tapped;
    }

    private boolean dialogueWasTouched;

    /** Interacting near a bonfire opens its menu rather than resting outright. */
    private void tryRest() {
        Vector3 nearest = level.nearestBonfire(player.body.position);
        if (nearest == null || player.body.position.dst(nearest) > BONFIRE_RANGE) return;
        // Sitting at a new bonfire makes it the one you come back to.
        bonfire.set(nearest);
        bonfireArea = currentArea;
        menu.open();
    }

    /** Resting refills health and Estus, brings every enemy back, and saves. */
    private void rest() {
        player.stats.health = player.stats.maxHealth;
        player.stats.stamina = player.stats.maxStamina;
        // A resin does not survive a rest; otherwise the optimal play is to buff
        // at the fire before every run, and the item stops being a decision.
        player.clearBuff();
        estus = estusMax;
        respawnEnemies();
        writeSave();
        game.audio.play(SoundBank.BONFIRE_REST, 0.9f, 1f);
        showToast("Rested");
    }

    /** Rebuilds the area's population from the level data, as a rest should. */
    private void respawnEnemies() {
        endBossFight(false);
        for (Enemy enemy : enemies) enemy.visual.dispose();
        enemies.clear();
        spawnEnemies();
        clearLockOn();
    }

    /** Souls are dropped where you died and can be picked back up - once. */
    private void collectBloodstain() {
        if (!hasBloodstain) return;
        if (player.body.position.dst(bloodstain) > 1.8f) return;
        player.stats.souls += bloodstainSouls;
        showToast("Recovered " + bloodstainSouls);
        hasBloodstain = false;
        bloodstainSouls = 0;
    }

    private void respawn() {
        bloodstain.set(player.body.position);
        bloodstainSouls = player.stats.souls;
        hasBloodstain = bloodstainSouls > 0;
        player.stats.souls = 0;

        estus = estusMax;
        player.clearBuff();
        deathTimer = 0f;
        save.deaths++;
        if (!bonfireArea.equals(currentArea)) {
            tmp.set(bonfire.x, bonfire.y + 0.2f, bonfire.z + 2f);
            enterArea(bonfireArea, tmp, 180f);
        } else {
            player.spawn(bonfire.x, bonfire.y + 0.2f, bonfire.z + 2f, 180f);
            respawnEnemies();
            camera.snapTo(player.body.position);
        }
        // Save on death, so the souls you just lost stay lost. Anything else and
        // dying could be undone by closing the app.
        writeSave();
    }

    @Override
    public void resize(int width, int height) {
        if (width == 0 || height == 0) return;
        renderer.onDisplayResize(width, height);
        camera.setAspect(renderer.aspectRatio());
        hud.resize(width, height);
        if (touchControls != null) touchControls.updateProjection(width, height);
    }

    @Override
    public void hide() {
        if (desktopControls != null) Gdx.input.setCursorCatched(false);
        writeSave();
    }

    @Override
    public void dispose() {
        writeSave();
        for (Npc npc : npcs) npc.dispose();
        npcs.clear();
        if (dialogue != null) dialogue.dispose();
        if (shop != null) shop.dispose();
        if (menu != null) menu.dispose();
        if (pickupModel != null) pickupModel.dispose();
        if (renderer != null) renderer.dispose();
        if (level != null) level.dispose();
        if (hud != null) hud.dispose();
        if (touchControls != null) touchControls.dispose();
        if (player != null) player.rig.model.dispose();
        if (weaponModel != null) weaponModel.dispose();
        for (Enemy enemy : enemies) enemy.visual.dispose();
        enemies.clear();
    }

    /** Exposed for the smoke test so it can assert the world actually loaded. */
    public int collisionTriangleCount() {
        return level != null ? level.collision.triangleCount() : 0;
    }

    public float elapsedTime() {
        return elapsed;
    }

    public RetroRenderer getRenderer() {
        return renderer;
    }
}
