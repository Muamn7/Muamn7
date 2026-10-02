/// Calculation Engine, part 2: shear, moment and axial force along the beam
/// by the method of sections.
///
/// Cut the beam at x and keep the part to the left of the cut. With the
/// convention in BeamConvention:
///   V(x) = Σ Fy of the actions left of the cut
///   M(x) = Σ Fy·(x − xᵢ) − Σ Cᵢ      (moments about the cut, sagging +)
///   N(x) = −Σ Fx of the actions left of the cut   (tension +)
/// Each segment between two consecutive points of interest becomes one
/// polynomial piece; the pieces are what the SFD and BMD are drawn from.
library;

import '../model/beam_problem.dart';
import '../statics/actions.dart';
import '../statics/equilibrium.dart';
import 'polynomial.dart';

enum DiagramKind { shear, moment, axial }

class InternalForces {
  InternalForces(this.shear, this.moment, this.axial, this.breakpoints,
      this.actions);

  final PiecewiseFunction shear;
  final PiecewiseFunction moment;
  final PiecewiseFunction axial;

  /// The ends of the beam and every point where something is applied.
  final List<double> breakpoints;

  /// The loads and solved reactions the diagrams were built from.
  final List<Action> actions;

  PiecewiseFunction of(DiagramKind kind) => switch (kind) {
        DiagramKind.shear => shear,
        DiagramKind.moment => moment,
        DiagramKind.axial => axial,
      };

  /// True when some part of the beam carries axial force.
  bool get hasAxial => axial.pieces.any((p) => p.p.c.any((v) => v.abs() > 1e-9));

  /// The actions applied exactly at [x].
  List<Action> actionsAt(double x) =>
      [for (final a in actions) if ((a.x - x).abs() < 1e-9) a];

  /// The actions strictly to the left of a cut made inside a segment that
  /// starts at [segmentStart] (everything at or before it).
  List<Action> actionsLeftOf(double segmentStart) =>
      [for (final a in actions) if (a.x <= segmentStart + 1e-9) a];
}

abstract final class InternalForceAnalyzer {
  static InternalForces analyze(StaticsSolution solution) {
    if (!solution.isSolved) {
      throw StateError('Internal forces need a solved, determinate beam');
    }
    final problem = solution.problem;
    final actions = solution.allActions;
    final breakpoints = _breakpoints(problem, actions);

    final shear = <Piece>[];
    final moment = <Piece>[];
    final axial = <Piece>[];
    for (var i = 0; i < breakpoints.length - 1; i++) {
      final a = breakpoints[i], b = breakpoints[i + 1];
      var v = Polynomial.zero;
      var m = Polynomial.zero;
      var n = Polynomial.zero;
      for (final action in actions) {
        if (action.x > a + 1e-9) continue; // right of the cut
        switch (action) {
          case PointForce(:final fx, :final fy, :final x):
            v += Polynomial.constant(fy);
            m += Polynomial.shiftedLinear(fy, x);
            n -= Polynomial.constant(fx);
          case PointCouple(moment: final c):
            m -= Polynomial.constant(c);
        }
      }
      shear.add(Piece(a, b, v));
      moment.add(Piece(a, b, m));
      axial.add(Piece(a, b, n));
    }
    return InternalForces(
      PiecewiseFunction(shear),
      PiecewiseFunction(moment),
      PiecewiseFunction(axial),
      breakpoints,
      actions,
    );
  }

  static List<double> _breakpoints(BeamProblem problem, List<Action> actions) {
    final xs = <double>[0, problem.length];
    for (final a in actions) {
      xs.add(a.x.clamp(0.0, problem.length).toDouble());
    }
    xs.sort();
    final unique = <double>[];
    for (final x in xs) {
      if (unique.isEmpty || (x - unique.last).abs() > 1e-9) unique.add(x);
    }
    return unique;
  }
}
