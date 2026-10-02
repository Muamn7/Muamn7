/// What a piece of the explanation points at in the drawing. The engine only
/// names targets; the renderer decides how to show them (a glow on an arrow,
/// a dimension line for a moment arm, a cross-hair on a diagram).
library;

import '../diagrams/internal_forces.dart';
import '../diagrams/polynomial.dart';

sealed class Highlight {
  const Highlight();
}

final class ReactionHighlight extends Highlight {
  const ReactionHighlight(this.reactionId);
  final String reactionId;

  @override
  bool operator ==(Object other) =>
      other is ReactionHighlight && other.reactionId == reactionId;
  @override
  int get hashCode => reactionId.hashCode;
}

final class LoadHighlight extends Highlight {
  const LoadHighlight(this.loadId);
  final String loadId;

  @override
  bool operator ==(Object other) =>
      other is LoadHighlight && other.loadId == loadId;
  @override
  int get hashCode => loadId.hashCode;
}

final class SupportHighlight extends Highlight {
  const SupportHighlight(this.supportId);
  final String supportId;

  @override
  bool operator ==(Object other) =>
      other is SupportHighlight && other.supportId == supportId;
  @override
  int get hashCode => supportId.hashCode;
}

/// The point moments are taken about.
final class MomentCentreHighlight extends Highlight {
  const MomentCentreHighlight(this.x);
  final double x;

  @override
  bool operator ==(Object other) =>
      other is MomentCentreHighlight && other.x == x;
  @override
  int get hashCode => x.hashCode;
}

/// A lever arm, drawn as a dimension line from the moment centre to the
/// line of action of a force.
final class ArmHighlight extends Highlight {
  const ArmHighlight(this.fromX, this.toX);
  final double fromX;
  final double toX;

  @override
  bool operator ==(Object other) =>
      other is ArmHighlight && other.fromX == fromX && other.toX == toX;
  @override
  int get hashCode => Object.hash(fromX, toX);
}

/// A cut through the beam for the method of sections.
final class SectionHighlight extends Highlight {
  const SectionHighlight(this.x);
  final double x;

  @override
  bool operator ==(Object other) => other is SectionHighlight && other.x == x;
  @override
  int get hashCode => x.hashCode;
}

/// One value on a diagram. [side] picks V(x⁻) or V(x⁺) at a jump.
final class DiagramPointHighlight extends Highlight {
  const DiagramPointHighlight(this.kind, this.x, [this.side]);
  final DiagramKind kind;
  final double x;
  final Side? side;

  @override
  bool operator ==(Object other) =>
      other is DiagramPointHighlight &&
      other.kind == kind &&
      other.x == x &&
      other.side == side;
  @override
  int get hashCode => Object.hash(kind, x, side);
}

/// A stretch of a diagram, such as one segment of the SFD.
final class DiagramRangeHighlight extends Highlight {
  const DiagramRangeHighlight(this.kind, this.x0, this.x1);
  final DiagramKind kind;
  final double x0;
  final double x1;

  @override
  bool operator ==(Object other) =>
      other is DiagramRangeHighlight &&
      other.kind == kind &&
      other.x0 == x0 &&
      other.x1 == x1;
  @override
  int get hashCode => Object.hash(kind, x0, x1);
}

/// How much of the solution the drawing shows at a given step. The
/// step-by-step player walks through these; the full results view shows
/// everything.
class Reveal {
  const Reveal({
    this.reactions = false,
    this.solved = const {},
    this.shear = false,
    this.moment = false,
    this.axial = false,
  });

  /// Supports are drawn as their reaction arrows (the free body diagram).
  final bool reactions;

  /// Reactions whose values are known by this step.
  final Set<String> solved;
  final bool shear;
  final bool moment;
  final bool axial;

  static const nothing = Reveal();

  Reveal copyWith({
    bool? reactions,
    Set<String>? solved,
    bool? shear,
    bool? moment,
    bool? axial,
  }) =>
      Reveal(
        reactions: reactions ?? this.reactions,
        solved: solved ?? this.solved,
        shear: shear ?? this.shear,
        moment: moment ?? this.moment,
        axial: axial ?? this.axial,
      );
}
