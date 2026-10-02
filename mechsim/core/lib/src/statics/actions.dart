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
