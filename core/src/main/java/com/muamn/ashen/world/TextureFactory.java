package com.muamn.ashen.world;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.Pixmap;
import com.badlogic.gdx.graphics.Texture;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.utils.Disposable;
import com.badlogic.gdx.utils.ObjectMap;

/**
 * Builds every texture in the game from code.
 *
 * The asset hosts this project would normally pull CC0 packs from are blocked in
 * the build sandbox, and generated textures turn out to be a good fit anyway: the
 * target look is 64x64, 32-colour, point-filtered and tiling, which is exactly
 * what a few octaves of value noise plus a fixed palette produce. Drop a PNG of
 * the same name into {@code assets/imported/textures/} and it is used instead -
 * see {@link AssetOverrides}.
 */
public class TextureFactory implements Disposable {

    /** PS2-era texture budget. Anything bigger just costs bandwidth. */
    public static final int SIZE = 64;

    private final ObjectMap<String, Texture> cache = new ObjectMap<>();

    public Texture get(String name) {
        Texture existing = cache.get(name);
        if (existing != null) return existing;

        Texture imported = AssetOverrides.loadTexture(name);
        Texture tex = imported != null ? imported : fromPixmap(generate(name));
        tex.setFilter(Texture.TextureFilter.Nearest, Texture.TextureFilter.Nearest);
        tex.setWrap(Texture.TextureWrap.Repeat, Texture.TextureWrap.Repeat);
        cache.put(name, tex);
        return tex;
    }

    private static Texture fromPixmap(Pixmap px) {
        Texture t = new Texture(px);
        px.dispose();
        return t;
    }

    /** Dispatches to the generator for a named material. */
    private Pixmap generate(String name) {
        switch (name) {
            case "stone":       return stone(0x5A5750, 0x3A3833, 7411, 0.22f);
            case "stone_dark":  return stone(0x3B3A36, 0x232220, 991, 0.26f);
            case "brick":       return brick(0x6B5F4E, 0x4A4034, 0x2A2621);
            case "cobble":      return cobble(0x59564E, 0x393732, 0x22211E);
            case "ash":         return ground(0x6E6A62, 0x4C4941, 0x8A867C, 313);
            case "dirt":        return ground(0x53483A, 0x3A3229, 0x6A5C49, 77);
            case "grass_dead":  return ground(0x555038, 0x3B3828, 0x6C6644, 4242);
            case "wood":        return wood(0x53412C, 0x35291B);
            case "iron":        return metal(0x6E7276, 0x44484C, 1201);
            case "steel":       return metal(0x9AA0A8, 0x60666E, 88);
            case "gold":        return metal(0xB9913E, 0x6E5522, 51);
            case "cloth_red":   return cloth(0x6E2320, 0x431614);
            case "cloth_dark":  return cloth(0x2A2A30, 0x17171C);
            case "leather":     return cloth(0x4A3A28, 0x2C2218);
            case "skin_pale":   return flat(0xA89486, 0x8C7A6C, 909);
            case "flesh_rot":   return flat(0x6A6A54, 0x4C4C3C, 1717);
            case "bone":        return flat(0xC9C2AC, 0x9C947E, 6161);
            case "ember":       return ember();
            case "fog_gate":    return fogGate();
            case "shadow":      return radialAlpha(0x000000, 0.55f);
            default:            return flat(0x808080, 0x606060, 1);
        }
    }

    // ---- Generators -------------------------------------------------------

