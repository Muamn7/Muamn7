import 'dart:convert';
import 'dart:math' as math;

import 'package:mechsim_core/mechsim_core.dart';
import 'package:test/test.dart';

const kN = 1000.0;

/// A(0,0) pinned, B(4,3) loaded with 10 kN down, C(8,0) on a roller.
TrussProblem triangle() => const TrussProblem(nodes: [
      TrussNode(id: 'n1', x: 0, y: 0),
      TrussNode(id: 'n2', x: 4, y: 3),
      TrussNode(id: 'n3', x: 8, y: 0),
    ], members: [
      TrussMember(id: 'm1', a: 'n1', b: 'n2'),
      TrussMember(id: 'm2', a: 'n2', b: 'n3'),
      TrussMember(id: 'm3', a: 'n1', b: 'n3'),
    ], supports: [
      TrussSupport(id: 's1', node: 'n1', type: TrussSupportType.pin),
      TrussSupport(id: 's2', node: 'n3', type: TrussSupportType.roller),
    ], loads: [
      TrussLoad(id: 'f1', node: 'n2', magnitude: 10 * kN),
    ]);

void expectBalanced(TrussSolution s) {
  for (final n in s.problem.nodes) {
    expect(s.residualAt(n.id), closeTo(0, 1e-6), reason: 'joint ${n.id}');
  }
}

/// The members a vertical line at x crosses.
List<String> cutAt(TrussProblem p, double x) => [
      for (final m in p.members)
        if ((p.node(m.a)!.x - x) * (p.node(m.b)!.x - x) < 0) m.id,
    ];

