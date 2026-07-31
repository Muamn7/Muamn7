package com.muamn.ashen.audio;

import java.util.Random;

/**
 * A small mono synthesiser: oscillators, noise, envelopes, filters and a WAV
 * encoder, all operating on plain {@code float[]} buffers.
 *
 * The game ships no audio files. That is the same decision as the textures and
 * for the same reasons - nothing to download, nothing to license, nothing to go
 * missing - but it lands better here than it does in graphics, because the
 * sounds a Souls game needs are the ones synthesis is good at: a blade through
 * air is filtered noise, a parry is a struck metal bar, a footstep is a click
 * and a scrape. None of that wants a microphone.
 *
 * Everything is pure and deterministic given its seed, so the whole bank can be
 * unit tested without an audio device - which matters, because CI has none.
 */
public final class Synth {

    /**
     * 22050 Hz mono. High enough that a sword whoosh keeps its edge, low enough
     * that the whole bank fits in a couple of megabytes on a phone. It is also
     * squarely in the era the rest of the game is imitating.
     */
    public static final int SAMPLE_RATE = 22050;

    private Synth() {}

    public static int samples(float seconds) {
        return Math.max(1, Math.round(seconds * SAMPLE_RATE));
    }

    public static float[] buffer(float seconds) {
        return new float[samples(seconds)];
    }

    // ---- sources ----------------------------------------------------------

    /** White noise, added into the buffer. */
    public static float[] noise(float[] out, float gain, Random random) {
        for (int i = 0; i < out.length; i++) {
            out[i] += (random.nextFloat() * 2f - 1f) * gain;
        }
        return out;
    }

    /**
     * A sine sweeping from one frequency to another over the buffer.
     *
     * Phase is integrated rather than computed from {@code i * f}, or a swept
     * tone tears at every sample where the frequency changes.
     */
    public static float[] sine(float[] out, float fromHz, float toHz, float gain, float curve) {
        double phase = 0.0;
        for (int i = 0; i < out.length; i++) {
            float t = out.length == 1 ? 0f : i / (float) (out.length - 1);
            float f = lerp(fromHz, toHz, (float) Math.pow(t, curve));
            phase += 2.0 * Math.PI * f / SAMPLE_RATE;
            out[i] += (float) Math.sin(phase) * gain;
        }
        return out;
    }

    /** A sawtooth sweep. Brighter than a sine; used for anything metallic. */
    public static float[] saw(float[] out, float fromHz, float toHz, float gain, float curve) {
        double phase = 0.0;
        for (int i = 0; i < out.length; i++) {
            float t = out.length == 1 ? 0f : i / (float) (out.length - 1);
            float f = lerp(fromHz, toHz, (float) Math.pow(t, curve));
            phase += f / SAMPLE_RATE;
            phase -= Math.floor(phase);
            out[i] += (float) (phase * 2.0 - 1.0) * gain;
        }
        return out;
    }

    /** A steady sine at one pitch, for drones and pads. */
    public static float[] tone(float[] out, float hz, float gain) {
        return sine(out, hz, hz, gain, 1f);
    }

    // ---- shaping ----------------------------------------------------------

    /**
     * Multiplies in an attack/decay envelope.
     *
     * @param attack  seconds to reach full
     * @param decay   seconds of fall after the hold
     * @param curve   >1 makes the decay snap early, <1 makes it linger
     */
    public static float[] envelope(float[] out, float attack, float decay, float curve) {
        int attackSamples = Math.max(1, Math.round(attack * SAMPLE_RATE));
        int decaySamples = Math.max(1, Math.round(decay * SAMPLE_RATE));
        for (int i = 0; i < out.length; i++) {
            float gain;
            if (i < attackSamples) {
                gain = i / (float) attackSamples;
            } else {
                float t = (i - attackSamples) / (float) decaySamples;
                gain = t >= 1f ? 0f : (float) Math.pow(1f - t, curve);
            }
            out[i] *= gain;
        }
        return out;
    }

    /** One-pole low pass. {@code cutoff} in Hz. */
    public static float[] lowpass(float[] out, float cutoff) {
        float alpha = alphaFor(cutoff);
        float previous = 0f;
        for (int i = 0; i < out.length; i++) {
            previous += alpha * (out[i] - previous);
            out[i] = previous;
        }
        return out;
    }

    /**
     * Low pass whose cutoff sweeps across the buffer. This is what turns plain
     * noise into a swing: the sound opens up as the blade accelerates.
     */
    public static float[] sweepLowpass(float[] out, float fromHz, float toHz) {
        float previous = 0f;
        for (int i = 0; i < out.length; i++) {
            float t = out.length == 1 ? 0f : i / (float) (out.length - 1);
            float alpha = alphaFor(lerp(fromHz, toHz, t));
            previous += alpha * (out[i] - previous);
            out[i] = previous;
        }
        return out;
    }

    /** One-pole high pass, as the complement of the low pass. */
    public static float[] highpass(float[] out, float cutoff) {
        float alpha = alphaFor(cutoff);
        float previous = 0f;
        for (int i = 0; i < out.length; i++) {
            float input = out[i];
            previous += alpha * (input - previous);
            out[i] = input - previous;
        }
        return out;
    }

    /**
     * A rough band pass: low pass then high pass. Two one-poles are a gentle
     * slope rather than a surgical band, which is what percussive noise wants.
     */
    public static float[] bandish(float[] out, float lowHz, float highHz) {
        lowpass(out, highHz);
        return highpass(out, lowHz);
    }

