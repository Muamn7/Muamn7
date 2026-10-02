/// Calculation Engine, part 1: reactions and the equilibrium equations.
///
/// The three equations ΣFx = 0, ΣFy = 0 and ΣM = 0 are built term by term
/// from the problem, never typed in. The same [EquilibriumEquation] objects
/// feed the matrix solver here and the step-by-step explanation, so what the
/// student reads is exactly what was solved.
library;

import '../model/beam_problem.dart';
import '../model/labels.dart';
import 'actions.dart';

enum ReactionKind { horizontal, vertical, moment }

/// An unknown support reaction. It is *assumed* to act in the positive
/// physical direction (→, ↑, ↺); a negative solved value means it acts the
/// other way.
class Reaction {
  const Reaction({
    required this.supportId,
    required this.kind,
    required this.x,
    required this.symbol,
  });

  final String supportId;
  final ReactionKind kind;
  final double x;

  /// HA, RA or MA for a support at point A.
  final String symbol;

  String get id => '$supportId.${kind.name}';

  Action asAction(double value) => switch (kind) {
        ReactionKind.horizontal => PointForce(id, x, fx: value),
        ReactionKind.vertical => PointForce(id, x, fy: value),
        ReactionKind.moment => PointCouple(id, x, value),
      };
}

/// The reactions a support provides, in the order a textbook lists them.
List<ReactionKind> reactionKindsOf(SupportType type) => switch (type) {
      SupportType.pin => const [ReactionKind.horizontal, ReactionKind.vertical],
      SupportType.roller => const [ReactionKind.vertical],
      SupportType.fixed => const [
          ReactionKind.horizontal,
          ReactionKind.vertical,
          ReactionKind.moment,
        ],
    };

List<Reaction> reactionsOf(BeamProblem problem, ProblemLabels labels) {
  final supports = [...problem.supports]..sort((a, b) => a.x.compareTo(b.x));
  return [
    for (final s in supports)
      for (final kind in reactionKindsOf(s.type))
        Reaction(
          supportId: s.id,
          kind: kind,
          x: s.x,
          symbol: '${_prefix(kind)}${labels.pointOf(s.id)}',
        ),
  ];
}

String _prefix(ReactionKind kind) => switch (kind) {
      ReactionKind.horizontal => 'H',
      ReactionKind.vertical => 'R',
      ReactionKind.moment => 'M',
    };

enum EquationKind { sumFx, sumFy, sumMoment }

/// One term of an equilibrium equation, in physical sign (→, ↑, ↺ positive).
class EquationTerm {
  /// A term that contains an unknown reaction: [coefficient] × unknown.
  /// For a moment equation the coefficient is the signed arm (x − x₀) of a
  /// vertical reaction, or 1 for a reaction couple.
  const EquationTerm.unknown(this.sourceId, double this.coefficient,
      {this.arm})
      : knownValue = null,
        component = null;

  /// A term whose value is known: a load, or a reaction already solved.
  /// [component] is the force component that produces it and [arm] its
  /// signed lever arm when the term is a moment.
  const EquationTerm.known(this.sourceId, double this.knownValue,
      {this.component, this.arm})
      : coefficient = null;

  final String sourceId;
  final double? coefficient;
  final double? knownValue;
  final double? component;
  final double? arm;

  bool get isUnknown => coefficient != null;

  /// The term's value once every unknown is replaced by [values].
  double evaluate(Map<String, double> values) => isUnknown
      ? coefficient! * (values[sourceId] ?? double.nan)
      : knownValue!;
}

class EquilibriumEquation {
  const EquilibriumEquation(this.kind, this.terms, {this.about});

  final EquationKind kind;

  /// For a moment equation, the x of the moment centre.
  final double? about;
  final List<EquationTerm> terms;

  Iterable<String> get unknownIds =>
      terms.where((t) => t.isUnknown).map((t) => t.sourceId);

