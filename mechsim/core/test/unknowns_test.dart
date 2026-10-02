// Loads of unknown size and reactions with a given value: the student
// decides what is known, and the engine solves for the rest.

import 'dart:convert';
import 'dart:math' as math;

import 'package:mechsim_core/mechsim_core.dart';
import 'package:test/test.dart';

import 'helpers.dart';

const _pin = Support(id: 's1', type: SupportType.pin, x: 0);

BeamProblem simplySupported({
  double length = 6,
  Map<String, double> knownB = const {},
  List<Load> loads = const [],
}) =>
    BeamProblem(length: length, supports: [
      _pin,
      Support(id: 's2', type: SupportType.roller, x: length, known: knownB),
    ], loads: loads);

void expectValid(StaticsSolution s) {
  final forces = InternalForceAnalyzer.analyze(s);
  final report = SolutionValidator.validate(s, forces);
  for (final item in report.items) {
    expect(item.passed, isTrue, reason: '${item.kind} ${item.residual}');
  }
}

void main() {
  test('given RB, find the load P that causes it', () {
    final p = simplySupported(
      knownB: {'vertical': 15 * kN},
      loads: [const PointLoad(id: 'p1', x: 3, magnitude: 0, unknown: true)],
    );
    final s = StaticsSolver.solve(p);
    expect(s.isSolved, isTrue);
    expect(s.reactions.map((r) => r.symbol), ['HA', 'RA', 'P1']);
    // ΣM_A: RB × 6 − P1 × 3 = 0 ⇒ P1 = 30 kN, acting down as drawn.
    expect(s.valueOf('p1'), closeToKn(30));
    expect(reaction(s, 'RA'), closeToKn(15));
    expect(s.valueOf('s2.vertical'), closeToKn(15));
    expectValid(s);
    final forces = InternalForceAnalyzer.analyze(s);
    expect(forces.moment.valueAt(3), closeToKnm(45));

    final solution = SolutionBuilder(lang: Lang.en).build(p);
    final text = TextRenderer.render(solution);
    expect(text, contains('P1 = ? ↓'));
    expect(text, contains('RB = 15 kN ↑ (given)'));
    expect(text, contains('P1 = 30.00 kN ↓'));
    final check = solution.steps.where((x) => x.kind == StepKind.check);
    for (final c in check) {
      expect(c.lines.last.plain, endsWith('✓'));
    }
    // The steps solve every unknown, one at a time.
    expect(planEquations(s).map((e) => e.solves.symbol).toSet(),
        {'HA', 'RA', 'P1'});
  });

  test('cantilever: given the fixed-end moment, find the tip load', () {
    final p = BeamProblem(length: 4, supports: [
      const Support(
          id: 's1', type: SupportType.fixed, x: 0, known: {'moment': 30 * kN}),
    ], loads: [
      const PointLoad(id: 'p1', x: 4, magnitude: 0, unknown: true),
    ]);
    final s = StaticsSolver.solve(p);
    expect(s.isSolved, isTrue);
    // ΣM_A: MA − P1 × 4 = 0 ⇒ P1 = 7.5 kN ↓; ΣFy: RA = 7.5 kN ↑.
    expect(s.valueOf('p1'), closeToKn(7.5));
    expect(reaction(s, 'RA'), closeToKn(7.5));
    expectValid(s);
    for (final lang in Lang.values) {
      SolutionBuilder(lang: lang).build(p);
    }
  });

  test('an unknown couple comes out with its true sense', () {
    final p = simplySupported(
      knownB: {'vertical': 10 * kN},
      loads: [
        const PointLoad(id: 'p1', x: 2, magnitude: 20 * kN),
        const PointMoment(id: 'c1', x: 4, magnitude: 0, unknown: true),
      ],
    );
    final s = StaticsSolver.solve(p);
    expect(s.isSolved, isTrue);
    // ΣM_A: 10 × 6 − 20 × 2 + C1 = 0 ⇒ C1 = −20: 20 kN·m clockwise.
    expect(s.valueOf('c1'), closeToKnm(-20));
    expect(reaction(s, 'RA'), closeToKn(10));
    expectValid(s);
    final text =
        TextRenderer.render(SolutionBuilder(lang: Lang.en).build(p));
    expect(text, contains('C1 = −20.00 kN·m ⇒ 20.00 kN·m ↻'));
  });

  test('an unknown horizontal load', () {
    final p = BeamProblem(length: 6, supports: [
      const Support(
          id: 's1',
          type: SupportType.pin,
          x: 0,
          known: {'horizontal': -5 * kN}),
      const Support(id: 's2', type: SupportType.roller, x: 6),
    ], loads: [
      const PointLoad(id: 'p1', x: 2, magnitude: 20 * kN),
      const PointLoad(
          id: 'p2', x: 4, magnitude: 0, angleDeg: 0, unknown: true),
    ]);
    final s = StaticsSolver.solve(p);
    expect(s.isSolved, isTrue);
    expect(s.valueOf('p2'), closeToKn(5)); // → as drawn
    expectValid(s);
  });

  test('a given reaction makes an indeterminate beam solvable', () {
    final p = BeamProblem(length: 6, supports: [
      _pin,
      const Support(
          id: 's2', type: SupportType.pin, x: 6, known: {'horizontal': 0}),
    ], loads: [
      const PointLoad(id: 'p1', x: 3, magnitude: 20 * kN),
    ]);
    final s = StaticsSolver.solve(p);
    expect(s.isSolved, isTrue);
    expect(reaction(s, 'RA'), closeToKn(10));
    expect(reaction(s, 'RB'), closeToKn(10));
    expectValid(s);
    // Without it, the beam is indeterminate to degree 1.
    final free = BeamProblem(length: 6, supports: [
      _pin,
      const Support(id: 's2', type: SupportType.pin, x: 6),
    ]);
    expect(StaticsSolver.solve(free).stability.status,
        Determinacy.indeterminate);
  });

  test('too few unknowns, and unknowns the equations cannot separate', () {
    final over = simplySupported(
      knownB: {'vertical': 10 * kN},
      loads: [const PointLoad(id: 'p1', x: 3, magnitude: 20 * kN)],
    );
    final s1 = StaticsSolver.solve(over);
    expect(s1.isSolved, isFalse);
    expect(s1.stability.reason, StabilityReason.tooFewUnknowns);

    // HA given: no unknown acts along the beam, so ΣFx finds nothing.
    final p2 = BeamProblem(length: 6, supports: [
      const Support(
          id: 's1', type: SupportType.pin, x: 0, known: {'horizontal': 0}),
      const Support(id: 's2', type: SupportType.roller, x: 6),
    ], loads: [
      const PointLoad(id: 'p1', x: 3, magnitude: 0, unknown: true),
    ]);
    final s2 = StaticsSolver.solve(p2);
    expect(s2.isSolved, isFalse);
    expect(s2.stability.reason, StabilityReason.unknownsNotIndependent);
    for (final lang in Lang.values) {
      final text = TextRenderer.render(SolutionBuilder(lang: lang).build(p2));
      expect(text, isNotEmpty);
    }

    // A structure that cannot stand is still reported as such, even with
    // values given.
    final p3 = BeamProblem(length: 6, supports: [
      const Support(
          id: 's1', type: SupportType.roller, x: 0, known: {'vertical': 1}),
      const Support(id: 's2', type: SupportType.roller, x: 6),
    ]);
    expect(StaticsSolver.solve(p3).stability.reason,
        StabilityReason.noHorizontalRestraint);
  });

  test('unknown and given values survive JSON', () {
    final p = simplySupported(
      knownB: {'vertical': 15 * kN},
      loads: [
        const PointLoad(id: 'p1', x: 3, magnitude: 0, unknown: true),
        const PointMoment(id: 'c1', x: 1, magnitude: 0, unknown: true),
      ],
    );
    final back = BeamProblem.fromJson(
        jsonDecode(jsonEncode(p.toJson())) as Map<String, Object?>);
    expect(back, p);
    expect(back.supports.last.known, {'vertical': 15 * kN});
    expect((back.loads.first as PointLoad).unknown, isTrue);
    expect(back.supports.last.withKnown('vertical', null).known, isEmpty);
  });

  test('random beams: give a reaction, find the load back', () {
    final rng = math.Random(20261003);
    var solved = 0;
    for (var i = 0; i < 400; i++) {
      final length = 2 + rng.nextInt(9).toDouble();
      double anywhere() => (rng.nextDouble() * length * 4).round() / 4;
      final cantilever = rng.nextInt(3) == 0;
      final supports = cantilever
          ? [
              Support(
                  id: 's1',
                  type: SupportType.fixed,
                  x: rng.nextBool() ? 0 : length),
            ]
          : [
              Support(id: 's1', type: SupportType.pin, x: anywhere()),
              Support(id: 's2', type: SupportType.roller, x: anywhere()),
            ];
      if (!cantilever && (supports[0].x - supports[1].x).abs() < 0.25) {
        continue;
      }
      final loads = <Load>[
        for (var k = 0; k < 1 + rng.nextInt(3); k++)
          PointLoad(
              id: 'p${k + 1}',
              x: anywhere(),
              magnitude: (1 + rng.nextInt(40)) * 500.0,
              angleDeg: rng.nextBool() ? -90 : 90),
        if (rng.nextBool())
          PointMoment(
              id: 'c1',
              x: anywhere(),
              magnitude: (1 + rng.nextInt(40)) * 500.0,
              counterClockwise: rng.nextBool()),
      ];
      final original = BeamProblem(
          length: length, supports: supports, loads: loads);
      final reference = StaticsSolver.solve(original);
      if (!reference.isSolved) continue;

      // Give one non-horizontal reaction its value and hide one load.
      final candidates = reference.reactions
          .where((r) => r.kind != ReactionKind.horizontal)
          .toList();
      final givenR = candidates[rng.nextInt(candidates.length)];
      final hidden = loads[rng.nextInt(loads.length)];
      final p = original.copyWith(
        supports: [
          for (final sup in supports)
            sup.id == givenR.supportId
                ? sup.withKnown(
                    givenR.kind.name, reference.valueOf(givenR.id))
                : sup,
        ],
        loads: [
          for (final l in loads)
            if (l.id != hidden.id)
              l
            else
              switch (l) {
                PointLoad() => l.copyWith(magnitude: 0, unknown: true),
                PointMoment() => l.copyWith(magnitude: 0, unknown: true),
                DistributedLoad() => l,
              },
        ],
      );
      final s = StaticsSolver.solve(p);
      if (!s.isSolved) {
        // Only when the equations cannot tell the two apart (the hidden
        // load acts where the given reaction does, say).
        expect(s.stability.reason, StabilityReason.unknownsNotIndependent,
            reason: '#$i ${p.toJson()}');
        continue;
      }
      final scale = loads.fold(
          0.0,
          (a, l) =>
              a +
              switch (l) {
                PointLoad() => l.magnitude,
                PointMoment() => l.magnitude,
                DistributedLoad() => 0,
              });
      final expected = switch (hidden) {
        PointLoad() => hidden.magnitude,
        PointMoment() => hidden.magnitude,
        DistributedLoad() => 0.0,
      };
      expect(s.valueOf(hidden.id), closeTo(expected, 1e-9 * scale * length),
          reason: '#$i ${p.toJson()}');
      for (final r in reference.reactions) {
        expect(s.valueOf(r.id),
            closeTo(reference.valueOf(r.id), 1e-9 * scale * length),
            reason: '#$i ${r.symbol}');
      }
      expectValid(s);
      for (final lang in Lang.values) {
        final solution = SolutionBuilder(lang: lang).build(p);
        for (final c in solution.steps.where((x) => x.kind == StepKind.check)) {
          expect(c.lines.last.plain, endsWith('✓'), reason: '#$i');
        }
        expect(planEquations(s).length, s.reactions.length, reason: '#$i');
      }
      solved++;
    }
    expect(solved, greaterThan(150));
  });
}
