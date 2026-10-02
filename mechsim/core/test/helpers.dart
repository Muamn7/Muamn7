import 'package:mechsim_core/mechsim_core.dart';
import 'package:test/test.dart';

const kN = 1000.0;

BeamProblem beam(double length,
    {List<(SupportType, double)> supports = const [],
    List<(double kNValue, double x, double angle)> loads = const []}) {
  var p = BeamProblem(length: length);
  for (final (type, x) in supports) {
    p = p.withSupport(Support(id: p.nextId('s'), type: type, x: x));
  }
  for (final (value, x, angle) in loads) {
    p = p.withLoad(PointLoad(
        id: p.nextId('p'), x: x, magnitude: value * kN, angleDeg: angle));
  }
  return p;
}

/// A downward load in kN at x.
(double, double, double) down(double value, double x) => (value, x, -90);

double reaction(StaticsSolution s, String symbol) =>
    s.valueOf(s.reactionBySymbol(symbol)!.id);

Matcher closeToKn(double kNValue) => closeTo(kNValue * kN, 1e-6);
Matcher closeToKnm(double kNmValue) => closeTo(kNmValue * kN, 1e-6);

/// Moment at x computed from the part of the beam to the RIGHT of the cut —
/// a route the analyzer never takes (it sums the left part).
double momentFromRight(StaticsSolution s, double x) {
  var m = 0.0;
  for (final a in s.allActions) {
    if (a.x <= x + 1e-12) continue;
    switch (a) {
      case PointForce(:final fy):
        m += (a.x - x) * fy;
      case PointCouple(moment: final c):
        m += c;
    }
  }
  return m;
}

double shearFromRight(StaticsSolution s, double x) {
  var v = 0.0;
  for (final a in s.allActions) {
    if (a.x <= x + 1e-12) continue;
    if (a is PointForce) v -= a.fy;
  }
  return v;
}