  /// What the left-hand side adds up to once [values] are substituted. For
  /// a solved problem this is zero (to rounding).
  double residual(Map<String, double> values) =>
      terms.fold(0.0, (sum, t) => sum + t.evaluate(values));

  /// The same equation with the reactions in [values] turned into known
  /// terms.
  EquilibriumEquation substitute(Map<String, double> values) =>
      EquilibriumEquation(kind, [
        for (final t in terms)
          if (t.isUnknown && values.containsKey(t.sourceId))
            EquationTerm.known(t.sourceId, t.coefficient! * values[t.sourceId]!,
                component: kind == EquationKind.sumMoment && t.arm == null
                    ? null
                    : values[t.sourceId],
                arm: t.arm)
          else
            t,
      ], about: about);

  /// Solves for the single unknown left in the equation.
  double solveSingle(Map<String, double> known) {
    final remaining = unknownIds.where((id) => !known.containsKey(id)).toList();
    if (remaining.length != 1) {
      throw StateError('Equation has ${remaining.length} unknowns, not 1');
    }
    var constant = 0.0;
    var coefficient = 0.0;
    for (final t in terms) {
      if (t.isUnknown && t.sourceId == remaining.single) {
        coefficient += t.coefficient!;
      } else {
        constant += t.evaluate(known);
      }
    }
    return -constant / coefficient;
  }
}

/// Builds equilibrium equations for a problem.
class EquationBuilder {
  EquationBuilder(this.problem, this.reactions);

  final BeamProblem problem;
  final List<Reaction> reactions;

  List<Load> get _loads =>
      [...problem.loads]..sort((a, b) => a.x.compareTo(b.x));

  EquilibriumEquation sumFx() => EquilibriumEquation(EquationKind.sumFx, [
        for (final r in reactions)
          if (r.kind == ReactionKind.horizontal)
            EquationTerm.unknown(r.id, 1),
        for (final l in _loads)
          if (l is PointLoad && l.fx != 0)
            EquationTerm.known(l.id, l.fx, component: l.fx),
      ]);

  /// ΣFy. A distributed load enters as its resultant; a couple does not
  /// enter at all (it is a pure moment).
  EquilibriumEquation sumFy() => EquilibriumEquation(EquationKind.sumFy, [
        for (final r in reactions)
          if (r.kind == ReactionKind.vertical) EquationTerm.unknown(r.id, 1),
        for (final l in _loads)
          if (_fy(l) != 0) EquationTerm.known(l.id, _fy(l), component: _fy(l)),
      ]);

  /// ΣM about the point (x0, 0), counter-clockwise positive. Forces whose
  /// line of action passes through the point are left out: their moment is
  /// zero, and the explanation says so. A distributed load acts through its
  /// resultant at its centroid; a couple has the same moment about every
  /// point.
  EquilibriumEquation sumMoment(double x0) =>
      EquilibriumEquation(EquationKind.sumMoment, [
        for (final r in reactions)
          if (r.kind == ReactionKind.moment)
            EquationTerm.unknown(r.id, 1)
          else if (r.kind == ReactionKind.vertical && !_same(r.x, x0))
            EquationTerm.unknown(r.id, r.x - x0, arm: r.x - x0),
        for (final l in _loads)
          if (l is PointMoment && l.magnitude != 0)
            EquationTerm.known(l.id, l.moment)
          else if (_fy(l) != 0 && !_same(_at(l), x0))
            EquationTerm.known(l.id, (_at(l) - x0) * _fy(l),
                component: _fy(l), arm: _at(l) - x0),
      ], about: x0);

  /// The vertical force a load puts on the beam (its resultant).
  static double _fy(Load l) => switch (l) {
        PointLoad() => l.fy,
        DistributedLoad() => l.fy,
        PointMoment() => 0,
      };

  /// Where that force acts.
  static double _at(Load l) => switch (l) {
        DistributedLoad() => l.centroid,
        _ => l.x,
      };

  static bool _same(double a, double b) => (a - b).abs() < 1e-9;
}

