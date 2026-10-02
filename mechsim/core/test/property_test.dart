// Hundreds of random beams, each checked three independent ways: the
// engine's own validator, the step-by-step equations replayed one at a time,
// and the shear/moment recomputed from the right-hand part of the beam.

import 'dart:math' as math;

import 'package:mechsim_core/mechsim_core.dart';
import 'package:test/test.dart';

import 'helpers.dart';

BeamProblem randomBeam(math.Random rng) {
  final length = 1 + rng.nextInt(20) * 0.5;
  double anywhere() => (rng.nextDouble() * length * 4).round() / 4;
  var p = BeamProblem(length: length);
  if (rng.nextInt(4) == 0) {
    p = p.withSupport(Support(
        id: 's1', type: SupportType.fixed, x: rng.nextBool() ? 0 : length));
  } else {
    var a = anywhere(), b = anywhere();
    while ((a - b).abs() < 0.25) {
      a = anywhere();
      b = anywhere();
    }
    final pinFirst = rng.nextBool();
    p = p
        .withSupport(Support(id: 's1', type: pinFirst ? SupportType.pin : SupportType.roller, x: a))
        .withSupport(Support(id: 's2', type: pinFirst ? SupportType.roller : SupportType.pin, x: b));
  }
  if (rng.nextInt(3) == 0) {
    var a = anywhere(), b = anywhere();
    if (a > b) (a, b) = (b, a);
    if (b - a >= 0.25) {
      p = p.withLoad(DistributedLoad(
        id: p.nextId('w'),
        x: a,
        x2: b,
        w1: rng.nextInt(20) * 500.0,
        w2: rng.nextInt(20) * 500.0,
        upward: rng.nextInt(5) == 0,
      ));
    }
  }
  if (rng.nextInt(4) == 0) {
    p = p.withLoad(PointMoment(
      id: p.nextId('c'),
      x: anywhere(),
      magnitude: (1 + rng.nextInt(40)) * 500.0,
      counterClockwise: rng.nextBool(),
    ));
  }
  final loads = rng.nextInt(5);
  for (var i = 0; i < loads; i++) {
    p = p.withLoad(PointLoad(
      id: p.nextId('p'),
      x: anywhere(),
      magnitude: (1 + rng.nextInt(100)) * 500.0,
      angleDeg: rng.nextInt(3) == 0 ? rng.nextInt(360) - 180.0 : -90,
    ));
  }
  return p;
}

void checkThoroughly(BeamProblem p, {String reason = ''}) {
  final s = StaticsSolver.solve(p);
  expect(s.isSolved, isTrue, reason: reason);
  final forces = InternalForceAnalyzer.analyze(s);

  // 1. The validator: equilibrium about both ends, closure, jumps, slopes.
  final report = SolutionValidator.validate(s, forces);
  for (final item in report.items) {
    expect(item.passed, isTrue,
        reason: '$reason ${item.kind} residual ${item.residual}');
  }

  // 2. Replaying the planned equations one unknown at a time gives the same
  //    reactions as the matrix solve.
  final plan = planEquations(s);
  expect(plan.length, s.reactions.length, reason: reason);
  final known = <String, double>{};
  for (final step in plan) {
    known[step.solves.id] = step.equation.solveSingle(known);
  }
  final scale = math.max(
      1.0,
      p.loads.fold(
          0.0,
          (a, l) => a + switch (l) {
                PointLoad() => l.magnitude,
                DistributedLoad() => l.resultant.abs(),
                PointMoment() => l.magnitude / math.max(1.0, p.length),
              }));
  for (final r in s.reactions) {
    final tol = 1e-9 * scale * (r.kind == ReactionKind.moment ? math.max(1.0, p.length) : 1);
    expect(known[r.id], closeTo(s.valueOf(r.id), tol), reason: '$reason ${r.symbol}');
  }

  // 3. Internal forces from the right-hand part agree with the left-hand
  //    method of sections everywhere along the beam.
  final mTol = 1e-9 * scale * math.max(1.0, p.length);
  for (var i = 1; i < 40; i++) {
    final x = p.length * i / 40 + 1e-7;
    expect(forces.shear.valueAt(x), closeTo(shearFromRight(s, x), 1e-9 * scale),
        reason: '$reason V($x)');
    expect(forces.moment.valueAt(x), closeTo(momentFromRight(s, x), mTol),
        reason: '$reason M($x)');
  }

  // 4. The explanation builds in both languages without throwing, and every
  //    check line it prints comes out zero.
  for (final lang in Lang.values) {
    final solution = SolutionBuilder(lang: lang).build(p);
    final check = solution.steps.where((x) => x.kind == StepKind.check);
    for (final c in check) {
      expect(c.lines.last.plain, endsWith('✓'), reason: '$reason ${c.title}');
    }
  }
}

void main() {
  test('600 random determinate beams', () {
    final rng = math.Random(20261002);
    var solved = 0;
    for (var i = 0; i < 2000 && solved < 600; i++) {
      final p = randomBeam(rng);
      if (!StaticsSolver.solve(p).isSolved) continue;
      checkThoroughly(p, reason: 'beam #$i ${p.toJson()}');
      solved++;
    }
    expect(solved, 600);
  });

  test('every generated practice problem is determinate and checks out', () {
    for (final level in PracticeLevel.values) {
      final gen = ProblemGenerator(level.index * 97 + 5);
      for (var i = 0; i < 150; i++) {
        final p = gen.generate(level);
        checkThoroughly(p, reason: '$level #$i');
        // A UDL over the whole span starts on a support, as it should; a
        // point load there would only teach that it goes into the support.
        for (final load in p.pointLoads) {
          for (final sup in p.supports) {
            expect((load.x - sup.x).abs(), greaterThan(1e-9),
                reason: 'a practice load should not sit on a support');
          }
        }
      }
    }
  });

  test('every example in the library solves and validates', () {
    for (final e in ExampleLibrary.all) {
      checkThoroughly(e.problem, reason: e.id);
    }
  });
}
