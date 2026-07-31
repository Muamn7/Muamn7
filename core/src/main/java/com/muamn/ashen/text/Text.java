package com.muamn.ashen.text;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.Texture;
import com.badlogic.gdx.graphics.g2d.BitmapFont;
import com.badlogic.gdx.graphics.g2d.Batch;
import com.badlogic.gdx.graphics.g2d.GlyphLayout;
import com.badlogic.gdx.graphics.g2d.freetype.FreeTypeFontGenerator;
import com.badlogic.gdx.utils.Disposable;

/**
 * All text drawing goes through here.
 *
 * Two things the rest of the game should not have to think about:
 *
 * <ul>
 *   <li><b>Shaping.</b> Every string is passed through {@link ArabicShaper} on
 *       the way to the batch. Latin text comes back untouched, so callers never
 *       branch on language.</li>
 *   <li><b>Measurement.</b> The UI used to guess widths as
 *       {@code length * 9 * scale}, which was close enough for a monospaced
 *       ASCII bitmap font and is nonsense for a proportional Arabic one. Widths
 *       come from a real {@link GlyphLayout} now, which is also what makes
 *       right-alignment possible at all.</li>
 * </ul>
 *
 * <h3>Two fonts, not one</h3>
 * Noto Naskh Arabic covers Arabic and digits and <em>no Latin letters at all</em>
 * - not one, upper or lower case. Drawing English through it produces a line of
 * numbers with the words silently missing, which is exactly what the first
 * build did. So Latin goes through libGDX's built-in bitmap font, which is
 * ASCII-only and is what this game used before, and Arabic goes through the
 * TTF. Each string picks its own by whether it contains Arabic.
 *
 * <h3>When there is no font</h3>
 * FreeType needs a native library. If it is missing, or the bundled TTF is,
 * everything falls back to the built-in font - which has no Arabic glyphs, so
 * the language is forced to English rather than drawing a screen of nothing.
 * A game in the wrong language is recoverable; a game with no legible text is
 * not.
 */
public final class Text implements Disposable {

    /** The bundled face. OFL-1.1; see CREDITS.md. */
    private static final String FONT_PATH = "fonts/NotoNaskhArabic-Regular.ttf";

    /** Rendered size of the atlas glyphs. Scaled down at draw time, never up. */
    private static final int BASE_SIZE = 34;
    /**
     * Cap height of libGDX's built-in font, near enough. Multiplying the Latin
     * font's scale by this keeps the two faces the same size on screen despite
     * being rasterised at very different resolutions.
     */
    private static final float LATIN_MATCH = BASE_SIZE / 15f;

    private FreeTypeFontGenerator generator;
    /** Arabic and digits. Null until {@link #load} succeeds. */
    private BitmapFont arabicFont;
    /** ASCII. Always present - it needs nothing but libGDX itself. */
    private BitmapFont latinFont;
    private boolean arabicCapable;

    private float scale = 1f;
    private final Color colour = new Color(1f, 1f, 1f, 1f);
    private final GlyphLayout layout = new GlyphLayout();

    /**
     * Loads the font. Never throws; a failure leaves the built-in font in place
     * and {@link #supportsArabic()} false.
     */
    public void load() {
        latinFont = new BitmapFont();
        try {
            if (!Gdx.files.internal(FONT_PATH).exists()) {
                throw new IllegalStateException("missing " + FONT_PATH);
            }
            generator = new FreeTypeFontGenerator(Gdx.files.internal(FONT_PATH));
            FreeTypeFontGenerator.FreeTypeFontParameter parameter =
                    new FreeTypeFontGenerator.FreeTypeFontParameter();
            parameter.size = BASE_SIZE;
            parameter.characters = glyphSet();
            parameter.magFilter = Texture.TextureFilter.Linear;
            parameter.minFilter = Texture.TextureFilter.Linear;
            // A dark outline keeps light text legible against fog and stone,
            // which most of this game's backgrounds are.
            parameter.borderWidth = 1.4f;
            parameter.borderColor = new Color(0f, 0f, 0f, 0.85f);
            parameter.borderStraight = false;
            parameter.shadowOffsetY = 1;
            parameter.shadowColor = new Color(0f, 0f, 0f, 0.5f);

            arabicFont = generator.generateFont(parameter);
            arabicCapable = true;
            Gdx.app.log("Text", "loaded " + FONT_PATH + " with "
                    + parameter.characters.length() + " glyphs");
        } catch (Throwable t) {
            // Throwable: a missing FreeType native surfaces as an
            // UnsatisfiedLinkError, and that must not take the game down.
            Gdx.app.error("Text", "no Arabic font - falling back to English", new Exception(t));
            arabicFont = null;
            arabicCapable = false;
            Strings.setLanguage(Strings.Language.ENGLISH);
        }
    }