enum Determinacy { determinate, unstable, indeterminate, invalid }

enum StabilityReason {
  ok,
  noBeam,
  noSupports,
  elementOffBeam,
  noHorizontalRestraint,
  concurrentReactions,
  tooFewReactions,
  tooManyReactions,
}

class StabilityReport {
  const StabilityReport(this.status, this.reason,
      {required this.unknowns, this.degree = 0});

  final Determinacy status;
  final StabilityReason reason;
  final int unknowns;

  /// Degree of static indeterminacy (unknowns − 3) when indeterminate.
  final int degree;

  bool get isDeterminate => status == Determinacy.determinate;
}

class StaticsSolution {
  StaticsSolution._(this.problem, this.labels, this.stability, this.reactions,
      this.values);

  final BeamProblem problem;
  final ProblemLabels labels;
  final StabilityReport stability;
  final List<Reaction> reactions;

  /// Solved reaction values in SI, keyed by [Reaction.id]. Empty unless the
  /// problem is determinate.
  final Map<String, double> values;

  bool get isSolved => stability.isDeterminate;

  Reaction reaction(String id) => reactions.firstWhere((r) => r.id == id);

  Reaction? reactionBySymbol(String symbol) {
    for (final r in reactions) {
      if (r.symbol == symbol) return r;
    }
    return null;
  }

  double valueOf(String reactionId) => values[reactionId]!;

  List<Action> get loadActions => [
        for (final l in problem.loads)
          switch (l) {
            PointLoad() => PointForce(l.id, l.x, fx: l.fx, fy: l.fy),
            DistributedLoad() => DistributedForce(l.id, l.x, l.x2, l.q1, l.q2),
            PointMoment() => PointCouple(l.id, l.x, l.moment),
          },
      ];

  List<Action> get reactionActions => [
        for (final r in reactions)
          if (values.containsKey(r.id)) r.asAction(values[r.id]!),
      ];

  List<Action> get allActions => [...loadActions, ...reactionActions];

  EquationBuilder get equations => EquationBuilder(problem, reactions);
}

/// Solves the reactions of a statically determinate beam.
///
/// The solve itself is a 3×3 linear system (ΣFx, ΣFy, ΣM about x = 0) by
/// Gaussian elimination with partial pivoting. It is deliberately a
/// different route from the step-by-step order the explanation takes, so
/// the tests can check one against the other.
abstract final class StaticsSolver {
  static StaticsSolution solve(BeamProblem problem) {
    final labels = ProblemLabels.of(problem);
    final reactions = reactionsOf(problem, labels);
    final n = reactions.length;

    StaticsSolution result(StabilityReport report,
            [Map<String, double> values = const {}]) =>
        StaticsSolution._(problem, labels, report, reactions, values);

    if (!problem.hasBeam) {
      return result(StabilityReport(Determinacy.invalid, StabilityReason.noBeam,
          unknowns: n));
    }
    final tol = 1e-9 * (problem.length > 1 ? problem.length : 1);
    final offBeam = [
      ...problem.supports.map((s) => s.x),
      for (final l in problem.loads) ...l.positions,
    ].any((x) => x < -tol || x > problem.length + tol);
    if (offBeam) {
      return result(StabilityReport(
          Determinacy.invalid, StabilityReason.elementOffBeam,
          unknowns: n));
    }
    if (problem.supports.isEmpty) {
      return result(StabilityReport(
          Determinacy.unstable, StabilityReason.noSupports,
          unknowns: 0));
    }

    final builder = EquationBuilder(problem, reactions);
    final equations = [builder.sumFx(), builder.sumFy(), builder.sumMoment(0)];
    final matrix = [
      for (final eq in equations)
        [
          for (final r in reactions)
            eq.terms
                .where((t) => t.isUnknown && t.sourceId == r.id)
                .fold(0.0, (sum, t) => sum + t.coefficient!),
        ],
    ];
    final rhs = [
      for (final eq in equations)
        -eq.terms
            .where((t) => !t.isUnknown)
            .fold(0.0, (sum, t) => sum + t.knownValue!),
    ];

    final rank = _rank(matrix, tol);
    if (rank < 3) {
      return result(StabilityReport(
          Determinacy.unstable, _whyUnstable(reactions, n),
          unknowns: n));
    }
    if (n > 3) {
      return result(StabilityReport(
          Determinacy.indeterminate, StabilityReason.tooManyReactions,
          unknowns: n, degree: n - 3));
    }

    final solution = _solveSquare(matrix, rhs);
    // Round-off below a billionth of the applied load is noise: a reaction
    // that should be zero is reported as exactly zero.
    final scale = problem.loads
        .fold(0.0, (sum, l) => sum + _size(l, problem.length))
        .clamp(1.0, double.infinity);
    final momentScale = scale * (problem.length > 1 ? problem.length : 1);
    double clean(int i) {
      final noise = reactions[i].kind == ReactionKind.moment
          ? 1e-12 * momentScale
          : 1e-12 * scale;
      return solution[i].abs() <= noise ? 0.0 : solution[i];
    }

    return result(
      StabilityReport(Determinacy.determinate, StabilityReason.ok, unknowns: n),
      {for (var i = 0; i < n; i++) reactions[i].id: clean(i)},
    );
  }

