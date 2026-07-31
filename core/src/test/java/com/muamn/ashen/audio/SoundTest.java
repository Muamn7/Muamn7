package com.muamn.ashen.audio;

import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.Random;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Guards the synthesiser and the bank it feeds.
 *
 * There is no way to unit test whether a sound is good. There is a very
 * effective way to test whether it is broken, and these are the ways it can be:
 * silence, clipping, a click at the ends, a loop with a seam, a header the
 * decoder will not read, or a recipe that changes between launches.
 */
class SoundTest {

    // ---- the WAV container ------------------------------------------------

    @Test
    void theWavHeaderIsWhatADecoderExpects() {
        byte[] wav = Synth.toWav(new float[100]);
        assertEquals(44 + 200, wav.length);
        assertEquals("RIFF", ascii(wav, 0, 4));
        assertEquals("WAVE", ascii(wav, 8, 4));
        assertEquals("fmt ", ascii(wav, 12, 4));
        assertEquals("data", ascii(wav, 36, 4));

        assertEquals(36 + 200, intAt(wav, 4), "RIFF size counts everything after itself");
        assertEquals(16, intAt(wav, 16), "PCM fmt chunk is 16 bytes");
        assertEquals(1, shortAt(wav, 20), "format must be uncompressed PCM");
        assertEquals(1, shortAt(wav, 22), "mono");
        assertEquals(Synth.SAMPLE_RATE, intAt(wav, 24));
        assertEquals(Synth.SAMPLE_RATE * 2, intAt(wav, 28), "byte rate is rate * blockAlign");
        assertEquals(2, shortAt(wav, 32), "block align is 2 for 16-bit mono");
        assertEquals(16, shortAt(wav, 34));
        assertEquals(200, intAt(wav, 40), "data size must match the sample count");
    }

    @Test
    void samplesSurviveTheRoundTripToPcm() {
        float[] samples = {0f, 1f, -1f, 0.5f, -0.5f};
        byte[] wav = Synth.toWav(samples);
        assertEquals(0, shortAt(wav, 44));
        assertEquals(32767, shortAt(wav, 46));
        assertEquals(-32767, shortAt(wav, 48));
        assertEquals(16384, shortAt(wav, 50), 1);
        assertEquals(-16384, shortAt(wav, 52), 1);
    }

    @Test
    void samplesBeyondFullScaleAreClampedNotWrapped() {
        // Wrapping is the difference between a loud sound and a burst of noise.
        byte[] wav = Synth.toWav(new float[]{4f, -4f});
        assertEquals(32767, shortAt(wav, 44));
        assertEquals(-32767, shortAt(wav, 46));
    }

    // ---- the primitives ---------------------------------------------------

    @Test
    void normaliseHitsTheRequestedPeakWithoutChangingShape() {
        float[] samples = {0.1f, -0.2f, 0.05f};
        Synth.normalise(samples, 0.8f);
        assertEquals(0.8f, Math.abs(samples[1]), 1e-5f);
        assertEquals(-0.5f, samples[0] / samples[1], 1e-5f, "the ratios must be untouched");
    }

    @Test
    void normalisingSilenceDoesNotDivideByZero() {
        float[] silence = new float[16];
        Synth.normalise(silence, 0.9f);
        for (float sample : silence) assertEquals(0f, sample);
    }

    @Test
    void theEnvelopeStartsAndEndsAtZero() {
        float[] samples = new float[Synth.samples(0.2f)];
        java.util.Arrays.fill(samples, 1f);
        Synth.envelope(samples, 0.01f, 0.19f, 2f);
        assertEquals(0f, samples[0], 1e-6f);
        assertEquals(0f, samples[samples.length - 1], 0.02f);
        assertTrue(samples[Synth.samples(0.01f)] > 0.9f, "the peak should follow the attack");
    }