    /**
     * Soft clipping. Adds harmonics without the buzz of a hard clip.
     *
     * The curve is scaled so an input of 1 comes out at exactly 1, which means an
     * input already past full scale would come out past it - so the result is
     * clamped. A saturator that can overshoot is not a saturator.
     */
    public static float[] saturate(float[] out, float drive) {
        float scale = 1f / (float) Math.tanh(drive);
        for (int i = 0; i < out.length; i++) {
            float shaped = (float) Math.tanh(out[i] * drive) * scale;
            out[i] = Math.max(-1f, Math.min(1f, shaped));
        }
        return out;
    }

    /**
     * A cheap stone-room reverb: a few delayed, quieter copies.
     *
     * Not a real reverb, but the whole game is fog and stone corridors, and four
     * taps is the difference between a sound happening in a room and a sound
     * happening in a vacuum.
     */
    public static float[] room(float[] out, float amount, float sizeSeconds) {
        int[] taps = {
                Math.round(sizeSeconds * SAMPLE_RATE * 0.37f),
                Math.round(sizeSeconds * SAMPLE_RATE * 0.61f),
                Math.round(sizeSeconds * SAMPLE_RATE * 0.83f),
                Math.round(sizeSeconds * SAMPLE_RATE),
        };
        float[] wet = out.clone();
        for (int t = 0; t < taps.length; t++) {
            int delay = Math.max(1, taps[t]);
            float gain = amount * (float) Math.pow(0.62, t + 1);
            for (int i = delay; i < out.length; i++) {
                wet[i] += out[i - delay] * gain;
            }
        }
        System.arraycopy(wet, 0, out, 0, out.length);
        return out;
    }

    /** Mixes {@code source} into {@code out} starting at a sample offset. */
    public static float[] mix(float[] out, float[] source, int offset, float gain) {
        for (int i = 0; i < source.length; i++) {
            int index = offset + i;
            if (index < 0 || index >= out.length) continue;
            out[index] += source[i] * gain;
        }
        return out;
    }

    /**
     * Scales the buffer so its loudest sample sits at {@code peak}.
     *
     * Every sound in the bank goes through this, so nothing needs its gains
     * hand-balanced against the others and nothing can clip on the way out.
     */
    public static float[] normalise(float[] out, float peak) {
        float loudest = 0f;
        for (float sample : out) loudest = Math.max(loudest, Math.abs(sample));
        if (loudest < 1e-6f) return out;
        float scale = peak / loudest;
        for (int i = 0; i < out.length; i++) out[i] *= scale;
        return out;
    }

    /**
     * Fades the ends to zero.
     *
     * A buffer that starts or stops mid-wave clicks, and a looping buffer whose
     * ends do not meet clicks once per loop, which is far worse.
     */
    public static float[] deClick(float[] out, float seconds) {
        int n = Math.min(out.length / 2, Math.max(1, Math.round(seconds * SAMPLE_RATE)));
        for (int i = 0; i < n; i++) {
            float gain = i / (float) n;
            out[i] *= gain;
            out[out.length - 1 - i] *= gain;
        }
        return out;
    }

    /**
     * Crossfades the tail over the head so the buffer loops without a seam.
     *
     * @param seconds length of the overlap; the buffer shortens by this much
     */
    public static float[] seamlessLoop(float[] out, float seconds) {
        int n = Math.min(out.length / 3, Math.max(1, Math.round(seconds * SAMPLE_RATE)));
        int kept = out.length - n;
        float[] looped = new float[kept];
        System.arraycopy(out, 0, looped, 0, kept);
        for (int i = 0; i < n; i++) {
            float t = i / (float) n;
            looped[i] = looped[i] * t + out[kept + i] * (1f - t);
        }
        return looped;
    }

    // ---- output -----------------------------------------------------------

    /** 16-bit mono PCM in a RIFF/WAVE container. */
    public static byte[] toWav(float[] samples) {
        int dataBytes = samples.length * 2;
        byte[] wav = new byte[44 + dataBytes];

        writeAscii(wav, 0, "RIFF");
        writeIntLE(wav, 4, 36 + dataBytes);
        writeAscii(wav, 8, "WAVE");
        writeAscii(wav, 12, "fmt ");
        writeIntLE(wav, 16, 16);              // PCM header size
        writeShortLE(wav, 20, 1);             // format: PCM
        writeShortLE(wav, 22, 1);             // channels: mono
        writeIntLE(wav, 24, SAMPLE_RATE);
        writeIntLE(wav, 28, SAMPLE_RATE * 2); // byte rate
        writeShortLE(wav, 32, 2);             // block align
        writeShortLE(wav, 34, 16);            // bits per sample
        writeAscii(wav, 36, "data");
        writeIntLE(wav, 40, dataBytes);

        for (int i = 0; i < samples.length; i++) {
            float clamped = Math.max(-1f, Math.min(1f, samples[i]));
            writeShortLE(wav, 44 + i * 2, Math.round(clamped * 32767f));
        }
        return wav;
    }

    private static void writeAscii(byte[] out, int at, String text) {
        for (int i = 0; i < text.length(); i++) out[at + i] = (byte) text.charAt(i);
    }

    private static void writeIntLE(byte[] out, int at, int value) {
        out[at] = (byte) value;
        out[at + 1] = (byte) (value >> 8);
        out[at + 2] = (byte) (value >> 16);
        out[at + 3] = (byte) (value >> 24);
    }

    private static void writeShortLE(byte[] out, int at, int value) {
        out[at] = (byte) value;
        out[at + 1] = (byte) (value >> 8);
    }

    // ---- helpers ----------------------------------------------------------

    private static float alphaFor(float cutoffHz) {
        float clamped = Math.max(1f, Math.min(SAMPLE_RATE * 0.45f, cutoffHz));
        float rc = 1f / (2f * (float) Math.PI * clamped);
        float dt = 1f / SAMPLE_RATE;
        return dt / (rc + dt);
    }

    private static float lerp(float a, float b, float t) {
        return a + (b - a) * t;
    }
}
