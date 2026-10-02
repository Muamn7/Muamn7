import 'package:mechsim_core/mechsim_core.dart';
import 'package:test/test.dart';

import 'helpers.dart';

String strip(String s) => s.replaceAll(RegExp('[\u2066-\u2069]'), '');

void main() {
  final example = beam(6,
      supports: [(SupportType.pin, 0), (SupportType.roller, 6)],
      loads: [down(20, 3)]);

  group('the example from the brief, in English', () {
    final solution = const SolutionBuilder(lang: Lang.en).build(example);
    SolutionStep step(String title) =>
        solution.steps.firstWhere((s) => s.title == title);

    test('steps follow the textbook order', () {
      expect(solution.steps.map((s) => s.kind).toList(), [
        StepKind.given,
        StepKind.freeBody,
        StepKind.equilibrium,
        StepKind.equilibrium,
        StepKind.equilibrium,
        StepKind.check,
        StepKind.reactions,
        StepKind.shear,
        StepKind.shearDiagram,
        StepKind.moment,
        StepKind.momentDiagram,
        StepKind.maxMoment,
      ]);
      expect(solution.steps.where((s) => s.kind == StepKind.equilibrium).map((s) => s.title),
          ['ΣFx = 0', 'ΣM_A = 0', 'ΣFy = 0']);
      expect(solution.steps[5].title, 'Check: ΣM_B = 0');
    });

    test('ΣM_A = 0 is written exactly as a student would', () {
      final lines = step('ΣM_A = 0').lines.map((l) => l.plain).toList();
      expect(lines, [
        'ΣM_A = 0 (↺ +)',
        'RB × 6 − 20 × 3 = 0',
        'RB × 6 = 20 × 3',
        'RB = 60 ÷ 6 = 10 kN ↑',
      ]);
    });

    test('ΣFy = 0 substitutes RB and gives RA', () {
      final lines = step('ΣFy = 0').lines.map((l) => l.plain).toList();
      expect(lines, [
        'ΣFy = 0 (↑ +)',
        'RA + RB − 20 = 0',
        'RA + 10 − 20 = 0',
        'RA = 20 − 10 = 10 kN ↑',
      ]);
    });

    test('every term explains itself', () {
      final eq = step('ΣM_A = 0').lines[1];
      final rb = eq.tokens.firstWhere((t) => t.text == 'RB × 6');
      expect(rb.explanation, contains('reaction force at support B'));
      expect(rb.explanation, contains('6 m'));
      expect(rb.explanation, contains('positive'));
      expect(rb.highlights, contains(const ReactionHighlight('s2.vertical')));
      expect(rb.highlights, contains(const ArmHighlight(0, 6)));
      final load = eq.tokens.firstWhere((t) => t.text == '20 × 3');
      expect(load.explanation, contains('20 kN'));
      expect(load.explanation, contains('3 m'));
      expect(load.explanation, contains('negative'));
      expect(load.highlights, contains(const LoadHighlight('p1')));
    });

    test('why moments about A', () {
      final why = step('ΣM_A = 0').explanation;
      expect(why, contains('because we want RB'));
      expect(why, contains('HA and RA'));
    });

    test('the check comes out zero', () {
      expect(solution.steps[5].lines.last.plain, '−60 + 60 = 0 ✓');
    });

    test('shear by sections explains the negative segment', () {
      final s = solution.steps.firstWhere((s) => s.kind == StepKind.shear);
      expect(s.lines[0].plain, '0 < x < 3 m: V = RA = 10 kN');
      expect(s.lines[1].plain, '3 < x < 6 m: V = RA − P1 = 10 − 20 = −10 kN');
      expect(s.lines[1].note, contains('negative'));
      expect(s.results[1].highlights,
          [const DiagramRangeHighlight(DiagramKind.shear, 3, 6)]);
    });

    test('moment by sections and by areas', () {
      final m = solution.steps.firstWhere((s) => s.kind == StepKind.moment);
      expect(m.lines[0].plain, '0 ≤ x ≤ 3 m: M = RA·x = 10x');
      expect(m.lines[1].plain,
          '3 ≤ x ≤ 6 m: M = RA·x − P1·(x − 3) = 10x − 20(x − 3) = −10x + 60');
      final bmd = solution.steps.firstWhere((s) => s.kind == StepKind.momentDiagram);
      expect(bmd.lines.map((l) => l.plain), [
        'M(0) = 0',
        'M(3) = M(0) + (10 × 3) = 0 + 30 = 30',
        'M(6) = M(3) + (−10 × 3) = 30 − 30 = 0 ✓',
      ]);
    });

    test('Mmax is linked to its place on the BMD', () {
      final max = solution.results!.maxMoment!;
      expect(max.text, 'Mmax = 30.00 kN·m  @ x = 3.00 m');
      expect(max.highlights.single, isA<DiagramPointHighlight>());
      final h = max.highlights.single as DiagramPointHighlight;
      expect(h.kind, DiagramKind.moment);
      expect(h.x, 3);
    });

    test('reaction results are linked to their arrows', () {
      final rb = solution.results!.reactions.firstWhere((r) => r.symbol == 'RB');
      expect(rb.text, 'RB = 10.00 kN ↑');
      expect(rb.highlights, [const ReactionHighlight('s2.vertical')]);
      expect(solution.stepSolving('s2.vertical'), 3);
    });

    test('the player reveals reactions one by one, then the diagrams', () {
      final reveals = solution.steps.map((s) => s.reveal).toList();
      expect(reveals[0].reactions, isFalse);
      expect(reveals[1].reactions, isTrue);
      expect(reveals[1].solved, isEmpty);
      expect(reveals[3].solved, {'s1.horizontal', 's2.vertical'});
      expect(reveals[8].shear, isTrue);
      expect(reveals[8].moment, isFalse);
      expect(reveals[10].moment, isTrue);
    });
  });

  group('in Arabic', () {
    final solution = const SolutionBuilder(lang: Lang.ar).build(example);

    test('the explanation of ΣM_A reads like the brief', () {
      final s = solution.steps.firstWhere((s) => s.title == 'ΣM_A = 0');
      final why = strip(s.explanation);
      expect(why, startsWith('استخدمنا العزوم حول A لأننا نريد إيجاد RB'));
      expect(strip(s.detail!), startsWith('الجسم في حالة اتزان، لذلك مجموع العزوم حول أي نقطة يساوي صفر'));
      final rb = s.lines[1].tokens.firstWhere((t) => t.text == 'RB × 6');
      expect(strip(rb.explanation!), startsWith('RB هي قوة رد الفعل عند المسند B، و6 m هي المسافة بين A وB'));
      final load = s.lines[1].tokens.firstWhere((t) => t.text == '20 × 3');
      expect(strip(load.explanation!), startsWith('20 kN هي قيمة الحمل P1 و3 m هي المسافة من A إلى الحمل'));
    });

    test('ΣFy says why it comes after ΣM_A', () {
      final s = solution.steps.firstWhere((s) => s.title == 'ΣFy = 0');
      expect(strip(s.explanation),
          'بعد معرفة RB نستطيع إيجاد RA باستخدام اتزان القوى الرأسية.');
    });

    test('math in Arabic prose is isolated left-to-right', () {
      final s = solution.steps.firstWhere((s) => s.title == 'ΣM_A = 0');
      expect(s.explanation, contains('\u2066RB\u2069'));
    });
  });

  group('sign convention', () {
    test('changing it changes the written signs, never the answers', () {
      const flipped = SignConvention(
          upPositive: false, rightPositive: false, counterClockwisePositive: false);
      final a = const SolutionBuilder(lang: Lang.en).build(example);
      final b = const SolutionBuilder(lang: Lang.en, convention: flipped).build(example);
      expect(b.statics.values, a.statics.values);
      final eq = b.steps.firstWhere((s) => s.title == 'ΣM_A = 0');
      expect(eq.lines[0].plain, 'ΣM_A = 0 (↻ +)');
      expect(eq.lines[1].plain, '−RB × 6 + 20 × 3 = 0');
      expect(eq.lines.last.plain, 'RB = 60 ÷ 6 = 10 kN ↑');
      final fy = b.steps.firstWhere((s) => s.title == 'ΣFy = 0');
      expect(fy.lines[1].plain, '−RA − RB + 20 = 0');
      expect(fy.lines.last.plain, 'RA = 20 − 10 = 10 kN ↑');
    });
  });

  group('other beams', () {
    test('cantilever: ΣFx, ΣFy, then ΣM about the wall', () {
      final s = const SolutionBuilder(lang: Lang.en)
          .build(beam(4, supports: [(SupportType.fixed, 0)], loads: [down(10, 4)]));
      expect(s.steps.where((x) => x.kind == StepKind.equilibrium).map((x) => x.title),
          ['ΣFx = 0', 'ΣFy = 0', 'ΣM_A = 0']);
      final m = s.steps.firstWhere((x) => x.title == 'ΣM_A = 0');
      expect(m.lines[1].plain, 'MA − 10 × 4 = 0');
      expect(m.lines.last.plain, 'MA = 10 × 4 = 40 kN·m ↺');
      final max = s.steps.firstWhere((x) => x.kind == StepKind.maxMoment);
      expect(max.lines.single.plain, 'M−max = −40 kN·m @ x = 0 m');
    });

    test('overhang: a negative reaction is explained', () {
      final s = const SolutionBuilder(lang: Lang.en).build(beam(6,
          supports: [(SupportType.pin, 0), (SupportType.roller, 4)],
          loads: [down(12, 6)]));
      final fy = s.steps.firstWhere((x) => x.title == 'ΣFy = 0');
      expect(fy.lines.last.plain, 'RA = 12 − 18 = −6 kN');
      expect(fy.lines.last.note, contains('actually acts ↓'));
      final ra = s.results!.reactions.firstWhere((r) => r.symbol == 'RA');
      expect(ra.text, 'RA = −6.00 kN ⇒ 6.00 kN ↓');
    });

    test('inclined load gets a components step and an axial step', () {
      final s = const SolutionBuilder(lang: Lang.en).build(beam(5,
          supports: [(SupportType.pin, 0), (SupportType.roller, 5)],
          loads: [(20, 2, -60)]));
      final c = s.steps.firstWhere((x) => x.kind == StepKind.components);
      expect(c.lines[0].plain, 'P1x = 20 × cos 60° = 10 kN →');
      expect(c.lines[1].plain, 'P1y = 20 × sin 60° = 17.321 kN ↓');
      final fx = s.steps.firstWhere((x) => x.title == 'ΣFx = 0');
      expect(fx.lines[1].plain, 'HA + 10 = 0');
      expect(fx.lines.last.plain, 'HA = −10 kN');
      expect(s.steps.last.kind, StepKind.axial);
      expect(s.steps.last.lines.first.note, contains('tension'));
    });

    test('millimetres: derivations in kN·mm, results converted to kN·m', () {
      const units = UnitSystem(
          force: Units.kilonewton, length: Units.millimetre, moment: Units.kilonewtonMetre);
      final s = const SolutionBuilder(lang: Lang.en, units: units)
          .build(beam(4, supports: [(SupportType.fixed, 0)], loads: [down(10, 4)]));
      final m = s.steps.firstWhere((x) => x.title == 'ΣM_A = 0');
      expect(m.lines[1].plain, 'MA − 10 × 4000 = 0');
      expect(m.lines.last.plain, 'MA = 10 × 4000 = 40000 kN·mm = 40 kN·m ↺');
    });

    test('an unstable beam explains itself instead of solving', () {
      final s = const SolutionBuilder(lang: Lang.en).build(beam(6,
          supports: [(SupportType.roller, 0), (SupportType.roller, 6)],
          loads: [down(10, 3)]));
      expect(s.isSolved, isFalse);
      expect(s.steps.last.kind, StepKind.unsolvable);
      expect(s.steps.last.explanation, contains('sliding sideways'));
      expect(s.steps.last.detail, contains('replace one roller with a pin'));
    });
  });

  test('text renderer prints every step and the checks', () {
    final text = TextRenderer.render(const SolutionBuilder(lang: Lang.ar).build(example));
    expect(text, contains('RB × 6 − 20 × 3 = 0'));
    expect(text, contains('All checks passed ✓'));
    expect(text, isNot(contains('\u2066')));
  });
}