    @Test
    void deClickSilencesBothEnds() {
        float[] samples = new float[Synth.samples(0.1f)];
        java.util.Arrays.fill(samples, 1f);
        Synth.deClick(samples, 0.005f);
        assertEquals(0f, samples[0], 1e-6f);
        assertEquals(0f, samples[samples.length - 1], 1e-6f);
        assertEquals(1f, samples[samples.length / 2], 1e-6f, "the middle is untouched");
    }

    @Test
    void theLowPassActuallyRemovesHighFrequencies() {
        float[] high = Synth.buffer(0.2f);
        Synth.tone(high, 8000f, 1f);
        float before = rms(high);
        Synth.lowpass(high, 300f);
        assertTrue(rms(high) < before * 0.2f,
                "an 8kHz tone through a 300Hz low pass should nearly vanish");

        float[] low = Synth.buffer(0.2f);
        Synth.tone(low, 120f, 1f);
        float lowBefore = rms(low);
        Synth.lowpass(low, 3000f);
        assertTrue(rms(low) > lowBefore * 0.8f, "a 120Hz tone should pass a 3kHz filter");
    }

    @Test
    void theHighPassIsTheComplement() {
        float[] samples = Synth.buffer(0.2f);
        Synth.tone(samples, 80f, 1f);
        float before = rms(samples);
        Synth.highpass(samples, 3000f);
        assertTrue(rms(samples) < before * 0.2f);
    }

    @Test
    void saturationAddsGainWithoutEverExceedingOne() {
        float[] samples = {0.1f, 0.5f, 1f, -1f, 3f};
        Synth.saturate(samples, 3f);
        for (float sample : samples) {
            assertTrue(Math.abs(sample) <= 1.001f, "saturate produced " + sample);
        }
        assertTrue(samples[0] > 0.1f, "quiet samples should come up");
    }

    @Test
    void aSweptSineDoesNotTearWhereTheFrequencyChanges() {
        // Integrating phase rather than recomputing it is the whole point; a torn
        // sweep shows up as a sample-to-sample jump far larger than the rest.
        float[] samples = Synth.buffer(0.3f);
        Synth.sine(samples, 100f, 4000f, 1f, 1f);
        float largest = 0f;
        for (int i = 1; i < samples.length; i++) {
            largest = Math.max(largest, Math.abs(samples[i] - samples[i - 1]));
        }
        // At 4kHz on a 22.05kHz rate one step is at most about 1.1 of full scale.
        assertTrue(largest < 1.3f, "largest step was " + largest);
    }

    @Test
    void mixIgnoresWhateverFallsOffTheEnds() {
        float[] out = new float[4];
        Synth.mix(out, new float[]{1f, 1f, 1f}, -2, 1f);
        assertArrayEquals(new float[]{1f, 0f, 0f, 0f}, out, 1e-6f);
        Synth.mix(out, new float[]{1f, 1f, 1f}, 3, 1f);
        assertArrayEquals(new float[]{1f, 0f, 0f, 1f}, out, 1e-6f);
    }

    @Test
    void seamlessLoopShortensTheBufferAndJoinsTheEnds() {
        float[] samples = Synth.buffer(1f);
        Synth.noise(samples, 1f, new Random(1));
        int before = samples.length;
        float[] looped = Synth.seamlessLoop(samples, 0.1f);
        assertEquals(before - Synth.samples(0.1f), looped.length);
        // The join is what matters: the step from the last sample back to the
        // first must be no worse than a step anywhere else in the buffer.
        float seam = Math.abs(looped[0] - looped[looped.length - 1]);
        float largestInside = 0f;
        for (int i = 1; i < looped.length; i++) {
            largestInside = Math.max(largestInside, Math.abs(looped[i] - looped[i - 1]));
        }
        assertTrue(seam <= largestInside * 1.5f,
                "seam " + seam + " against a largest internal step of " + largestInside);
    }

    // ---- the bank ---------------------------------------------------------