    /**
     * The characters to rasterise.
     *
     * The whole Arabic Presentation Forms-B block rather than only the glyphs
     * the shipped strings happen to need, because item and area names come from
     * JSON and a designer adding a word should not have to think about the
     * atlas.
     */
    static String glyphSet() {
        StringBuilder sb = new StringBuilder();
        for (char c = 0x20; c <= 0x7E; c++) sb.append(c);        // printable ASCII
        for (char c = 0x0600; c <= 0x06FF; c++) sb.append(c);    // Arabic
        for (char c = 0xFB50; c <= 0xFBFF; c++) sb.append(c);    // Presentation Forms-A
        for (char c = 0xFE70; c <= 0xFEFC; c++) sb.append(c);    // Presentation Forms-B
        sb.append('—').append('–').append('«').append('»');
        return sb.toString();
    }

    public boolean supportsArabic() {
        return arabicCapable;
    }

    /**
     * The face that can actually draw this string.
     *
     * Arabic goes to the TTF; everything else to the built-in font, which is
     * the only one of the two with Latin letters in it.
     */
    private BitmapFont fontFor(String text) {
        if (arabicFont != null && ArabicShaper.hasArabic(text)) return arabicFont;
        return latinFont;
    }

    /** Applies the current scale and colour to whichever face is about to draw. */
    private BitmapFont prepare(String text) {
        BitmapFont font = fontFor(text);
        font.getData().setScale(font == latinFont ? scale * LATIN_MATCH : scale);
        font.setColor(colour);
        return font;
    }

    /** Sets the drawing scale. 1 means the size the atlas was rendered at. */
    public void setScale(float scale) {
        this.scale = scale;
    }

    public void setColor(float r, float g, float b, float a) {
        colour.set(r, g, b, a);
    }

    public void setColor(Color color) {
        colour.set(color);
    }

    /** Height of a line at the current scale. */
    public float lineHeight() {
        return arabicFont != null
                ? arabicFont.getData().lineHeight : latinFont.getData().lineHeight;
    }

    /** Width of a string as it will actually be drawn, after shaping. */
    public float width(String text) {
        if (text == null || text.isEmpty()) return 0f;
        layout.setText(prepare(text), ArabicShaper.shape(text));
        return layout.width;
    }

    /**
     * Draws at a left edge. {@code y} is the baseline top, as libGDX means it.
     *
     * Note this is a left edge even in Arabic. Callers that want the language's
     * natural side use {@link #drawLeading}.
     */
    public void draw(Batch batch, String text, float x, float y) {
        if (text == null || text.isEmpty()) return;
        prepare(text).draw(batch, ArabicShaper.shape(text), x, y);
    }

    /** Draws with the right edge at {@code x}. */
    public void drawRight(Batch batch, String text, float x, float y) {
        if (text == null || text.isEmpty()) return;
        String shaped = ArabicShaper.shape(text);
        BitmapFont font = prepare(text);
        layout.setText(font, shaped);
        font.draw(batch, shaped, x - layout.width, y);
    }

    /** Draws centred on {@code centreX}. */
    public void drawCentred(Batch batch, String text, float centreX, float y) {
        if (text == null || text.isEmpty()) return;
        String shaped = ArabicShaper.shape(text);
        BitmapFont font = prepare(text);
        layout.setText(font, shaped);
        font.draw(batch, shaped, centreX - layout.width * 0.5f, y);
    }

    /**
     * Draws at the side the current language starts from: the left edge in
     * English, the right edge in Arabic.
     *
     * This is what makes a menu read correctly rather than merely legibly - an
     * Arabic list whose rows all start at the left is the single most obvious
     * sign that a game was translated without being laid out.
     */
    public void drawLeading(Batch batch, String text, float left, float right, float y) {
        if (Strings.rtl()) drawRight(batch, text, right, y);
        else draw(batch, text, left, y);
    }

    /** Draws at the side the current language ends on. The mirror of the above. */
    public void drawTrailing(Batch batch, String text, float left, float right, float y) {
        if (Strings.rtl()) draw(batch, text, left, y);
        else drawRight(batch, text, right, y);
    }

    @Override
    public void dispose() {
        if (arabicFont != null) arabicFont.dispose();
        if (latinFont != null) latinFont.dispose();
        if (generator != null) generator.dispose();
        arabicFont = null;
        latinFont = null;
        generator = null;
    }
}
