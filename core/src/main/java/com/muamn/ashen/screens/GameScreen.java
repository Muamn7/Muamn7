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
import com.muamn.ashen.camera.OrbitCamera;
import com.muamn.ashen.combat.Combatant;
import com.muamn.ashen.combat.WeaponDef;
import com.muamn.ashen.combat.WeaponFactory;
import com.muamn.ashen.entity.AnimatedVisual;
import com.muamn.ashen.entity.CharacterRig;
import com.muamn.ashen.entity.Enemy;
import com.muamn.ashen.entity.EnemyDef;
import com.muamn.ashen.entity.EnemyVisual;
import com.muamn.ashen.entity.HumanoidFactory;
import com.muamn.ashen.entity.HumanoidSpec;
import com.muamn.ashen.entity.Player;
import com.muamn.ashen.entity.RigVisual;
import com.muamn.ashen.input.ControlState;
import com.muamn.ashen.input.DesktopControls;
import com.muamn.ashen.input.TouchControls;
import com.muamn.ashen.render.RetroRenderer;
import com.muamn.ashen.render.RetroShader;
import com.muamn.ashen.save.SaveData;
import com.muamn.ashen.save.SaveGame;
import com.muamn.ashen.ui.BonfireMenu;
import com.muamn.ashen.ui.Hud;
import com.muamn.ashen.world.AssetOverrides;
import com.muamn.ashen.world.Level;
import com.muamn.ashen.world.Levels;

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

    private final SaveGame saveGame = new SaveGame();
    private SaveData save;
    private final BonfireMenu menu = new BonfireMenu();

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

        level = Levels.asylumCourtyard(game.textures);
        applyLevelMood();

        HumanoidSpec spec = HumanoidSpec.knight();
        CharacterRig rig = new CharacterRig(
                HumanoidFactory.build(spec, game.textures, "player"), spec);

        save = saveGame.load();
        weaponIndex = indexOfWeapon(save.weaponId);
        weapon = game.weapons.all().get(weaponIndex);
        weapon.upgrade = MathUtils.clamp(save.weaponUpgrade, 0, 10);

        player = new Player(rig, weapon);
        applySave(save);
        equip(weapon);

        bonfire.set(save.bonfireX, save.bonfireY, save.bonfireZ);
        player.spawn(bonfire.x, bonfire.y + 0.2f, bonfire.z + 2f, 180f);

        spawnEnemies();

        camera = new OrbitCamera(renderer.aspectRatio());
        camera.distance = game.cameraDistance;
        camera.yaw = level.spawnFacing + 180f + game.cameraYawOffset;
        camera.snapTo(player.body.position);

        hud = new Hud();
        hud.resize(Gdx.graphics.getWidth(), Gdx.graphics.getHeight());
        hud.showDebug = game.debugOverlay;

        if (game.openMenuOnStart) menu.open(game.menuPage);

        if (isTouchPlatform()) {
            touchControls = new TouchControls();
            touchControls.updateProjection(Gdx.graphics.getWidth(), Gdx.graphics.getHeight());
        } else {
            desktopControls = new DesktopControls();
            Gdx.input.setCursorCatched(true);
        }
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

        save.bonfireId = level.id;
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
        // The imported rig if it is present, otherwise the procedural hollow -
        // the level must populate either way.
        EnemyDef reaperDef = EnemyDef.reaper();
        if (AssetOverrides.hasModel(reaperDef.modelName)) {
            addEnemy(reaperDef, 3f, -18f, 200f);
        } else {
            addEnemy(EnemyDef.hollowSoldier(), 3f, -18f, 200f);
        }
        addEnemy(EnemyDef.hollowSoldier(), -8f, -16f, 60f);
        addEnemy(EnemyDef.hollowSoldier(), 10f, 6f, 250f);

        combatants.clear();
        combatants.add(player);
        for (Enemy e : enemies) combatants.add(e);
        player.setTargets(combatants);
    }

    private void addEnemy(EnemyDef def, float x, float z, float facing) {
        EnemyVisual visual;
        Model imported = def.modelName != null ? AssetOverrides.loadModel(def.modelName) : null;
        if (imported != null && imported.animations.size > 0) {
            visual = new AnimatedVisual(imported, 1f);
        } else {
            if (imported != null) imported.dispose();
            HumanoidSpec spec = HumanoidSpec.hollow();
            visual = new RigVisual(
                    new CharacterRig(HumanoidFactory.build(spec, game.textures, null), spec),
                    def.runSpeed);
        }
        Enemy enemy = new Enemy(def, visual, game.weapons.get(def.weaponId));
        enemy.spawn(x, 0.2f, z, facing);
        enemy.setTarget(player);
        enemies.add(enemy);
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

        // The menu owns input and freezes the world while it is up.
        if (menu.isOpen()) {
            menu.update(dt, player, weapon, this::rest);
            controls.reset();
            camera.update(player.body.position, level.collision, dt);
            hud.update(player.stats, dt);
            renderScene();
            renderHud();
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

        camera.update(player.body.position, level.collision, dt);
        hud.update(player.stats, dt);

        renderScene();
        renderHud();
        if (touchControls != null) touchControls.render();

        controls.clearEdges();
    }

    private void renderHud() {
        if (menu.isOpen()) {
            hud.render(player.stats);
            menu.render(player, weapon);
            return;
        }
        if (hud.showDebug) {
            hud.setDebugLine(String.format(
                    "fps %d | %s | %s +%d | spd %.1f | souls %d | estus %d | enemies %d",
                    Gdx.graphics.getFramesPerSecond(), player.getState(),
                    weapon.nameEn, weapon.upgrade, player.groundSpeed(),
                    player.stats.souls, estus, aliveEnemies()));
        }
        hud.render(player.stats);
        if (lockedEnemy != null && !lockedEnemy.dead()) {
            hud.enemyBar(lockedEnemy.def.nameEn, lockedEnemy.stats.healthFraction());
        }
        if (toastTimer > 0f) hud.toast(toast, Math.min(1f, toastTimer));

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
        camera.applyLook(controls.look.x, controls.look.y);
        // Look deltas are consumed by the first substep; later substeps get zero.
        controls.look.setZero();

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

        if (controls.usePressed) drinkEstus();
        if (controls.interactPressed) tryRest();

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
            }
        }

        collectBloodstain();

        // Falling out of the world should never be unrecoverable.
        if (player.body.position.y < -25f) {
            player.spawn(level.spawn.x, level.spawn.y, level.spawn.z, level.spawnFacing);
            camera.snapTo(player.body.position);
        }
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
        player.stats.heal(player.stats.maxHealth * ESTUS_HEAL_FRACTION);
        showToast("Estus " + estus + "/" + estusMax);
    }

    /** Interacting near a bonfire opens its menu rather than resting outright. */
    private void tryRest() {
        if (player.body.position.dst(bonfire) > BONFIRE_RANGE) return;
        menu.open();
    }

    /** Resting refills health and Estus, brings every enemy back, and saves. */
    private void rest() {
        player.stats.health = player.stats.maxHealth;
        player.stats.stamina = player.stats.maxStamina;
        estus = estusMax;
        respawnEnemies();
        writeSave();
        showToast("Rested");
    }

    private void respawnEnemies() {
        for (Enemy enemy : enemies) {
            enemy.spawn(enemy.body.position.x, enemy.body.position.y, enemy.body.position.z,
                    enemy.facing());
            enemy.setTarget(player);
        }
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

        player.spawn(bonfire.x, bonfire.y + 0.2f, bonfire.z + 2f, 180f);
        estus = estusMax;
        deathTimer = 0f;
        save.deaths++;
        respawnEnemies();
        camera.snapTo(player.body.position);
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
        menu.dispose();
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