    @Test
    void everySoundIsAudibleAndNoneClips() {
        for (String id : SoundBank.ALL) {
            float[] samples = SoundBank.render(id);
            assertTrue(samples.length > 0, id + " rendered nothing");

            float peak = 0f;
            for (float sample : samples) peak = Math.max(peak, Math.abs(sample));
            assertTrue(peak > 0.2f, id + " is effectively silent (peak " + peak + ")");
            assertTrue(peak <= 1f, id + " clips (peak " + peak + ")");
            assertTrue(rms(samples) > 0.008f, id + " has almost no energy in it");
        }
    }

    @Test
    void noSoundContainsNaNOrInfinity() {
        for (String id : SoundBank.ALL) {
            for (float sample : SoundBank.render(id)) {
                assertFalse(Float.isNaN(sample), id + " produced NaN");
                assertFalse(Float.isInfinite(sample), id + " produced infinity");
            }
        }
    }

    @Test
    void oneShotsStartAndEndSilent() {
        for (String id : SoundBank.ALL) {
            if (SoundBank.isLoop(id)) continue;
            float[] samples = SoundBank.render(id);
            assertEquals(0f, samples[0], 1e-4f, id + " starts mid-wave and will click");
            assertEquals(0f, samples[samples.length - 1], 1e-4f, id + " ends mid-wave");
        }
    }

    @Test
    void renderingIsDeterministic() {
        // A sound that comes out different every launch is not a sound.
        for (String id : SoundBank.ALL) {
            assertArrayEquals(SoundBank.render(id), SoundBank.render(id), 0f,
                    id + " is not reproducible");
        }
    }

    @Test
    void idsAreUniqueAndAllRenderable() {
        Set<String> seen = new HashSet<>();
        for (String id : SoundBank.ALL) {
            assertTrue(seen.add(id), "duplicate sound id: " + id);
            SoundBank.render(id);
        }
    }

    @Test
    void loopsAreLongEnoughToNotBeObvious() {
        for (String id : SoundBank.ALL) {
            if (!SoundBank.isLoop(id)) continue;
            float seconds = SoundBank.render(id).length / (float) Synth.SAMPLE_RATE;
            assertTrue(seconds >= 8f, id + " loops every " + seconds + "s, which will grate");
        }
    }

    @Test
    void oneShotsAreShortEnoughToNotOverlapThemselves() {
        // Anything that can fire twice in quick succession has to be over before
        // it fires again, or a flurry of hits turns into mud.
        String[] rapid = {SoundBank.FOOTSTEP, SoundBank.SWING_LIGHT,
                SoundBank.HIT_FLESH, SoundBank.HIT_BONE, SoundBank.MENU_MOVE};
        for (String id : rapid) {
            float seconds = SoundBank.render(id).length / (float) Synth.SAMPLE_RATE;
            assertTrue(seconds <= 0.6f, id + " runs for " + seconds + "s");
        }
    }

    @Test
    void theWholeBankFitsInAReasonableCache() {
        // It is written to the device on first launch, so it has to stay small.
        long bytes = 0;
        for (String id : SoundBank.ALL) bytes += 44L + SoundBank.render(id).length * 2L;
        assertTrue(bytes < 3_000_000L, "the bank came to " + bytes / 1024 + "KB");
    }

    // ---- helpers ----------------------------------------------------------

    private static float rms(float[] samples) {
        double sum = 0;
        for (float sample : samples) sum += sample * sample;
        return (float) Math.sqrt(sum / samples.length);
    }

    private static String ascii(byte[] data, int at, int length) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < length; i++) sb.append((char) (data[at + i] & 0xFF));
        return sb.toString();
    }

    private static int intAt(byte[] data, int at) {
        return (data[at] & 0xFF) | (data[at + 1] & 0xFF) << 8
                | (data[at + 2] & 0xFF) << 16 | (data[at + 3] & 0xFF) << 24;
    }

    private static int shortAt(byte[] data, int at) {
        return (short) ((data[at] & 0xFF) | (data[at + 1] & 0xFF) << 8);
    }
}
