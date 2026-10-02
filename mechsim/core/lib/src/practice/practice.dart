/// Practice mode: questions about a beam, and an answer checker that does
/// not just say "wrong" but guesses *which* mistake was made and points at
/// the step to review — without giving the answer away.
library;

import 'dart:math' as math;

import '../diagrams/internal_forces.dart';
import '../explain/lang.dart';
import '../explain/solution.dart';
import '../statics/equilibrium.dart';
import '../units/format.dart';
import '../units/unit.dart';

enum QuestionKind { reaction, shearAt, maxMoment, maxMomentLocation }

class PracticeQuestion {
  const PracticeQuestion({
    required this.kind,
    required this.symbol,
    required this.answerSi,
    required this.dimension,
    this.reactionId,
    this.x,
  });

  final QuestionKind kind;

  /// What is asked for: RA, MA, V, Mmax, x.
  final String symbol;
  final double answerSi;
  final Dimension dimension;
  final String? reactionId;

  /// For a shear question, where the section is.
  final double? x;
}

/// What the checker thinks went wrong.
enum Mistake {
  none,
  sign,
  units,
  otherReaction,
  wholeLoad,
  equalShare,
  wrongSegment,
  notTheLargest,
  other,
}

class AnswerFeedback {
  const AnswerFeedback({
    required this.correct,
    required this.mistake,
    required this.message,
    this.reviewStep,
  });

  final bool correct;
  final Mistake mistake;
  final String message;

  /// The solution step to look at, opened by "Show Solution".
  final int? reviewStep;
}

/// Builds the questions for a solved beam and checks answers to them.
class PracticeSession {
  PracticeSession(this.solution) : questions = _questions(solution);

  final Solution solution;
  final List<PracticeQuestion> questions;

  UnitSystem get units => solution.units;
  _PracticeTexts get _t => _PracticeTexts.of(solution.lang);

  static List<PracticeQuestion> _questions(Solution s) {
    if (!s.isSolved) return const [];
    final statics = s.statics;
    final forces = s.forces!;
    final list = <PracticeQuestion>[];
    for (final r in statics.reactions) {
      final v = statics.valueOf(r.id);
      // A zero horizontal reaction is shown in the solution but is not much
      // of a question.
      if (r.kind == ReactionKind.horizontal && v == 0) continue;
      list.add(PracticeQuestion(
        kind: QuestionKind.reaction,
        symbol: r.symbol,
        answerSi: v,
        dimension: r.kind == ReactionKind.moment ? Dimension.moment : Dimension.force,
        reactionId: r.id,
      ));
    }

    // Shear in the most instructive segment: a negative one if there is one.
    final pieces = forces.shear.pieces;
    if (pieces.isNotEmpty) {
      final negative = pieces.where((p) => p.start < -1e-9).toList();
      final piece = negative.isNotEmpty
          ? negative.first
          : pieces.firstWhere((p) => p.start.abs() > 1e-9, orElse: () => pieces.first);
      list.add(PracticeQuestion(
        kind: QuestionKind.shearAt,
        symbol: 'V',
        answerSi: piece.start,
        dimension: Dimension.force,
        x: _niceMidpoint(piece.x0, piece.x1),
      ));
    }

    final peak = forces.moment.absMaximum;
    if (peak != null && peak.value.abs() > 1e-9) {
      list.add(PracticeQuestion(
        kind: QuestionKind.maxMoment,
        symbol: 'Mmax',
        answerSi: peak.value,
        dimension: Dimension.moment,
      ));
      final crossings = forces.shear.signChanges();
      if (crossings.any((x) => (x - peak.x).abs() < 1e-9)) {
        list.add(PracticeQuestion(
          kind: QuestionKind.maxMomentLocation,
          symbol: 'x',
          answerSi: peak.x,
          dimension: Dimension.length,
        ));
      }
    }
    return list;
  }

  /// A point inside a segment that reads well: the midpoint, rounded to a
  /// quarter metre when that keeps it strictly inside.
  static double _niceMidpoint(double a, double b) {
    final mid = (a + b) / 2;
    final rounded = (mid * 4).round() / 4;
    return (rounded > a + 1e-9 && rounded < b - 1e-9) ? rounded : mid;
  }

  String unitOf(PracticeQuestion q) => units.unitFor(q.dimension).symbol;

  String prompt(PracticeQuestion q) {
    final x = q.x == null
        ? ''
        : '${Num.compact(units.toDisplay(q.x!, Dimension.length))} ${units.length.symbol}';
    return switch (q.kind) {
      QuestionKind.reaction => _t.findReaction(q.symbol, _directionHint(q)),
      QuestionKind.shearAt => _t.findShear(x),
      QuestionKind.maxMoment => _t.findMaxMoment,
      QuestionKind.maxMomentLocation => _t.findMaxMomentLocation,
    };
  }

