/// The explained solution: what the UI, the step player, the practice mode
/// and the command line all render.
library;

import '../diagrams/internal_forces.dart';
import '../model/beam_problem.dart';
import '../model/sign_convention.dart';
import '../statics/equilibrium.dart';
import '../units/unit.dart';
import '../validation/validator.dart';
import 'highlight.dart';
import 'lang.dart';

enum StepKind {
  given,
  freeBody,
  components,
  equilibrium,
  check,
  reactions,
  shear,
  shearDiagram,
  moment,
  momentDiagram,
  maxMoment,
  axial,
  unsolvable,
}

enum TokenRole {
  /// A term of an equation; tapping it explains where it comes from.
  term,

  /// +, −, ×, ÷
  operator,
  equals,

  /// A heading such as ΣM_A or a segment range.
  symbol,

  /// A plain number.
  value,

  /// The answer of a line.
  result,

  /// Words.
  text,
}

class MathToken {
  const MathToken(
    this.text, {
    this.role = TokenRole.text,
    this.explanation,
    this.highlights = const [],
    this.spaceBefore = true,
  });

  final String text;
  final TokenRole role;

  /// Shown when the token is tapped.
  final String? explanation;

  /// What the token points at in the drawing.
  final List<Highlight> highlights;

  /// False for a unary minus glued to the term after it.
  final bool spaceBefore;

  bool get isInteractive => explanation != null || highlights.isNotEmpty;
}

class MathLine {
  const MathLine(this.tokens, {this.note, this.highlights = const []});

  final List<MathToken> tokens;

  /// A short remark in prose shown under the line.
  final String? note;

  /// What the whole line points at.
  final List<Highlight> highlights;

  String get plain {
    final b = StringBuffer();
    for (var i = 0; i < tokens.length; i++) {
      if (i > 0 && tokens[i].spaceBefore) b.write(' ');
      b.write(tokens[i].text);
    }
    return b.toString();
  }
}

/// A named result such as "RB = 10.00 kN ↑" or "Mmax = 30.00 kN·m".
class ResultValue {
  const ResultValue({
    required this.symbol,
    required this.si,
    required this.dimension,
    required this.text,
    this.direction,
    this.x,
    this.highlights = const [],
  });

  final String symbol;
  final double si;
  final Dimension dimension;

  /// Ready to show: symbol, value, unit and direction.
  final String text;
  final String? direction;

  /// Where along the beam the value belongs, if anywhere.
  final double? x;
  final List<Highlight> highlights;
}

class SolutionStep {
  const SolutionStep({
    required this.kind,
    required this.title,
    required this.goal,
    required this.lines,
    required this.explanation,
    this.detail,
    this.highlights = const [],
    this.reveal = Reveal.nothing,
    this.results = const [],
  });

  final StepKind kind;
  final String title;
  final String goal;
  final List<MathLine> lines;

  /// Why this step is done this way, in plain words.
  final String explanation;

  /// The longer answer behind the step's "Explain" button.
  final String? detail;
  final List<Highlight> highlights;
  final Reveal reveal;
  final List<ResultValue> results;
}

class KeyResults {
  const KeyResults({
    required this.reactions,
    this.maxShear,
    this.maxMoment,
    this.maxPositiveMoment,
    this.maxNegativeMoment,
    this.maxAxial,
    this.zeroShear = const [],
  });

  final List<ResultValue> reactions;

  /// Shear of the largest magnitude.
  final ResultValue? maxShear;

  /// Moment of the largest magnitude, with its sign.
  final ResultValue? maxMoment;
  final ResultValue? maxPositiveMoment;
  final ResultValue? maxNegativeMoment;
  final ResultValue? maxAxial;

  /// Where the shear changes sign.
  final List<double> zeroShear;
}

class Solution {
  const Solution({
    required this.problem,
    required this.statics,
    required this.lang,
    required this.units,
    required this.convention,
    required this.steps,
    this.forces,
    this.validation,
    this.results,
  });

  final BeamProblem problem;
  final StaticsSolution statics;
  final InternalForces? forces;
  final ValidationReport? validation;
  final List<SolutionStep> steps;
  final KeyResults? results;
  final Lang lang;
  final UnitSystem units;
  final SignConvention convention;

  bool get isSolved => statics.isSolved && forces != null;

  /// The first step of a given kind, used to jump from a practice question
  /// or a result to where it is worked out.
  int indexOf(StepKind kind) => steps.indexWhere((s) => s.kind == kind);

  /// The equilibrium step that solves [reactionId].
  int stepSolving(String reactionId) => steps.indexWhere((s) =>
      s.kind == StepKind.equilibrium &&
      s.results.any((r) => r.highlights.contains(ReactionHighlight(reactionId))));
}