void main() {
  test('triangle: the hand solution', () {
    final s = TrussSolver.solve(triangle());
    expect(s.isSolved, isTrue);
    expect(s.reaction('s1.x'), closeTo(0, 1e-9));
    expect(s.reaction('s1.y'), closeTo(5 * kN, 1e-6));
    expect(s.reaction('s2.y'), closeTo(5 * kN, 1e-6));
    // Joint A: Ay + F_AB·(3/5) = 0 ⇒ F_AB = −8.333 (C); F_AC = 6.667 (T).
    expect(s.force('m1'), closeTo(-25 / 3 * kN, 1e-6));
    expect(s.force('m2'), closeTo(-25 / 3 * kN, 1e-6));
    expect(s.force('m3'), closeTo(20 / 3 * kN, 1e-6));
    expectBalanced(s);

    final e = const TrussExplainer(lang: Lang.en).explain(triangle());
    final text = [
      for (final step in e.steps)
        for (final l in step.lines) l.plain,
    ].join('\n');
    expect(text, contains('m + r = 6 = 2j = 6 ✓'));
    expect(text, contains('ΣM_A = 0'));
    expect(text, contains('F_AB·(3/5)'));
    expect(text, contains('F_AB = −5 ÷ (3/5) = −8.333 kN (C)'));
    expect(text, contains('F_AC = 6.667 kN (T)'));
    expect(e.steps.last.kind, StepKind.trussMembers);
    final check = e.steps.where((x) => x.kind == StepKind.trussCheck);
    expect(check, isNotEmpty);
    for (final l in check.single.lines.where((l) => l.plain.contains('='))) {
      if (l.plain.endsWith('✓') || l.plain.endsWith('✗')) {
        expect(l.plain, endsWith('✓'));
      }
    }
  });

  test('Pratt truss: end diagonal and bottom chord, and a section', () {
    final p = TrussTemplates.build('pratt'); // 12 m, 4 panels, 3 m high
    final s = TrussSolver.solve(p);
    expect(s.isSolved, isTrue);
    expectBalanced(s);
    expect(s.reaction(s.reactions.last.id), closeTo(15 * kN, 1e-6));
    // The end diagonal at 45° carries Ay / sin 45° in compression.
    final a = p.nodes.first.id;
    final diagonal = p.membersAt(a).firstWhere((m) =>
        p.node(m.other(a))!.y > 0);
    expect(s.force(diagonal.id), closeTo(-15 * math.sqrt2 * kN, 1e-6));
    final chord = p.membersAt(a).firstWhere((m) =>
        p.node(m.other(a))!.y == 0);
    expect(s.force(chord.id), closeTo(15 * kN, 1e-6));

    // A vertical cut in the second panel: three members.
    final cut = cutAt(p, 4.5);
    expect(cut.length, 3);
    final section = const TrussExplainer(lang: Lang.en).section(p, cut);
    expect(section.isValid, isTrue);
    expect(section.steps.length, 1 + 3 + 1);
    final other = const TrussExplainer().section(p, cut, otherSide: true);
    expect(other.isValid, isTrue);
    expect(other.side.intersection(section.side), isEmpty);
  });

  test('every template, every vertical cut, both languages', () {
    for (final kind in TrussTemplates.kinds) {
      for (final panels in [2, 4, 6]) {
        if (kind == 'triangle' && panels != 2) continue;
        final p = TrussTemplates.build(kind, span: 3.0 * panels, panels: panels);
        final s = TrussSolver.solve(p);
        expect(s.isSolved, isTrue, reason: '$kind $panels');
        expectBalanced(s);
        for (final lang in Lang.values) {
          final e = TrussExplainer(lang: lang).explain(p);
          // Every member is found joint by joint, none left over.
          expect(e.steps.where((x) => x.title.contains(
                  lang == Lang.ar ? 'الأعضاء الباقية' : 'remaining')),
              isEmpty, reason: '$kind $panels');
          expect(e.members.length, p.members.length);
          for (var x = 0.25; x < p.nodes.map((n) => n.x).reduce(math.max); x += 0.5) {
            final cut = cutAt(p, x);
            if (cut.isEmpty || cut.length > 3) continue;
            final section = TrussExplainer(lang: lang).section(p, cut);
            expect(section.isValid, isTrue, reason: '$kind $panels at $x');
          }
        }
      }
    }
  });

  test('random loads on random templates match the matrix solve', () {
    final rng = math.Random(20261013);
    for (var i = 0; i < 120; i++) {
      final kind = TrussTemplates.kinds[rng.nextInt(TrussTemplates.kinds.length)];
      final panels = 2 + 2 * rng.nextInt(3);
      var p = TrussTemplates.build(kind,
          span: (1 + rng.nextInt(4)) * panels.toDouble(),
          panels: panels,
          height: 1.0 + rng.nextInt(5));
      // Loads anywhere, any direction.
      p = p.copyWith(loads: [
        for (final n in p.nodes)
          if (rng.nextInt(3) == 0)
            TrussLoad(
                id: 'L${n.id}',
                node: n.id,
                magnitude: (1 + rng.nextInt(40)) * 500.0,
                angleDeg: rng.nextBool() ? -90 : rng.nextInt(360) - 180.0),
      ]);
      final s = TrussSolver.solve(p);
      expect(s.isSolved, isTrue);
      expectBalanced(s);
      // The explanation reaches the solver's numbers (checked by asserts
      // inside each step) and its check joint balances.
      final e = TrussExplainer(lang: i.isEven ? Lang.ar : Lang.en).explain(p);
      final check = e.steps.where((x) => x.kind == StepKind.trussCheck);
      for (final c in check) {
        for (final l in c.lines) {
          if (l.plain.endsWith('✗')) fail('#$i check failed: ${l.plain}');
        }
      }
      // Off the joints: a line through a joint would not cut cleanly.
      final x = (0.3 + rng.nextInt(panels)) *
          (p.nodes.map((n) => n.x).reduce(math.max) / panels);
      final cut = cutAt(p, x);
      if (cut.isNotEmpty && cut.length <= 3) {
        expect(const TrussExplainer().section(p, cut).isValid, isTrue);
      }
    }
  });

  test('unstable, indeterminate, empty', () {
    // A square with no diagonal folds.
    var square = const TrussProblem(nodes: [
      TrussNode(id: 'a', x: 0, y: 0),
      TrussNode(id: 'b', x: 3, y: 0),
      TrussNode(id: 'c', x: 3, y: 3),
      TrussNode(id: 'd', x: 0, y: 3),
    ], members: [
      TrussMember(id: 'ab', a: 'a', b: 'b'),
      TrussMember(id: 'bc', a: 'b', b: 'c'),
      TrussMember(id: 'cd', a: 'c', b: 'd'),
      TrussMember(id: 'da', a: 'd', b: 'a'),
    ], supports: [
      TrussSupport(id: 's1', node: 'a', type: TrussSupportType.pin),
      TrussSupport(id: 's2', node: 'b', type: TrussSupportType.roller),
    ]);
    expect(TrussSolver.solve(square).stability.reason, TrussReason.mechanism);
    square = square.withMember(const TrussMember(id: 'ac', a: 'a', b: 'c'));
    expect(TrussSolver.solve(square).isSolved, isTrue);
    square = square.withMember(const TrussMember(id: 'bd', a: 'b', b: 'd'));
    final s = TrussSolver.solve(square);
    expect(s.stability.reason, TrussReason.indeterminate);
    expect(s.stability.degree, 1);
    expect(TrussSolver.solve(const TrussProblem()).stability.reason,
        TrussReason.empty);
    final e = const TrussExplainer().explain(square);
    expect(e.steps.last.kind, StepKind.unsolvable);
  });

  test('a cut that does not split the truss is refused', () {
    final p = TrussTemplates.build('pratt');
    final s = const TrussExplainer(lang: Lang.en)
        .section(p, [p.members.first.id]);
    expect(s.isValid, isFalse);
    expect(s.error, contains('do not split'));
    expect(const TrussExplainer().section(p, []).isValid, isFalse);
  });

  test('JSON and editing', () {
    final p = TrussTemplates.build('warren');
    final back = TrussProblem.fromJson(
        jsonDecode(jsonEncode(p.toJson())) as Map<String, Object?>);
    expect(back, p);
    final n = p.nodes[1].id;
    final removed = p.remove(n);
    expect(removed.nodes.length, p.nodes.length - 1);
    expect(removed.members.any((m) => m.joins(n)), isFalse);
    expect(p.withMember(TrussMember(id: 'x', a: n, b: n)), same(p));
    final a = p.members.first;
    expect(p.withMember(TrussMember(id: 'x', a: a.b, b: a.a)), same(p));
    expect(TrussLabels.of(p).member(a), 'AB');
  });
}