    private Pixmap stone(int light, int dark, int seed, float grain) {
        Pixmap px = blank();
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                float n = fbm(x, y, seed, 4, 8f);
                float t = MathUtils.clamp(n + rand(x, y, seed) * grain - grain * 0.5f, 0f, 1f);
                px.drawPixel(x, y, rgba(lerpRgb(dark, light, t)));
            }
        }
        return px;
    }

    private Pixmap brick(int face, int faceAlt, int mortar) {
        Pixmap px = blank();
        int rowH = 16, brickW = 32, mortarPx = 2;
        for (int y = 0; y < SIZE; y++) {
            int row = y / rowH;
            int offset = (row % 2) * (brickW / 2);
            for (int x = 0; x < SIZE; x++) {
                int bx = (x + offset) % brickW;
                int by = y % rowH;
                boolean isMortar = bx < mortarPx || by < mortarPx;
                int base;
                if (isMortar) {
                    base = mortar;
                } else {
                    // Alternate brick tint by cell so the wall does not look stamped.
                    int cell = ((x + offset) / brickW) * 31 + row * 17;
                    base = (cell % 3 == 0) ? faceAlt : face;
                }
                float n = fbm(x, y, 2024, 3, 16f) * 0.35f + 0.65f;
                px.drawPixel(x, y, rgba(scaleRgb(base, n)));
            }
        }
        return px;
    }

    private Pixmap cobble(int light, int mid, int gap) {
        Pixmap px = blank();
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                // Cell-noise style stones with jittered centres.
                float best = 1e9f, second = 1e9f;
                int cell = 8;
                int cx = x / cell, cy = y / cell;
                for (int oy = -1; oy <= 1; oy++) {
                    for (int ox = -1; ox <= 1; ox++) {
                        int gx = cx + ox, gy = cy + oy;
                        float px2 = (gx + rand(gx, gy, 5)) * cell;
                        float py2 = (gy + rand(gx, gy, 6)) * cell;
                        float d = (x - px2) * (x - px2) + (y - py2) * (y - py2);
                        if (d < best) { second = best; best = d; }
                        else if (d < second) { second = d; }
                    }
                }
                float edge = (float) (Math.sqrt(second) - Math.sqrt(best));
                int base = edge < 1.4f ? gap : lerpRgb(mid, light, MathUtils.clamp(edge / 6f, 0f, 1f));
                float n = fbm(x, y, 71, 3, 12f) * 0.3f + 0.7f;
                px.drawPixel(x, y, rgba(scaleRgb(base, n)));
            }
        }
        return px;
    }

    private Pixmap ground(int lo, int mid, int hi, int seed) {
        Pixmap px = blank();
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                float n = fbm(x, y, seed, 4, 6f);
                int c = n < 0.5f ? lerpRgb(mid, lo, 1f - n * 2f) : lerpRgb(mid, hi, (n - 0.5f) * 2f);
                // Speckle keeps flat ground from banding into visible plateaus.
                float speck = rand(x, y, seed + 1);
                if (speck > 0.94f) c = lerpRgb(c, hi, 0.5f);
                else if (speck < 0.05f) c = lerpRgb(c, lo, 0.5f);
                px.drawPixel(x, y, rgba(c));
            }
        }
        return px;
    }

    private Pixmap wood(int light, int dark) {
        Pixmap px = blank();
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                // Grain runs along +y, warped so the rings are not perfectly straight.
                float warp = fbm(x, y, 400, 3, 10f) * 6f;
                float rings = (float) Math.sin((x + warp) * 0.9f) * 0.5f + 0.5f;
                rings = rings * rings;
                int c = lerpRgb(dark, light, rings);
                if (x % 21 == 0) c = scaleRgb(c, 0.7f); // plank seams
                px.drawPixel(x, y, rgba(c));
            }
        }
        return px;
    }

    private Pixmap metal(int light, int dark, int seed) {
        Pixmap px = blank();
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                // Anisotropic streaks read as brushed/hammered metal at this size.
                float n = fbm(x * 0.35f, y * 3f, seed, 3, 8f);
                int c = lerpRgb(dark, light, n);
                float pit = rand(x, y, seed + 9);
                if (pit > 0.97f) c = scaleRgb(c, 0.55f);
                px.drawPixel(x, y, rgba(c));
            }
        }
        return px;
    }

    private Pixmap cloth(int light, int dark) {
        Pixmap px = blank();
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                boolean weave = ((x / 2) + (y / 2)) % 2 == 0;
                float n = fbm(x, y, 606, 3, 10f) * 0.4f + 0.6f;
                int c = lerpRgb(dark, light, weave ? 0.75f : 0.45f);
                px.drawPixel(x, y, rgba(scaleRgb(c, n)));
            }
        }
        return px;
    }

    private Pixmap flat(int light, int dark, int seed) {
        Pixmap px = blank();
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                float n = fbm(x, y, seed, 3, 9f);
                px.drawPixel(x, y, rgba(lerpRgb(dark, light, n)));
            }
        }
        return px;
    }

    private Pixmap ember() {
        Pixmap px = blank();
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                float n = fbm(x, y, 999, 4, 5f);
                int c = n > 0.62f ? 0xFFD24A : (n > 0.45f ? 0xE0761C : 0x8C2A08);
                px.drawPixel(x, y, rgba(c));
            }
        }
        return px;
    }

    /**
     * The boss fog wall: pale swirls that fade out top and bottom, so the gate
     * reads as a curtain of mist rather than a rectangle of texture.
     */
    private Pixmap fogGate() {
        Pixmap px = blank();
        Color col = new Color();
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                float swirl = fbm(x, y, 1234, 4, 4f);
                float band = fbm(x * 0.4f, y * 2.2f, 88, 3, 8f);
                float v = MathUtils.clamp(swirl * 0.65f + band * 0.55f, 0f, 1f);
                // Fade at the top and bottom edges so it blends into the arch.
                float edge = MathUtils.clamp(Math.min(y, SIZE - 1 - y) / (SIZE * 0.28f), 0f, 1f);
                float alpha = MathUtils.clamp(0.35f + v * 0.65f, 0f, 1f) * edge;
                col.set(0.78f + v * 0.20f, 0.82f + v * 0.16f, 0.88f, alpha);
                px.drawPixel(x, y, Color.rgba8888(col));
            }
        }
        return px;
    }

    /** Soft round blob used for the character's drop shadow. */
    private Pixmap radialAlpha(int rgb, float peak) {
        Pixmap px = blank();
        float c = (SIZE - 1) * 0.5f;
        Color col = new Color();
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                float d = (float) Math.sqrt((x - c) * (x - c) + (y - c) * (y - c)) / c;
                float a = MathUtils.clamp(1f - d, 0f, 1f);
                col.set(((rgb >> 16) & 0xFF) / 255f, ((rgb >> 8) & 0xFF) / 255f,
                        (rgb & 0xFF) / 255f, a * a * peak);
                px.drawPixel(x, y, Color.rgba8888(col));
            }
        }
        return px;
    }

    private static Pixmap blank() {
        Pixmap px = new Pixmap(SIZE, SIZE, Pixmap.Format.RGBA8888);
        px.setBlending(Pixmap.Blending.None);
        return px;
    }

    // ---- Noise ------------------------------------------------------------

    /** Deterministic hash in [0,1). No allocation, same result on every platform. */
    static float rand(float x, float y, int seed) {
        int h = seed * 374761393 + (int) (x * 668265263) + (int) (y * 2246822519L);
        h = (h ^ (h >>> 13)) * 1274126177;
        h = h ^ (h >>> 16);
        return (h & 0x00FFFFFF) / (float) 0x01000000;
    }

    /** Value noise with smoothstep interpolation, tiling every {@code period}. */
    private static float valueNoise(float x, float y, int seed, float period) {
        float xi = MathUtils.floor(x), yi = MathUtils.floor(y);
        float xf = x - xi, yf = y - yi;
        float u = xf * xf * (3f - 2f * xf);
        float v = yf * yf * (3f - 2f * yf);
        float x0 = wrap(xi, period), x1 = wrap(xi + 1, period);
        float y0 = wrap(yi, period), y1 = wrap(yi + 1, period);
        float a = rand(x0, y0, seed), b = rand(x1, y0, seed);
        float c = rand(x0, y1, seed), d = rand(x1, y1, seed);
        return MathUtils.lerp(MathUtils.lerp(a, b, u), MathUtils.lerp(c, d, u), v);
    }

    private static float wrap(float v, float period) {
        float r = v % period;
        return r < 0 ? r + period : r;
    }

    /**
     * Fractal noise in [0,1]. {@code cells} is how many noise cells span the
     * texture; keeping it an integer divisor of SIZE is what makes tiles seamless.
     */
    static float fbm(float x, float y, int seed, int octaves, float cells) {
        float sum = 0f, amp = 0.5f, total = 0f, freq = cells / SIZE;
        float period = cells;
        for (int i = 0; i < octaves; i++) {
            sum += valueNoise(x * freq, y * freq, seed + i * 131, period) * amp;
            total += amp;
            amp *= 0.5f;
            freq *= 2f;
            period *= 2f;
        }
        return sum / total;
    }

    // ---- Colour helpers ---------------------------------------------------

    private static int lerpRgb(int a, int b, float t) {
        t = MathUtils.clamp(t, 0f, 1f);
        int r = Math.round(((a >> 16) & 0xFF) + (((b >> 16) & 0xFF) - ((a >> 16) & 0xFF)) * t);
        int g = Math.round(((a >> 8) & 0xFF) + (((b >> 8) & 0xFF) - ((a >> 8) & 0xFF)) * t);
        int bl = Math.round((a & 0xFF) + ((b & 0xFF) - (a & 0xFF)) * t);
        return (r << 16) | (g << 8) | bl;
    }

    private static int scaleRgb(int c, float s) {
        int r = MathUtils.clamp(Math.round(((c >> 16) & 0xFF) * s), 0, 255);
        int g = MathUtils.clamp(Math.round(((c >> 8) & 0xFF) * s), 0, 255);
        int b = MathUtils.clamp(Math.round((c & 0xFF) * s), 0, 255);
        return (r << 16) | (g << 8) | b;
    }

    private static int rgba(int rgb) {
        return (rgb << 8) | 0xFF;
    }

    @Override
    public void dispose() {
        for (Texture t : cache.values()) t.dispose();
        cache.clear();
    }

    /** Writes every generated texture to disk. Debug aid, desktop only. */
    public void dumpAll(String dir) {
        String[] names = {"stone", "stone_dark", "brick", "cobble", "ash", "dirt",
                "grass_dead", "wood", "iron", "steel", "gold", "cloth_red",
                "cloth_dark", "leather", "skin_pale", "flesh_rot", "bone", "ember"};
        for (String n : names) {
            Pixmap px = generate(n);
            com.badlogic.gdx.graphics.PixmapIO.writePNG(Gdx.files.local(dir + "/" + n + ".png"), px);
            px.dispose();
        }
    }
}
