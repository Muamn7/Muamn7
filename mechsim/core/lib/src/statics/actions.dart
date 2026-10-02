/// Physics Engine: the forces and couples that act on the beam once every
/// load and every reaction is known. Both the diagrams and the validation work
/// on this flat list, so neither needs to know where an action came from.
library;

/// Something applied to the beam at a single point.
sealed class Action {
  const Action(this.sourceId, this.x);

  /// The load or reaction that produced this action.
  final String sourceId;
  final double x;
}

/// A force with components along +x (→) and +y (↑), in newtons.
final class PointForce extends Action {
  const PointForce(super.sourceId, super.x, {this.fx = 0, this.fy = 0});

  final double fx;
  final double fy;

  /// Moment about the point (px, 0), counter-clockwise positive. Every force
  /// acts on the beam axis (y = 0), so a horizontal component has no arm.
  double momentAbout(double px) => (x - px) * fy;
}

/// A concentrated couple in N·m, counter-clockwise positive.
final class PointCouple extends Action {
  const PointCouple(super.sourceId, super.x, this.moment);

  final double moment;
}

/// A load spread from [x] to [x1] whose intensity (N/m, up positive) varies
/// linearly from [q0] to [q1].
final class DistributedForce extends Action {
  const DistributedForce(super.sourceId, super.x, this.x1, this.q0, this.q1);

  final double x1;
  final double q0;
  final double q1;

  double get span => x1 - x;

  /// The resultant vertical force (up positive): the area under q.
  double get fy => (q0 + q1) / 2 * span;

  /// Where the resultant acts.
  double get centroid {
    final sum = q0 + q1;
    if (sum == 0 || span == 0) return x + span / 2;
    return x + span * (q0 + 2 * q1) / (3 * sum);
  }

  /// Intensity at a point inside the load.
  double intensityAt(double s) =>
      span == 0 ? q0 : q0 + (q1 - q0) * (s - x) / span;

  /// Moment about (px, 0), counter-clockwise positive. Splitting the load
  /// into a uniform and a triangular part keeps this exact even when the
  /// intensities have opposite signs and the resultant is zero.
  double momentAbout(double px) {
    final uniform = q0 * span * (x + span / 2 - px);
    final triangle = (q1 - q0) * span / 2 * (x + 2 * span / 3 - px);
    return uniform + triangle;
  }
}
