import 'package:mechsim_core/mechsim_core.dart';
import 'package:test/test.dart';

import 'helpers.dart';

InternalForces forcesOf(BeamProblem p) =>
    InternalForceAnalyzer.analyze(StaticsSolver.solve(p));

void main() {
  group('the example from the brief', () {
    final f = forcesOf(beam(6,
        supports: [(SupportType.pin, 0), (SupportType.roller, 6)],
        loads: [down(20, 3)]));

    test('shear: +10 then −10, with a jump of 20 under the load', () {
      expect(f.shear.valueAt(1.5), closeToKn(10));
      expect(f.shear.valueAt(4.5), closeToKn(-10));
      expect(f.shear.leftLimit(3), closeToKn(10));
      expect(f.shear.rightLimit(3), closeToKn(-10));
      expect(f.shear.rightLimit(0), closeToKn(10));
      expect(f.shear.leftLimit(6), closeToKn(-10));
    });

    test('moment: 0 → 30 kN·m at x = 3 → 0', () {
      expect(f.moment.valueAt(0), closeTo(0, 1e-9));
      expect(f.moment.valueAt(3), closeToKnm(30));
      expect(f.moment.valueAt(1.5), closeToKnm(15));
      expect(f.moment.leftLimit(6), closeTo(0, 1e-6));
    });

    test('Mmax = 30 kN·m at x = 3 m, where V changes sign', () {
      final peak = f.moment.absMaximum!;
      expect(peak.value, closeToKnm(30));
      expect(peak.x, closeTo(3, 1e-12));
      expect(f.shear.signChanges(), [closeTo(3, 1e-12)]);
    });

    test('no axial force', () {
      expect(f.hasAxial, isFalse);
    });

    test('graph outline starts and ends on the axis and jumps at the load', () {
      final g = GraphEngine.build(f.shear, DiagramKind.shear);
      expect(g.outline.first.value, 0);
      expect(g.outline.last.value, 0);
      final at3 = g.outline.where((p) => p.x == 3).map((p) => p.value / kN).toList();
      expect(at3, [closeTo(10, 1e-9), closeTo(-10, 1e-9)]);
      expect(g.maxValue, closeToKn(10));
      expect(g.minValue, closeToKn(-10));
      // One label per flat segment.
      expect(g.keyValues.map((k) => k.role), everyElement(KeyRole.plateau));
      expect(g.keyValues, hasLength(2));
    });

    test('BMD labels the peak once', () {
      final g = GraphEngine.build(f.moment, DiagramKind.moment);
      expect(g.keyValues, hasLength(1));
      expect(g.keyValues.single.value, closeToKnm(30));
      expect(g.keyValues.single.x, 3);
    });
  });

  test('off-centre load: Mmax = Pab/L under the load', () {
    const p = 30.0, l = 8.0, a = 2.0;
    final f = forcesOf(beam(l,
        supports: [(SupportType.pin, 0), (SupportType.roller, l)],
        loads: [down(p, a)]));
    final peak = f.moment.absMaximum!;
    expect(peak.value, closeToKnm(p * a * (l - a) / l));
    expect(peak.x, a);
  });

  test('two symmetric loads: constant moment between them', () {
    final f = forcesOf(beam(9,
        supports: [(SupportType.pin, 0), (SupportType.roller, 9)],
        loads: [down(10, 3), down(10, 6)]));
    expect(f.shear.valueAt(4.5), closeTo(0, 1e-9));
    expect(f.moment.valueAt(3), closeToKnm(30));
    expect(f.moment.valueAt(4.5), closeToKnm(30));
    expect(f.moment.valueAt(6), closeToKnm(30));
  });

  test('cantilever fixed on the left: M(0) = −PL, hogging all along', () {
    final f = forcesOf(beam(4, supports: [(SupportType.fixed, 0)], loads: [down(10, 4)]));
    expect(f.moment.rightLimit(0), closeToKnm(-40));
    expect(f.moment.valueAt(2), closeToKnm(-20));
    expect(f.moment.leftLimit(4), closeTo(0, 1e-6));
    expect(f.shear.valueAt(2), closeToKn(10));
    final peak = f.moment.absMaximum!;
    expect(peak.value, closeToKnm(-40));
    expect(peak.x, 0);
    expect(f.moment.maximum!.value, closeTo(0, 1e-6));
  });

  test('cantilever fixed on the right: M = −P·x', () {
    final f = forcesOf(beam(4, supports: [(SupportType.fixed, 4)], loads: [down(10, 0)]));
    expect(f.shear.valueAt(2), closeToKn(-10));
    expect(f.moment.valueAt(1), closeToKnm(-10));
    expect(f.moment.leftLimit(4), closeToKnm(-40));
  });

  test('overhang: hogging moment over the roller', () {
    final f = forcesOf(beam(6,
        supports: [(SupportType.pin, 0), (SupportType.roller, 4)],
        loads: [down(12, 6)]));
    expect(f.moment.valueAt(4), closeToKnm(-24));
    expect(f.shear.valueAt(2), closeToKn(-6));
    expect(f.shear.valueAt(5), closeToKn(12));
  });

  test('inclined load: tension between the pin and the load', () {
    final f = forcesOf(beam(5,
        supports: [(SupportType.pin, 0), (SupportType.roller, 5)],
        loads: [(20, 2, -60)]));
    expect(f.hasAxial, isTrue);
    expect(f.axial.valueAt(1), closeToKn(10)); // tension
    expect(f.axial.valueAt(3), closeTo(0, 1e-6));
  });

  test('a load pulling left puts the span in compression', () {
    final f = forcesOf(beam(5,
        supports: [(SupportType.pin, 0), (SupportType.roller, 5)],
        loads: [(10, 5, 180)]));
    expect(f.axial.valueAt(2), closeToKn(-10));
  });

  group('Polynomial', () {
    test('roots of a cubic inside an interval', () {
      // (x − 1)(x − 2)(x − 4) = x³ − 7x² + 14x − 8
      final p = Polynomial([-8, 14, -7, 1]);
      expect(p.rootsIn(0, 5), [closeTo(1, 1e-9), closeTo(2, 1e-9), closeTo(4, 1e-9)]);
      expect(p.rootsIn(1.5, 3), [closeTo(2, 1e-9)]);
    });

    test('derivative and integral', () {
      final p = Polynomial([1, 2, 3]); // 1 + 2x + 3x²
      expect(p.derivative().c, [2, 6]);
      expect(p.integrate(0, 1), closeTo(1 + 1 + 1, 1e-12));
    });
  });
}
