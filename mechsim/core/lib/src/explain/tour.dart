/// The guided tour of the method of sections: a cut walks along the beam
/// from the left end to the right, and at every x the student sees V(x) and
/// M(x) for the segment the cut is in, while the SFD and BMD are traced up to
/// the cut. It stops wherever something happens: a support, a load, the ends
/// of a distributed load, and where V = 0 (the extreme moment).
///
/// Nothing here is written anew: every line comes from the solution's own
/// steps (the method of sections, the SFD from the loads, the BMD from the
/// SFD's areas, the maximum moment), picked by what each line points at.
library;

import 'dart:math' as math;

import '../diagrams/internal_forces.dart';
import 'highlight.dart';
import 'solution.dart';

enum TourStopKind {
  /// The left end, where the walk starts.
  start,

  /// A support, a load, or an end of a distributed load.
  point,

  /// Inside a segment, where V crosses zero and M is extreme.
  zeroShear,

  /// The right end, where V and M must close.
  end,
}

/// A point where the walk pauses.
class TourStop {
  const TourStop(this.x, this.kind, this.lines);

  final double x;
  final TourStopKind kind;

  /// What happens here: the jump in V, M from the area of the SFD, the
  /// maximum moment.
  final List<MathLine> lines;
}

/// A stretch between two breakpoints, where V and M are each one
/// polynomial.
class TourSegment {
  const TourSegment(
    this.x0,
    this.x1, {
    required this.shear,
    required this.shearRule,
    required this.moment,
    required this.momentRule,
  });

  final double x0;
  final double x1;

  /// V(x) by the method of sections.
  final List<MathLine> shear;

  /// The same from the loads: "no load ⇒ V constant", "distributed load ⇒
  /// V: −2.9 → −17.9".
  final List<MathLine> shearRule;

  /// M(x) by the method of sections.
  final List<MathLine> moment;

  /// M at the far end from the area of the SFD (dM/dx = V).
  final List<MathLine> momentRule;
}

class DiagramTour {
  DiagramTour._(this.solution, this.forces, this.stops, this.segments);

  final Solution solution;
  final InternalForces forces;
  final List<TourStop> stops;
  final List<TourSegment> segments;

  double get length => solution.problem.length;

  /// The tour of a solved problem; null when it could not be solved.
  static DiagramTour? of(Solution solution) {
    final forces = solution.forces;
    if (forces == null || !solution.statics.isSolved) return null;
    final length = solution.problem.length;
    final tol = 1e-9 * math.max(1.0, length);
    bool same(double a, double b) => (a - b).abs() <= tol;

    final byKind = {for (final s in solution.steps) s.kind: s.lines};
    List<MathLine> lines(StepKind kind) => byKind[kind] ?? const [];
    Iterable<Highlight> all(MathLine l) =>
        [...l.highlights, for (final t in l.tokens) ...t.highlights];
    bool pointAt(MathLine l, double x) => all(l)
        .any((h) => h is DiagramPointHighlight && same(h.x, x));
    bool hasPoint(MathLine l) => all(l).any((h) => h is DiagramPointHighlight);
    bool over(MathLine l, double mid, [DiagramKind? kind]) => all(l).any((h) =>
        h is DiagramRangeHighlight &&
        (kind == null || h.kind == kind) &&
        h.x0 <= mid &&
        mid <= h.x1);

    final breaks = <double>[];
    for (final b in [0.0, ...forces.breakpoints, length]) {
      if (b < -tol || b > length + tol) continue;
      if (breaks.every((x) => !same(x, b))) breaks.add(b);
    }
    breaks.sort();

    final zeros = <double>[
      for (final piece in forces.shear.pieces)
        for (final r in piece.p.rootsIn(piece.x0, piece.x1))
          if (!same(r, piece.x0) && !same(r, piece.x1)) r,
    ];

    final xs = [...breaks];
    for (final z in zeros) {
      if (xs.every((x) => !same(x, z))) xs.add(z);
    }
    xs.sort();

    final stops = [
      for (final x in xs)
        TourStop(
          x,
          same(x, 0)
              ? TourStopKind.start
              : same(x, length)
                  ? TourStopKind.end
                  : zeros.any((z) => same(z, x))
                      ? TourStopKind.zeroShear
                      : TourStopKind.point,
          [
            for (final kind in [
              StepKind.shearDiagram,
              StepKind.momentDiagram,
              StepKind.maxMoment,
            ])
              for (final l in lines(kind))
                if (pointAt(l, x)) l,
          ],
        ),
    ];

    final segments = [
      for (var i = 0; i < breaks.length - 1; i++)
        if (!same(breaks[i], breaks[i + 1]))
          () {
            final a = breaks[i], b = breaks[i + 1], mid = (a + b) / 2;
            return TourSegment(
              a,
              b,
              shear: [
                for (final l in lines(StepKind.shear))
                  if (over(l, mid, DiagramKind.shear)) l,
              ],
              shearRule: [
                for (final l in lines(StepKind.shearDiagram))
                  if (over(l, mid) && !hasPoint(l)) l,
              ],
              moment: [
                for (final l in lines(StepKind.moment))
                  if (over(l, mid, DiagramKind.moment)) l,
              ],
              momentRule: [
                for (final l in lines(StepKind.momentDiagram))
                  if (over(l, mid)) l,
              ],
            );
          }(),
    ];
    return DiagramTour._(solution, forces, stops, segments);
  }

  /// The segment the cut at [x] is in; at a breakpoint, the one starting
  /// there (the one ending there at the right end).
  TourSegment segmentAt(double x) {
    for (final s in segments) {
      if (x < s.x1 - 1e-9 * math.max(1.0, length)) return s;
    }
    return segments.last;
  }

  /// The stop at [x], if the cut is on one.
  TourStop? stopAt(double x) {
    final tol = 1e-6 * math.max(1.0, length);
    for (final s in stops) {
      if ((s.x - x).abs() <= tol) return s;
    }
    return null;
  }

  /// V and M just right of the cut (just left of it at the right end).
  double shearAt(double x) => x >= length - 1e-12
      ? forces.shear.leftLimit(x)
      : forces.shear.rightLimit(x);
  double momentAt(double x) => x >= length - 1e-12
      ? forces.moment.leftLimit(x)
      : forces.moment.rightLimit(x);
}
