package com.muamn.ashen.audio;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.audio.Music;
import com.badlogic.gdx.audio.Sound;
import com.badlogic.gdx.files.FileHandle;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Disposable;
import com.badlogic.gdx.utils.ObjectMap;

/**
 * Playback: renders the bank to WAV files on first run, loads them, and plays
 * them.
 *
 * libGDX will only make a {@link Sound} from a file, and the bank is
 * synthesised at runtime, so the buffers are written into local storage and
 * loaded back. That costs about a second on first launch and nothing after -
 * the files are cached and only re-rendered when {@link #BANK_VERSION} changes.
 *
 * <h3>No device is a normal outcome</h3>
 * A headless CI machine has no ALSA, a phone can have audio taken away by
 * another app, and an emulator often has neither. Every entry point here is
 * safe to call with the whole system switched off, because a game that crashes
 * when the speaker is missing is worse than a silent one.
 */
public class Audio implements Disposable {

    /** Bump when a recipe changes, so cached WAVs are re-rendered. */
    private static final int BANK_VERSION = 1;
    private static final String CACHE_DIR = "audio-cache";
    private static final String STAMP = CACHE_DIR + "/version";

    /** Distance at which a positioned sound is inaudible. */
    private static final float FALLOFF_RANGE = 26f;

    private final ObjectMap<String, Sound> sounds = new ObjectMap<>();
    private Music music;
    private String musicId = "";

    private boolean available;

    public float masterVolume = 1f;
    public float effectVolume = 0.85f;
    public float musicVolume = 0.55f;

    /** Where the listener is, for distance falloff. */
    private final Vector3 listener = new Vector3();

    /**
     * Renders and loads the bank. Never throws: on any failure the whole system
     * turns itself off and every later call is a no-op.
     */
    public void load() {
        if (Gdx.audio == null) {
            Gdx.app.log("Audio", "no audio device - running silent");
            return;
        }
        try {
            FileHandle dir = Gdx.files.local(CACHE_DIR);
            if (!cacheIsCurrent()) {
                long start = System.currentTimeMillis();
                dir.mkdirs();
                for (String id : SoundBank.ALL) {
                    Gdx.files.local(pathOf(id)).writeBytes(
                            Synth.toWav(SoundBank.render(id)), false);
                }
                Gdx.files.local(STAMP).writeString(Integer.toString(BANK_VERSION), false);
                Gdx.app.log("Audio", "synthesised " + SoundBank.ALL.length + " sounds in "
                        + (System.currentTimeMillis() - start) + "ms");
            }

            for (String id : SoundBank.ALL) {
                if (SoundBank.isLoop(id)) continue;   // loops load as Music, on demand
                sounds.put(id, Gdx.audio.newSound(Gdx.files.local(pathOf(id))));
            }
            available = true;
            Gdx.app.log("Audio", "loaded " + sounds.size + " sounds");
        } catch (Throwable t) {
            // Throwable, not Exception: a missing native audio library surfaces as
            // an UnsatisfiedLinkError, and that must not take the game down either.
            Gdx.app.error("Audio", "audio unavailable - running silent", new Exception(t));
            available = false;
            disposeAll();
        }
    }

    private boolean cacheIsCurrent() {
        try {
            FileHandle stamp = Gdx.files.local(STAMP);
            if (!stamp.exists()) return false;
            if (Integer.parseInt(stamp.readString().trim()) != BANK_VERSION) return false;
            for (String id : SoundBank.ALL) {
                if (!Gdx.files.local(pathOf(id)).exists()) return false;
            }
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private static String pathOf(String id) {
        return CACHE_DIR + "/" + id + ".wav";
    }

    public boolean isAvailable() {
        return available;
    }

    /** Where the player is. Positioned sounds fade with distance from here. */
    public void setListener(Vector3 position) {
        listener.set(position);
    }

    // ---- one-shots --------------------------------------------------------

    public void play(String id) {
        play(id, 1f, 1f);
    }

    /**
     * @param volume 0..1, before the master and effect volumes
     * @param pitch  playback rate; 1 is as rendered
     */
    public void play(String id, float volume, float pitch) {
        if (!available) return;
        Sound sound = sounds.get(id);
        if (sound == null) return;
        float gain = volume * effectVolume * masterVolume;
        if (gain <= 0.001f) return;
        try {
            sound.play(MathUtils.clamp(gain, 0f, 1f), MathUtils.clamp(pitch, 0.5f, 2f), 0f);
        } catch (Exception ignored) {
            // A device pulled out mid-play is not worth a crash.
        }
    }

    /**
     * Plays a sound at a world position, quieter the further away it is.
     *
     * Not true 3D panning: libGDX pans on a single -1..1 axis and getting that
     * right needs the camera basis, which this class deliberately does not know
     * about. Distance alone carries most of the information anyway - what the
     * player needs is to tell "something hit something over there" from
     * "something hit me".
     */
    public void playAt(String id, Vector3 position, float volume, float pitch) {
        if (!available) return;
        float distance = position.dst(listener);
        if (distance >= FALLOFF_RANGE) return;
        float falloff = 1f - distance / FALLOFF_RANGE;
        play(id, volume * falloff * falloff, pitch);
    }

    /** A pitch jitter around 1, so a repeated sound does not machine-gun. */
    public static float vary(float amount) {
        return 1f + MathUtils.random(-amount, amount);
    }

    // ---- loops ------------------------------------------------------------

    /**
     * Starts a looping bed, or does nothing if it is already the one playing.
     * Passing null or an empty id stops whatever is playing.
     */
    public void playMusic(String id) {
        if (!available) return;
        if (id == null || id.isEmpty()) {
            stopMusic();
            return;
        }
        if (id.equals(musicId) && music != null && music.isPlaying()) return;
        stopMusic();
        try {
            music = Gdx.audio.newMusic(Gdx.files.local(pathOf(id)));
            music.setLooping(true);
            music.setVolume(MathUtils.clamp(musicVolume * masterVolume, 0f, 1f));
            music.play();
            musicId = id;
        } catch (Exception e) {
            Gdx.app.error("Audio", "could not start " + id, e);
            music = null;
            musicId = "";
        }
    }

    public void stopMusic() {
        if (music == null) return;
        try {
            music.stop();
            music.dispose();
        } catch (Exception ignored) {
            // Already gone.
        }
        music = null;
        musicId = "";
    }

    /** Applies a volume change to whatever is already playing. */
    public void refreshMusicVolume() {
        if (music == null) return;
        try {
            music.setVolume(MathUtils.clamp(musicVolume * masterVolume, 0f, 1f));
        } catch (Exception ignored) {
            // Same.
        }
    }

    public void pause() {
        if (music != null && music.isPlaying()) music.pause();
    }

    public void resume() {
        if (music != null && !music.isPlaying()) music.play();
    }

    @Override
    public void dispose() {
        disposeAll();
    }

    private void disposeAll() {
        stopMusic();
        for (Sound sound : sounds.values()) {
            try {
                sound.dispose();
            } catch (Exception ignored) {
                // Nothing useful to do while shutting down.
            }
        }
        sounds.clear();
    }
}