  String _directionHint(PracticeQuestion q) {
    final r = solution.statics.reaction(q.reactionId!);
    return switch (r.kind) {
      ReactionKind.horizontal => '→ +',
      ReactionKind.vertical => '↑ +',
      ReactionKind.moment => '↺ +',
    };
  }

  /// Checks an answer typed in display units.
  AnswerFeedback check(PracticeQuestion q, double answerDisplay) {
    final expected = units.toDisplay(q.answerSi, q.dimension);
    bool near(double a, double b) =>
        (a - b).abs() <= math.max(0.011, 0.005 * b.abs());

    if (near(answerDisplay, expected)) {
      return AnswerFeedback(
          correct: true, mistake: Mistake.none, message: _t.correct);
    }

    final review = reviewStep(q);
    AnswerFeedback wrong(Mistake m, String message) => AnswerFeedback(
        correct: false, mistake: m, message: message, reviewStep: review);

    if (expected.abs() > 1e-9 && near(answerDisplay, -expected)) {
      return wrong(Mistake.sign, _t.signMistake(q.kind == QuestionKind.reaction));
    }
    for (final factor in const [1000.0, 0.001, 1e6, 1e-6]) {
      if (expected.abs() > 1e-9 && near(answerDisplay, expected * factor)) {
        return wrong(Mistake.units, _t.unitsMistake(unitOf(q)));
      }
    }

    switch (q.kind) {
      case QuestionKind.reaction:
        final r = solution.statics.reaction(q.reactionId!);
        for (final other in solution.statics.reactions) {
          if (other.id == r.id || other.kind != r.kind) continue;
          final v = units.toDisplay(solution.statics.valueOf(other.id), q.dimension);
          if (near(answerDisplay, v) || near(answerDisplay, -v)) {
            return wrong(Mistake.otherReaction,
                _t.otherReaction(other.symbol, q.symbol, _equationTitle(review)));
          }
        }
        if (r.kind == ReactionKind.vertical) {
          final total = units.toDisplay(
              -solution.problem.pointLoads.fold(0.0, (s, l) => s + l.fy),
              Dimension.force);
          if (near(answerDisplay, total) && solution.statics.reactions
              .where((x) => x.kind == ReactionKind.vertical).length > 1) {
            return wrong(Mistake.wholeLoad, _t.wholeLoad(_equationTitle(review)));
          }
          if (near(answerDisplay, total / 2)) {
            return wrong(Mistake.equalShare, _t.equalShare(_equationTitle(review)));
          }
        }
        return wrong(Mistake.other, _t.reviewEquation(_equationTitle(review)));
      case QuestionKind.shearAt:
        final forces = solution.forces!;
        for (final piece in forces.shear.pieces) {
          final v = units.toDisplay(piece.start, Dimension.force);
          if (near(answerDisplay, v)) {
            return wrong(Mistake.wrongSegment, _t.wrongSegment);
          }
        }
        return wrong(Mistake.other, _t.shearHint);
      case QuestionKind.maxMoment:
        final forces = solution.forces!;
        for (final x in forces.breakpoints) {
          for (final side in [forces.moment.leftLimit(x), forces.moment.rightLimit(x)]) {
            final v = units.toDisplay(side, Dimension.moment);
            if (near(answerDisplay, v)) {
              return wrong(Mistake.notTheLargest,
                  _t.notTheLargest('${Num.compact(units.toDisplay(x, Dimension.length))} ${units.length.symbol}'));
            }
          }
        }
        return wrong(Mistake.other, _t.maxMomentHint);
      case QuestionKind.maxMomentLocation:
        return wrong(Mistake.other, _t.locationHint);
    }
  }

  /// The solution step that works out the answer to [q].
  int? reviewStep(PracticeQuestion q) {
    final index = switch (q.kind) {
      QuestionKind.reaction => solution.stepSolving(q.reactionId!),
      QuestionKind.shearAt => solution.indexOf(StepKind.shear),
      QuestionKind.maxMoment => solution.indexOf(StepKind.momentDiagram),
      QuestionKind.maxMomentLocation => solution.indexOf(StepKind.maxMoment),
    };
    return index < 0 ? null : index;
  }

  String _equationTitle(int? step) =>
      step == null ? '' : solution.steps[step].title;

  /// The worked answer, revealed only on "Show Solution".
  String answerText(PracticeQuestion q) {
    final v = units.toDisplay(q.answerSi, q.dimension);
    return '${q.symbol} = ${Num.fixed(v)} ${unitOf(q)}';
  }
}

abstract class _PracticeTexts {
  const _PracticeTexts();

  static _PracticeTexts of(Lang lang) =>
      lang == Lang.ar ? const _ArabicPractice() : const _EnglishPractice();

  String findReaction(String symbol, String convention);
  String findShear(String x);
  String get findMaxMoment;
  String get findMaxMomentLocation;
  String get correct;
  String signMistake(bool reaction);
  String unitsMistake(String unit);
  String otherReaction(String other, String asked, String equation);
  String wholeLoad(String equation);
  String equalShare(String equation);
  String reviewEquation(String equation);
  String get wrongSegment;
  String get shearHint;
  String notTheLargest(String x);
  String get maxMomentHint;
  String get locationHint;
}

