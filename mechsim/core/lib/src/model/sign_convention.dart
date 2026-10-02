/// Which directions count as positive when the equilibrium equations are
/// written out.
///
/// The convention changes how an equation *looks* (which terms carry a minus
/// sign), never what the reactions *are*: a reaction is always reported by
/// its physical direction. The internal-force convention (shear and moment
/// signs on the diagrams) is the standard beam convention and is fixed; see
/// [BeamConvention].
library;

class SignConvention {
  const SignConvention({
    this.upPositive = true,
    this.rightPositive = true,
    this.counterClockwisePositive = true,
  });

  /// ↑ positive (true) or ↓ positive (false) in ΣFy.
  final bool upPositive;

  /// → positive (true) or ← positive (false) in ΣFx.
  final bool rightPositive;

  /// ↺ positive (true) or ↻ positive (false) in ΣM.
  final bool counterClockwisePositive;

  static const standard = SignConvention();

  /// +1 or −1: the factor that turns a physical component (→, ↑, ↺ positive)
  /// into its sign in an equation written in this convention.
  double get xSign => rightPositive ? 1 : -1;
  double get ySign => upPositive ? 1 : -1;
  double get momentSign => counterClockwisePositive ? 1 : -1;

  String get xArrow => rightPositive ? '→' : '←';
  String get yArrow => upPositive ? '↑' : '↓';
  String get momentArrow => counterClockwisePositive ? '↺' : '↻';

  SignConvention copyWith({
    bool? upPositive,
    bool? rightPositive,
    bool? counterClockwisePositive,
  }) =>
      SignConvention(
        upPositive: upPositive ?? this.upPositive,
        rightPositive: rightPositive ?? this.rightPositive,
        counterClockwisePositive:
            counterClockwisePositive ?? this.counterClockwisePositive,
      );

  Map<String, Object?> toJson() => {
        'up': upPositive,
        'right': rightPositive,
        'ccw': counterClockwisePositive,
      };

  factory SignConvention.fromJson(Map<String, Object?> json) => SignConvention(
        upPositive: json['up'] as bool? ?? true,
        rightPositive: json['right'] as bool? ?? true,
        counterClockwisePositive: json['ccw'] as bool? ?? true,
      );

  @override
  bool operator ==(Object other) =>
      other is SignConvention &&
      other.upPositive == upPositive &&
      other.rightPositive == rightPositive &&
      other.counterClockwisePositive == counterClockwisePositive;

  @override
  int get hashCode =>
      Object.hash(upPositive, rightPositive, counterClockwisePositive);
}

/// The internal-force convention used for SFD, BMD and the axial diagram.
///
/// Cut the beam and look at the part to the left of the cut:
/// * shear V is positive when the left part is pushed up by its loads
///   (V = Σ upward forces on the left part);
/// * moment M is positive when it bends the beam into a smile, "sagging"
///   (M = Σ moments of the left part about the cut, clockwise positive);
/// * axial N is positive in tension (the cut face is pulled).
abstract final class BeamConvention {}