  /// A load's size as a force, to tell round-off from a real value.
  static double _size(Load l, double length) => switch (l) {
        PointLoad() => l.magnitude,
        DistributedLoad() => l.resultant.abs(),
        PointMoment() => l.magnitude / (length > 1 ? length : 1),
      };

  static StabilityReason _whyUnstable(List<Reaction> reactions, int n) {
    if (!reactions.any((r) => r.kind == ReactionKind.horizontal)) {
      return StabilityReason.noHorizontalRestraint;
    }
    final hasCouple = reactions.any((r) => r.kind == ReactionKind.moment);
    final xs = reactions.map((r) => r.x).toList();
    final concurrent = xs.every((x) => (x - xs.first).abs() < 1e-9);
    if (!hasCouple && concurrent) return StabilityReason.concurrentReactions;
    return StabilityReason.tooFewReactions;
  }

  static int _rank(List<List<double>> source, double tol) {
    final m = [for (final row in source) [...row]];
    final rows = m.length;
    final cols = rows == 0 ? 0 : m.first.length;
    var rank = 0;
    for (var c = 0; c < cols && rank < rows; c++) {
      var pivot = rank;
      for (var r = rank + 1; r < rows; r++) {
        if (m[r][c].abs() > m[pivot][c].abs()) pivot = r;
      }
      if (m[pivot][c].abs() <= tol) continue;
      final tmp = m[rank];
      m[rank] = m[pivot];
      m[pivot] = tmp;
      for (var r = rank + 1; r < rows; r++) {
        final f = m[r][c] / m[rank][c];
        for (var k = c; k < cols; k++) {
          m[r][k] -= f * m[rank][k];
        }
      }
      rank++;
    }
    return rank;
  }

  static List<double> _solveSquare(List<List<double>> a, List<double> b) {
    final n = b.length;
    final m = [
      for (var i = 0; i < n; i++) [...a[i], b[i]],
    ];
    for (var c = 0; c < n; c++) {
      var pivot = c;
      for (var r = c + 1; r < n; r++) {
        if (m[r][c].abs() > m[pivot][c].abs()) pivot = r;
      }
      final tmp = m[c];
      m[c] = m[pivot];
      m[pivot] = tmp;
      for (var r = 0; r < n; r++) {
        if (r == c) continue;
        final f = m[r][c] / m[c][c];
        if (f == 0) continue;
        for (var k = c; k <= n; k++) {
          m[r][k] -= f * m[c][k];
        }
      }
    }
    return [for (var i = 0; i < n; i++) m[i][n] / m[i][i]];
  }
}
