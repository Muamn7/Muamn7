/// Validation: after every solve the engine checks its own answer, and the
/// app shows the checks to the student.
///
/// None of these checks reuse the route the answer was found by. Equilibrium
/// is re-summed from the flat list of actions about two points the solver
/// never used; the diagrams are checked against the loads with the
/// differential relations (dM/dx = V, jumps equal to point loads) and the
/// area rule (ΔM = area under the SFD).
library;

import 'dart:math' as math;

import '../diagrams/internal_forces.dart';
import '../statics/actions.dart';
import '../statics/equilibrium.dart';

enum CheckKind {
  sumFx,
  sumFy,
  sumMomentLeftEnd,
  sumMomentRightEnd,
  shearClosesAtEnd,
  momentClosesAtEnd,
  axialClosesAtEnd,
  shearJumpsMatchLoads,
  momentJumpsMatchCouples,
  slopeEqualsShear,
  areaRule,
}

class CheckItem {
  const CheckItem(this.kind, this.residual, this.tolerance, {this.where});

  final CheckKind kind;

  /// How far from exact the check came out (zero would be perfect).
  final double residual;
  final double tolerance;

  /// Where the worst residual was found, if the check runs along the beam.
  final double? where;

  bool get passed => residual.abs() <= tolerance;
}

class ValidationReport {
  const ValidationReport(this.items);

  final List<CheckItem> items;

  bool get allPassed => items.every((i) => i.passed);

  CheckItem? operator [](CheckKind kind) {
    for (final i in items) {
      if (i.kind == kind) return i;
    }
    return null;
  }
}

abstract final class SolutionValidator {
  static ValidationReport validate(
      StaticsSolution solution, InternalForces forces) {
    final problem = solution.problem;
    final actions = solution.allActions;
    final length = problem.length;

    var forceScale = 0.0;
    for (final a in actions) {
      if (a is PointForce) forceScale += a.fx.abs() + a.fy.abs();
      if (a is PointCouple) forceScale += a.moment.abs() / math.max(length, 1);
    }
    forceScale = math.max(forceScale, 1);
    final fTol = 1e-9 * forceScale;
    final mTol = fTol * math.max(length, 1);

    double sumFx = 0, sumFy = 0, mLeft = 0, mRight = 0;
    for (final a in actions) {
      switch (a) {
        case PointForce():
          sumFx += a.fx;
          sumFy += a.fy;
          mLeft += a.momentAbout(0);
          mRight += a.momentAbout(length);
        case PointCouple():
          mLeft += a.moment;
          mRight += a.moment;
      }
    }

    final items = <CheckItem>[
      CheckItem(CheckKind.sumFx, sumFx, fTol),
      CheckItem(CheckKind.sumFy, sumFy, fTol),
      CheckItem(CheckKind.sumMomentLeftEnd, mLeft, mTol),
      CheckItem(CheckKind.sumMomentRightEnd, mRight, mTol),
    ];

    // The diagrams must come back to zero past the right end: the last
    // value plus whatever is applied exactly at x = L.
    double atEnd(double Function(Action) pick) =>
        forces.actionsAt(length).fold(0.0, (s, a) => s + pick(a));
    final vEnd = forces.shear.leftLimit(length) +
        atEnd((a) => a is PointForce ? a.fy : 0);
    final mEnd = forces.moment.leftLimit(length) -
        atEnd((a) => a is PointCouple ? a.moment : 0);
    final nEnd = forces.axial.leftLimit(length) -
        atEnd((a) => a is PointForce ? a.fx : 0);
    items
      ..add(CheckItem(CheckKind.shearClosesAtEnd, vEnd, fTol))
      ..add(CheckItem(CheckKind.momentClosesAtEnd, mEnd, mTol))
      ..add(CheckItem(CheckKind.axialClosesAtEnd, nEnd, fTol));

    // At every breakpoint inside the beam (and at x = 0 coming from nothing)
    // the jump in V equals the vertical force applied there, and the jump in
    // M equals minus the couple applied there.
    var worstV = 0.0, worstM = 0.0;
    double? whereV, whereM;
    for (final x in forces.breakpoints) {
      if ((x - length).abs() < 1e-9) continue;
      final here = forces.actionsAt(x);
      final fy = here.fold(0.0, (s, a) => s + (a is PointForce ? a.fy : 0));
      final c = here.fold(0.0, (s, a) => s + (a is PointCouple ? a.moment : 0));
      final dv = forces.shear.rightLimit(x) - forces.shear.leftLimit(x) - fy;
      final dm = forces.moment.rightLimit(x) - forces.moment.leftLimit(x) + c;
      if (dv.abs() > worstV.abs()) {
        worstV = dv;
        whereV = x;
      }
      if (dm.abs() > worstM.abs()) {
        worstM = dm;
        whereM = x;
      }
    }
    items
      ..add(CheckItem(CheckKind.shearJumpsMatchLoads, worstV, fTol, where: whereV))
      ..add(CheckItem(CheckKind.momentJumpsMatchCouples, worstM, mTol,
          where: whereM));

    // Inside each segment: dM/dx = V, and ΔM across it = area under V.
    var worstSlope = 0.0, worstArea = 0.0;
    double? whereSlope, whereArea;
    for (var i = 0; i < forces.moment.pieces.length; i++) {
      final m = forces.moment.pieces[i];
      final v = forces.shear.pieces[i];
      final slope = m.p.derivative() - v.p;
      final slopeError = slope.c.fold(0.0, (s, k) => math.max(s, k.abs()));
      if (slopeError > worstSlope) {
        worstSlope = slopeError;
        whereSlope = (m.x0 + m.x1) / 2;
      }
      final areaError = (m.end - m.start) - v.p.integrate(v.x0, v.x1);
      if (areaError.abs() > worstArea.abs()) {
        worstArea = areaError;
        whereArea = (m.x0 + m.x1) / 2;
      }
    }
    items
      ..add(CheckItem(CheckKind.slopeEqualsShear, worstSlope, fTol,
          where: whereSlope))
      ..add(CheckItem(CheckKind.areaRule, worstArea, mTol, where: whereArea));

    return ValidationReport(items);
  }

  /// Residual of one equation with the solved values substituted.
  static double residualOf(EquilibriumEquation eq, StaticsSolution s) =>
      eq.residual(s.values);
}
