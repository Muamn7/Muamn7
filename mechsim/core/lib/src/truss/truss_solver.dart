/// The truss engine: every joint gives two equations, ΣFx = 0 and ΣFy = 0,
/// in the member forces (tension positive) and the support reactions. The
/// whole set is solved at once here, by Gaussian elimination; the method of
/// joints and the method of sections in the explanation then reach the same
/// numbers one joint or one cut at a time, and the tests hold them to it.
library;

import 'dart:math' as math;

import '../statics/equilibrium.dart' show Determinacy;
import 'truss_problem.dart';

enum TrussAxis { x, y }

/// A support reaction: Ax or Ay, positive → or ↑.
class TrussReaction {
  const TrussReaction({
    required this.supportId,
    required this.node,
    required this.axis,
    required this.symbol,
  });

  final String supportId;
  final String node;
  final TrussAxis axis;
  final String symbol;

  String get id => '$supportId.${axis.name}';
}

enum TrussReason {
  ok,

  /// No joints or no members yet.
  empty,

  /// A member whose two ends are at the same point.
  zeroLength,

  /// A joint with no member, which nothing holds.
  freeJoint,
  noSupports,

  /// Fewer independent restraints than equations: the truss can move or
  /// fold (m + r < 2j, or the members are arranged so that it can).
  mechanism,

  /// More unknowns than equations: m + r > 2j.
  indeterminate,
}

class TrussStability {
  const TrussStability(
    this.status,
    this.reason, {
    required this.members,
    required this.reactions,
    required this.joints,
  });

  final Determinacy status;
  final TrussReason reason;
  final int members;
  final int reactions;
  final int joints;

  bool get isDeterminate => status == Determinacy.determinate;

  /// m + r − 2j: zero for a determinate truss.
  int get degree => members + reactions - 2 * joints;
}

class TrussSolution {
  TrussSolution._(this.problem, this.labels, this.stability, this.reactions,
      this.forces, this.reactionValues);

  final TrussProblem problem;
  final TrussLabels labels;
  final TrussStability stability;
  final List<TrussReaction> reactions;

  /// Member force in N, tension positive, by member id.
  final Map<String, double> forces;

  /// Reaction in N, positive → or ↑, by [TrussReaction.id].
  final Map<String, double> reactionValues;

  bool get isSolved => stability.isDeterminate;

  double force(String memberId) => forces[memberId]!;
  double reaction(String id) => reactionValues[id]!;

  /// Every force that acts on a joint from outside the members: its loads
  /// and its reactions, as (fx, fy).
  (double, double) externalAt(String node) {
    var fx = 0.0, fy = 0.0;
    for (final l in problem.loads) {
      if (l.node == node) {
        fx += l.fx;
        fy += l.fy;
      }
    }
    for (final r in reactions) {
      if (r.node != node) continue;
      final v = reactionValues[r.id] ?? 0;
      if (r.axis == TrussAxis.x) {
        fx += v;
      } else {
        fy += v;
      }
    }
    return (fx, fy);
  }

  /// How far a joint is from balance with the solved forces: zero (to
  /// rounding) when the answer is right.
  double residualAt(String nodeId) {
    var (fx, fy) = externalAt(nodeId);
    final n = problem.node(nodeId)!;
    for (final m in problem.membersAt(nodeId)) {
      final o = problem.node(m.other(nodeId))!;
      final len = problem.lengthOf(m);
      final f = forces[m.id] ?? 0;
      fx += f * (o.x - n.x) / len;
      fy += f * (o.y - n.y) / len;
    }
    return math.sqrt(fx * fx + fy * fy);
  }
}

/// The reactions of a truss's supports, in order of the supports' joints.
List<TrussReaction> trussReactionsOf(TrussProblem p, TrussLabels labels) => [
      for (final s in p.supports)
        for (final axis in s.type == TrussSupportType.pin
            ? const [TrussAxis.x, TrussAxis.y]
            : const [TrussAxis.y])
          TrussReaction(
            supportId: s.id,
            node: s.node,
            axis: axis,
            symbol: '${labels.node(s.node)}${axis.name}',
          ),
    ];

abstract final class TrussSolver {
  static TrussSolution solve(TrussProblem p) {
    final labels = TrussLabels.of(p);
    final reactions = trussReactionsOf(p, labels);
    final m = p.members.length, r = reactions.length, j = p.nodes.length;

    TrussSolution result(Determinacy status, TrussReason reason,
            [Map<String, double> forces = const {},
            Map<String, double> values = const {}]) =>
        TrussSolution._(
          p,
          labels,
          TrussStability(status, reason, members: m, reactions: r, joints: j),
          reactions,
          forces,
          values,
        );

    if (p.nodes.isEmpty || p.members.isEmpty) {
      return result(Determinacy.invalid, TrussReason.empty);
    }
    final size = _size(p);
    if (p.members.any((e) => p.lengthOf(e) <= 1e-9 * size)) {
      return result(Determinacy.invalid, TrussReason.zeroLength);
    }
    if (p.nodes.any((n) => p.membersAt(n.id).isEmpty)) {
      return result(Determinacy.unstable, TrussReason.freeJoint);
    }
    if (p.supports.isEmpty) {
      return result(Determinacy.unstable, TrussReason.noSupports);
    }

    // Rows: ΣFx and ΣFy at each joint. Columns: members, then reactions.
    final index = {for (var i = 0; i < j; i++) p.nodes[i].id: i};
    final n = m + r;
    final a = [for (var i = 0; i < 2 * j; i++) List<double>.filled(n, 0)];
    final b = List<double>.filled(2 * j, 0);
    for (var k = 0; k < m; k++) {
      final mem = p.members[k];
      final na = p.node(mem.a)!, nb = p.node(mem.b)!;
      final len = p.lengthOf(mem);
      final ux = (nb.x - na.x) / len, uy = (nb.y - na.y) / len;
      // Tension pulls each end towards the other.
      a[2 * index[mem.a]!][k] += ux;
      a[2 * index[mem.a]! + 1][k] += uy;
      a[2 * index[mem.b]!][k] -= ux;
      a[2 * index[mem.b]! + 1][k] -= uy;
    }
    for (var k = 0; k < r; k++) {
      final re = reactions[k];
      final row = 2 * index[re.node]! + (re.axis == TrussAxis.x ? 0 : 1);
      a[row][m + k] = 1;
    }
    for (final l in p.loads) {
      final i = index[l.node];
      if (i == null) continue;
      b[2 * i] -= l.fx;
      b[2 * i + 1] -= l.fy;
    }

    final rank = _rank(a, 1e-10);
    if (rank < 2 * j) {
      return result(Determinacy.unstable, TrussReason.mechanism);
    }
    if (n > 2 * j) {
      return result(Determinacy.indeterminate, TrussReason.indeterminate);
    }

    final x = _solveSquare(a, b);
    final scale = math.max(
        1.0, p.loads.fold(0.0, (s, l) => s + l.magnitude.abs()));
    double clean(double v) => v.abs() <= 1e-10 * scale ? 0.0 : v;
    return result(
      Determinacy.determinate,
      TrussReason.ok,
      {for (var k = 0; k < m; k++) p.members[k].id: clean(x[k])},
      {for (var k = 0; k < r; k++) reactions[k].id: clean(x[m + k])},
    );
  }

  static double _size(TrussProblem p) {
    var s = 0.0;
    for (final n in p.nodes) {
      s = math.max(s, math.max(n.x.abs(), n.y.abs()));
    }
    return math.max(1.0, s);
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
        if (f == 0) continue;
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