class _ArabicPractice extends _PracticeTexts {
  const _ArabicPractice();

  String m(String s) => '\u2066$s\u2069';

  @override
  String findReaction(String symbol, String convention) =>
      'أوجد ${m(symbol)}  (${m(convention)})';
  @override
  String findShear(String x) => 'أوجد قوة القص V عند ${m('x = $x')}';
  @override
  String get findMaxMoment => 'أوجد أقصى عزم Mmax (بإشارته)';
  @override
  String get findMaxMomentLocation => 'أين يقع Mmax؟  x = ?';
  @override
  String get correct => '✓ صحيح';
  @override
  String signMistake(bool reaction) => reaction
      ? 'القيمة صحيحة لكن الإشارة خاطئة. افترضنا الاتجاه الموجب؛ هل يعمل رد الفعل فعلًا في هذا الاتجاه؟'
      : 'القيمة صحيحة لكن الإشارة خاطئة. راجع اصطلاح الإشارات: القص الموجب يرفع الجزء الأيسر، والعزم الموجب Sagging.';
  @override
  String unitsMistake(String unit) => 'الرقم صحيح لكن بوحدة أخرى. اكتب الإجابة بوحدة $unit.';
  @override
  String otherReaction(String other, String asked, String equation) =>
      'هذه قيمة ${m(other)} وليست ${m(asked)}. راجع معادلة ${m(equation)}.';
  @override
  String wholeLoad(String equation) =>
      'وضعت الحمل كله على مسند واحد. المساند تتقاسم الحمل حسب البعد: راجع معادلة ${m(equation)}.';
  @override
  String equalShare(String equation) =>
      'قسمت الحمل بالتساوي، لكن الحمل ليس في المنتصف. راجع معادلة ${m(equation)}.';
  @override
  String reviewEquation(String equation) => 'راجع معادلة ${m(equation)}.';
  @override
  String get wrongSegment =>
      'هذه قيمة القص في جزء آخر من الكمرة. خذ فقط القوى الواقعة على يسار المقطع.';
  @override
  String get shearHint =>
      'اقطع الكمرة عند المقطع واجمع القوى الرأسية على يساره: للأعلى موجبة وللأسفل سالبة.';
  @override
  String notTheLargest(String x) =>
      'هذا هو العزم عند ${m('x = $x')}، لكنه ليس الأكبر. أين تغيّر V إشارتها؟';
  @override
  String get maxMomentHint =>
      'Mmax يقع حيث تغيّر V إشارتها، وقيمته = مساحة SFD حتى تلك النقطة.';
  @override
  String get locationHint => 'انظر إلى SFD: أين تغيّر قوة القص إشارتها؟';
}

class _EnglishPractice extends _PracticeTexts {
  const _EnglishPractice();

  @override
  String findReaction(String symbol, String convention) =>
      'Find $symbol  ($convention)';
  @override
  String findShear(String x) => 'Find the shear V at x = $x';
  @override
  String get findMaxMoment => 'Find the maximum moment Mmax (with its sign)';
  @override
  String get findMaxMomentLocation => 'Where is Mmax?  x = ?';
  @override
  String get correct => '✓ Correct';
  @override
  String signMistake(bool reaction) => reaction
      ? 'Right size, wrong sign. We assumed the positive direction; does the reaction really act that way?'
      : 'Right size, wrong sign. Check the convention: positive shear lifts the left part, positive moment is sagging.';
  @override
  String unitsMistake(String unit) => 'The number is right but in another unit. Give the answer in $unit.';
  @override
  String otherReaction(String other, String asked, String equation) =>
      'That is $other, not $asked. Review $equation.';
  @override
  String wholeLoad(String equation) =>
      'You put the whole load on one support. The supports share it according to distance: review $equation.';
  @override
  String equalShare(String equation) =>
      'You split the load equally, but it is not in the middle. Review $equation.';
  @override
  String reviewEquation(String equation) => 'Review $equation.';
  @override
  String get wrongSegment =>
      'That is the shear in another part of the beam. Only the forces left of the cut count.';
  @override
  String get shearHint =>
      'Cut the beam at the section and add the vertical forces to its left: up positive, down negative.';
  @override
  String notTheLargest(String x) =>
      'That is the moment at x = $x, but not the largest. Where does V change sign?';
  @override
  String get maxMomentHint =>
      'Mmax is where V changes sign, and equals the area of the SFD up to that point.';
  @override
  String get locationHint => 'Look at the SFD: where does the shear change sign?';
}

/// Exposes the diagram kind a question is about, for the UI to highlight.
DiagramKind? diagramOf(PracticeQuestion q) => switch (q.kind) {
      QuestionKind.shearAt => DiagramKind.shear,
      QuestionKind.maxMoment || QuestionKind.maxMomentLocation => DiagramKind.moment,
      QuestionKind.reaction => null,
    };
