import 'dart:math' as math;

import 'package:mechsim_core/mechsim_core.dart';
import 'package:test/test.dart';

import 'helpers.dart';

void main() {
  group('known beams', () {
    test('the example from the brief: 6 m, 20 kN at mid-span', () {
      final s = StaticsSolver.solve(beam(6,
          supports: [(SupportType.pin, 0), (SupportType.roller, 6)],
          loads: [down(20, 3)]));
      expect(s.isSolved, isTrue);
      expect(reaction(s, 'RA'), closeToKn(10));
      expect(reaction(s, 'RB'), closeToKn(10));
      expect(reaction(s, 'HA'), 0);
    });

    test('off-centre load: RA = Pb/L, RB = Pa/L', () {
      for (final a in [0.5, 1.0, 2.0, 2.5, 7.25]) {
        const p = 30.0, l = 8.0;
        final s = StaticsSolver.solve(beam(l,
            supports: [(SupportType.pin, 0), (SupportType.roller, l)],
            loads: [down(p, a)]));
        expect(reaction(s, 'RA'), closeToKn(p * (l - a) / l), reason: 'a = $a');
        expect(reaction(s, 'RB'), closeToKn(p * a / l), reason: 'a = $a');
      }
    });

    test('roller on the left, pin on the right', () {
      final s = StaticsSolver.solve(beam(6,
          supports: [(SupportType.roller, 0), (SupportType.pin, 6)],
          loads: [down(12, 2)]));
      expect(reaction(s, 'RA'), closeToKn(8));
      expect(reaction(s, 'RB'), closeToKn(4));
      expect(reaction(s, 'HB'), 0);
    });

    test('overhang: a negative reaction', () {
      final s = StaticsSolver.solve(beam(6,
          supports: [(SupportType.pin, 0), (SupportType.roller, 4)],
          loads: [down(12, 6)]));
      expect(reaction(s, 'RB'), closeToKn(18));
      expect(reaction(s, 'RA'), closeToKn(-6));
    });

    test('cantilever fixed on the left', () {
      final s = StaticsSolver.solve(beam(4,
          supports: [(SupportType.fixed, 0)], loads: [down(10, 4)]));
      expect(reaction(s, 'RA'), closeToKn(10));
      expect(reaction(s, 'MA'), closeToKnm(40)); // counter-clockwise
      expect(reaction(s, 'HA'), 0);
    });

    test('cantilever fixed on the right', () {
      final s = StaticsSolver.solve(beam(5,
          supports: [(SupportType.fixed, 5)], loads: [down(8, 0), down(12, 2)]));
      expect(reaction(s, 'RA'), closeToKn(20));
      // Loads to the left of the support turn it counter-clockwise, so the
      // wall answers clockwise: 8·5 + 12·3 = 76.
      expect(reaction(s, 'MA'), closeToKnm(-76));
    });

    test('inclined load: the pin takes the horizontal component', () {
      final s = StaticsSolver.solve(beam(5,
          supports: [(SupportType.pin, 0), (SupportType.roller, 5)],
          loads: [(20, 2, -60)]));
      final fy = 20 * math.sin(60 * math.pi / 180);
      expect(reaction(s, 'HA'), closeToKn(-10));
      expect(reaction(s, 'RB'), closeTo(fy * 2 / 5 * kN, 1e-6));
      expect(reaction(s, 'RA'), closeTo(fy * 3 / 5 * kN, 1e-6));
    });

    test('upward load', () {
      final s = StaticsSolver.solve(beam(8,
          supports: [(SupportType.pin, 0), (SupportType.roller, 6)],
          loads: [down(30, 3), (10, 8, 90)]));
      // ΣM_A: 6 RB − 30·3 + 10·8 = 0
      expect(reaction(s, 'RB'), closeToKn(10 / 6));
      expect(reaction(s, 'RA'), closeToKn(30 - 10 - 10 / 6));
    });

    test('load directly over a support goes straight into it', () {
      final s = StaticsSolver.solve(beam(6,
          supports: [(SupportType.pin, 0), (SupportType.roller, 6)],
          loads: [down(20, 0)]));
      expect(reaction(s, 'RA'), closeToKn(20));
      expect(reaction(s, 'RB'), 0);
    });

    test('no loads: all reactions are exactly zero', () {
      final s = StaticsSolver.solve(beam(6,
          supports: [(SupportType.pin, 0), (SupportType.roller, 6)]));
      expect(s.values.values, everyElement(0.0));
    });
  });

  group('stability', () {
    StabilityReport report(BeamProblem p) => StaticsSolver.solve(p).stability;

    test('no beam', () {
      expect(report(const BeamProblem()).reason, StabilityReason.noBeam);
    });

    test('no supports', () {
      final r = report(beam(6, loads: [down(10, 3)]));
      expect(r.status, Determinacy.unstable);
      expect(r.reason, StabilityReason.noSupports);
    });

    test('two rollers cannot resist sliding', () {
      final r = report(beam(6,
          supports: [(SupportType.roller, 0), (SupportType.roller, 6)]));
      expect(r.status, Determinacy.unstable);
      expect(r.reason, StabilityReason.noHorizontalRestraint);
    });

    test('a single pin lets the beam rotate', () {
      final r = report(beam(6, supports: [(SupportType.pin, 0)]));
      expect(r.status, Determinacy.unstable);
      expect(r.reason, StabilityReason.concurrentReactions);
    });

    test('pin and roller at the same point', () {
      final r = report(beam(6,
          supports: [(SupportType.pin, 2), (SupportType.roller, 2)]));
      expect(r.status, Determinacy.unstable);
      expect(r.reason, StabilityReason.concurrentReactions);
    });

    test('two pins are indeterminate to degree 1', () {
      final r = report(beam(6, supports: [(SupportType.pin, 0), (SupportType.pin, 6)]));
      expect(r.status, Determinacy.indeterminate);
      expect(r.degree, 1);
    });

    test('propped cantilever is indeterminate to degree 1', () {
      final r = report(beam(6,
          supports: [(SupportType.fixed, 0), (SupportType.roller, 6)]));
      expect(r.status, Determinacy.indeterminate);
      expect(r.degree, 1);
    });

    test('a support off the beam', () {
      final r = report(beam(6,
          supports: [(SupportType.pin, 0), (SupportType.roller, 7)]));
      expect(r.status, Determinacy.invalid);
      expect(r.reason, StabilityReason.elementOffBeam);
    });
  });

  group('labels', () {
    test('supports first, then load points, left to right', () {
      final p = beam(6,
          supports: [(SupportType.roller, 6), (SupportType.pin, 0)],
          loads: [down(5, 4), down(5, 2), down(5, 6)]);
      final labels = ProblemLabels.of(p);
      expect(labels.pointAt(0), 'A');
      expect(labels.pointAt(6), 'B');
      expect(labels.pointAt(2), 'C');
      expect(labels.pointAt(4), 'D');
      // The load at x = 6 shares the support's letter.
      expect(labels.pointOf('p3'), 'B');
      expect(labels.loadName('p2'), 'P1');
      expect(labels.loadName('p1'), 'P2');
    });
  });

  group('model edits', () {
    test('changing the length keeps an end support on the end', () {
      final p = beam(6, supports: [(SupportType.pin, 0), (SupportType.roller, 6)],
          loads: [down(10, 5)]);
      final longer = p.withLength(8);
      expect(longer.supports[1].x, 8);
      expect(longer.loads.single.x, 5);
      final shorter = p.withLength(4);
      expect(shorter.loads.single.x, 4);
    });

    test('moves are clamped onto the beam', () {
      final p = beam(6, supports: [(SupportType.pin, 0)]);
      expect(p.move('s1', -3).supports.single.x, 0);
      expect(p.move('s1', 9).supports.single.x, 6);
    });

    test('vertical loads have an exactly zero horizontal component', () {
      const load = PointLoad(id: 'p', x: 0, magnitude: 1000);
      expect(load.fx, 0);
      expect(load.fy, -1000);
      expect(const PointLoad(id: 'p', x: 0, magnitude: 1000, angleDeg: 90).fx, 0);
    });
  });
}
