import 'dart:io';

import 'package:mechsim_core/io.dart';
import 'package:mechsim_core/mechsim_core.dart';
import 'package:test/test.dart';

import 'helpers.dart';

void main() {
  group('practice', () {
    final problem = beam(8,
        supports: [(SupportType.pin, 0), (SupportType.roller, 8)],
        loads: [down(30, 2)]);
    final session = PracticeSession(const SolutionBuilder(lang: Lang.en).build(problem));
    PracticeQuestion q(String symbol) =>
        session.questions.firstWhere((x) => x.symbol == symbol);

    test('asks for the reactions, a shear, Mmax and where it is', () {
      expect(session.questions.map((x) => x.symbol), ['RA', 'RB', 'V', 'Mmax', 'x']);
      expect(session.prompt(q('RA')), 'Find RA  (↑ +)');
      expect(session.prompt(q('V')), 'Find the shear V at x = 5 m');
    });

    test('a right answer, within rounding', () {
      expect(session.check(q('RA'), 22.5).correct, isTrue);
      expect(session.check(q('RA'), 22.499).correct, isTrue);
      expect(session.check(q('Mmax'), 45).correct, isTrue);
      expect(session.check(q('x'), 2).correct, isTrue);
      expect(session.check(q('V'), -7.5).correct, isTrue);
    });

    test('a swapped reaction points at the equation that gives it', () {
      final f = session.check(q('RA'), 7.5);
      expect(f.correct, isFalse);
      expect(f.mistake, Mistake.otherReaction);
      expect(f.message, 'That is RB, not RA. Review ΣFy = 0.');
      expect(session.solution.steps[f.reviewStep!].title, 'ΣFy = 0');
      final g = session.check(q('RB'), 22.5);
      expect(g.message, 'That is RA, not RB. Review ΣM_A = 0.');
    });

    test('recognises the usual mistakes', () {
      expect(session.check(q('V'), 7.5).mistake, Mistake.sign);
      expect(session.check(q('RA'), 22500).mistake, Mistake.units);
      expect(session.check(q('RA'), 30).mistake, Mistake.wholeLoad);
      expect(session.check(q('RA'), 15).mistake, Mistake.equalShare);
      expect(session.check(q('V'), 22.5).mistake, Mistake.wrongSegment);
      expect(session.check(q('RA'), 3).mistake, Mistake.other);
    });

    test('the answer is only given by Show Solution', () {
      final f = session.check(q('RA'), 3);
      expect(f.message, isNot(contains('22.5')));
      expect(session.answerText(q('RA')), 'RA = 22.50 kN');
    });

    test('Arabic hint names the equation to review', () {
      final ar = PracticeSession(const SolutionBuilder(lang: Lang.ar).build(problem));
      final f = ar.check(ar.questions.first, 1);
      expect(f.message.replaceAll(RegExp('[\u2066-\u2069]'), ''), 'راجع معادلة ΣFy = 0.');
    });

    test('cantilever asks for the reaction moment', () {
      final c = PracticeSession(const SolutionBuilder(lang: Lang.en)
          .build(beam(4, supports: [(SupportType.fixed, 0)], loads: [down(10, 4)])));
      expect(c.questions.map((x) => x.symbol), ['RA', 'MA', 'V', 'Mmax']);
      expect(c.check(c.questions[1], 40).correct, isTrue);
      expect(c.check(c.questions[3], -40).correct, isTrue);
      expect(c.check(c.questions[3], 40).mistake, Mistake.sign);
    });

    test('the generator is reproducible from its seed', () {
      final a = ProblemGenerator(42).generate(PracticeLevel.intermediate);
      final b = ProblemGenerator(42).generate(PracticeLevel.intermediate);
      expect(a, b);
    });
  });

  group('storage', () {
    final problem = beam(6,
        supports: [(SupportType.pin, 0), (SupportType.roller, 6)],
        loads: [down(20, 3), (15, 4, -45)]);

    test('a problem survives JSON', () {
      expect(BeamProblem.fromJson(problem.toJson()), problem);
    });

    test('a newer schema is refused rather than misread', () {
      final json = problem.toJson()..['schema'] = 99;
      expect(() => BeamProblem.fromJson(json), throwsFormatException);
    });

    test('a corrupt entry does not lose the others', () {
      final good = SavedProblem(
          id: 'a', name: 'good', savedAt: DateTime.utc(2026), problem: problem);
      final text = ProblemLibraryCodec.encode([good]).replaceFirst(
          '"problems": [', '"problems": [{"id": 1},');
      final loaded = ProblemLibraryCodec.decode(text);
      expect(loaded.single.name, 'good');
      expect(loaded.single.problem, problem);
    });

    test('file repository saves, replaces, lists newest first, deletes', () async {
      final dir = await Directory.systemTemp.createTemp('mechsim');
      addTearDown(() => dir.delete(recursive: true));
      final file = File('${dir.path}/problems.json');
      final repo = FileProblemRepository(file);
      await repo.save(SavedProblem(
          id: '1', name: 'first', savedAt: DateTime.utc(2026, 1), problem: problem));
      await repo.save(SavedProblem(
          id: '2', name: 'second', savedAt: DateTime.utc(2026, 2), problem: problem));
      await repo.save(SavedProblem(
          id: '1', name: 'first again', savedAt: DateTime.utc(2026, 3), problem: problem));

      final again = FileProblemRepository(file);
      expect((await again.list()).map((p) => p.name), ['first again', 'second']);
      await again.delete('2');
      expect((await FileProblemRepository(file).list()).single.id, '1');
    });
  });
}
