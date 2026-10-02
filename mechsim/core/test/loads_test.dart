import 'dart:math' as math;

import 'package:mechsim_core/mechsim_core.dart';
import 'package:test/test.dart';

import 'helpers.dart';

/// A beam with a distributed load in kN/m from [a] to [b].
BeamProblem withUdl(BeamProblem p, double w1, double a, double b,
        {double? w2, bool up = false}) =>
    p.withLoad(DistributedLoad(
        id: p.nextId('w'), x: a, x2: b, w1: w1 * kN, w2: (w2 ?? w1) * kN, upward: up));

BeamProblem withCouple(BeamProblem p, double kNm, double x) => p.withLoad(PointMoment(
    id: p.nextId('c'), x: x, magnitude: kNm.abs() * kN, counterClockwise: kNm >= 0));

void main() {
  final simple = beam(6, supports: [(SupportType.pin, 0), (SupportType.roller, 6)]);

  group('uniformly distributed load', () {
    test('full span: R = wL/2, Mmax = wL²/8 at mid-span', () {
      final p = withUdl(simple, 5, 0, 6);
      final s = StaticsSolver.solve(p);
      expect(reaction(s, 'RA'), closeToKn(15));
      expect(reaction(s, 'RB'), closeToKn(15));
      final f = InternalForceAnalyzer.analyze(s);
      expect(f.shear.valueAt(1), closeToKn(10));
      expect(f.shear.valueAt(3), closeTo(0, 1e-6));
      final peak = f.moment.absMaximum!;
      expect(peak.value, closeToKnm(22.5));
      expect(peak.x, closeTo(3, 1e-9));
      expect(f.moment.valueAt(2), closeToKnm(15 * 2 - 5 * 4 / 2));
    });

    test('partial and symmetric', () {
      final p = withUdl(beam(8, supports: [(SupportType.pin, 0), (SupportType.roller, 8)]),
          10, 2, 6);
      final s = StaticsSolver.solve(p);
      expect(reaction(s, 'RA'), closeToKn(20));
      final f = InternalForceAnalyzer.analyze(s);
      expect(f.moment.valueAt(4), closeToKnm(20 * 4 - 10 * 2 * 1));
      expect(f.shear.valueAt(1), closeToKn(20)); // before the load: constant
      expect(f.moment.valueAt(1), closeToKnm(20));
    });

    test('cantilever: MA = wL²/2', () {
      final p = withUdl(beam(4, supports: [(SupportType.fixed, 0)]), 3, 0, 4);
      final s = StaticsSolver.solve(p);
      expect(reaction(s, 'RA'), closeToKn(12));
      expect(reaction(s, 'MA'), closeToKnm(24));
      final f = InternalForceAnalyzer.analyze(s);
      expect(f.moment.rightLimit(0), closeToKnm(-24));
      expect(f.moment.valueAt(2), closeToKnm(-6));
    });

    test('an upward distributed load pushes the reactions down', () {
      final p = withUdl(simple, 4, 0, 6, up: true);
      final s = StaticsSolver.solve(p);
      expect(reaction(s, 'RA'), closeToKn(-12));
    });
  });

  group('uniformly varying load', () {
    test('triangle 0 → w over the span: RA = wL/6, RB = wL/3, '
        'Mmax = wL²/(9√3) at L/√3', () {
      const w = 6.0, l = 6.0;
      final p = withUdl(simple, 0, 0, l, w2: w);
      final s = StaticsSolver.solve(p);
      expect(reaction(s, 'RA'), closeToKn(w * l / 6));
      expect(reaction(s, 'RB'), closeToKn(w * l / 3));
      final peak = InternalForceAnalyzer.analyze(s).moment.absMaximum!;
      expect(peak.value, closeTo(w * l * l / (9 * math.sqrt(3)) * kN, 1e-6));
      expect(peak.x, closeTo(l / math.sqrt(3), 1e-9));
    });

    test('resultant and centroid of a trapezoid', () {
      const d = DistributedLoad(id: 'w', x: 1, x2: 4, w1: 2000, w2: 8000);
      expect(d.resultant, 15000);
      expect(d.centroid, closeTo(1 + 3 * (2 + 16) / (3 * 10), 1e-12));
    });
  });

  group('applied couple', () {
    test('a couple alone: equal and opposite reactions, BMD jumps', () {
      final p = withCouple(simple, 12, 3);
      final s = StaticsSolver.solve(p);
      expect(reaction(s, 'RB'), closeToKn(-2));
      expect(reaction(s, 'RA'), closeToKn(2));
      final f = InternalForceAnalyzer.analyze(s);
      expect(f.shear.valueAt(1), closeToKn(2));
      expect(f.shear.valueAt(5), closeToKn(2));
      expect(f.moment.leftLimit(3), closeToKnm(6));
      expect(f.moment.rightLimit(3), closeToKnm(-6));
    });

    test('a clockwise couple on a cantilever', () {
      final p = withCouple(beam(3, supports: [(SupportType.fixed, 0)]), -9, 3);
      final s = StaticsSolver.solve(p);
      expect(reaction(s, 'RA'), 0);
      expect(reaction(s, 'MA'), closeToKnm(9));
      expect(InternalForceAnalyzer.analyze(s).moment.valueAt(1), closeToKnm(-9));
    });
  });

  group('explanation', () {
    final p = withUdl(simple, 5, 0, 6);
    final solution = const SolutionBuilder(lang: Lang.en).build(p);

    test('replaces the load by its resultant before the equations', () {
      final r = solution.steps.firstWhere((x) => x.kind == StepKind.resultants);
      expect(r.lines.map((l) => l.plain), ['W1 = 5 × 6 = 30 kN ↓', 'x̄(W1) = 3 m']);
      final eq = solution.steps.firstWhere((x) => x.title == 'ΣM_A = 0');
      expect(eq.lines[1].plain, 'RB × 6 − 30 × 3 = 0');
      final term = eq.lines[1].tokens.firstWhere((t) => t.text == '30 × 3');
      expect(term.explanation, contains('resultant of distributed load W1'));
      expect(term.highlights, contains(const ResultantHighlight('w1')));
    });

    test('shear and moment by sections inside the load', () {
      final v = solution.steps.firstWhere((x) => x.kind == StepKind.shear);
      expect(v.lines.single.plain, '0 < x < 6 m: V = RA − w1·x = 15 − 5x = −5x + 15');
      final m = solution.steps.firstWhere((x) => x.kind == StepKind.moment);
      expect(m.lines.first.plain,
          '0 ≤ x ≤ 6 m: M = RA·x − w1·x²/2 = 15x − 2.5x² = −2.5x² + 15x');
      expect(m.lines.last.plain, 'M(0) = 0, M(3) = 22.5, M(6) = 0 (kN·m)');
    });

    test('the BMD by areas stops where V = 0', () {
      final b = solution.steps.firstWhere((x) => x.kind == StepKind.momentDiagram);
      expect(b.lines.map((l) => l.plain), [
        'M(0) = 0',
        'M(3) = M(0) + ((15 + 0)/2 × 3) = 0 + 22.5 = 22.5',
        'M(6) = M(3) + ((0 − 15)/2 × 3) = 22.5 − 22.5 = 0 ✓',
      ]);
      final max = solution.steps.firstWhere((x) => x.kind == StepKind.maxMoment);
      expect(max.lines.first.plain, 'V changes sign at x = 3 m');
    });

    test('a couple appears in ΣM but not in ΣFy, and makes the BMD jump', () {
      final s = const SolutionBuilder(lang: Lang.en).build(withCouple(simple, 12, 3));
      final m = s.steps.firstWhere((x) => x.title == 'ΣM_A = 0');
      expect(m.lines[1].plain, 'RB × 6 + 12 = 0');
      final fy = s.steps.firstWhere((x) => x.title == 'ΣFy = 0');
      expect(fy.lines[1].plain, 'RA + RB = 0');
      final b = s.steps.firstWhere((x) => x.kind == StepKind.momentDiagram);
      expect(b.lines.map((l) => l.plain), contains('x = 3 m C1 ↺ ⇒ ΔM = −12 ⇒ M = −6'));
    });

    test('the Arabic text names the load and its resultant', () {
      final ar = const SolutionBuilder(lang: Lang.ar).build(p);
      final r = ar.steps.firstWhere((x) => x.kind == StepKind.resultants);
      expect(r.explanation, contains('مساحة مخطط الحمل'));
    });
  });

  group('model', () {
    test('new loads survive JSON', () {
      final p = withCouple(withUdl(simple, 2, 1, 4, w2: 5), -7, 2);
      expect(BeamProblem.fromJson(p.toJson()), p);
    });

    test('a distributed load slides as a whole and stays on the beam', () {
      final p = withUdl(simple, 5, 1, 3);
      final moved = p.move('w1', 5.5).loads.single as DistributedLoad;
      expect((moved.x, moved.x2), (4.0, 6.0));
    });

    test('labels: W for distributed loads, C for couples, both ends lettered', () {
      final p = withCouple(withUdl(simple, 5, 1, 3), 4, 4);
      final labels = ProblemLabels.of(p);
      expect(labels.loadName('w1'), 'W1');
      expect(labels.loadName('c1'), 'C1');
      expect(labels.pointAt(1), isNotNull);
      expect(labels.pointAt(3), isNotNull);
    });
  });
}
