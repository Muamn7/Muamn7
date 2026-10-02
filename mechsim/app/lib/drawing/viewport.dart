import 'dart:math' as math;
import 'dart:ui';

/// Maps world coordinates (metres, y up) to the screen (pixels, y down).
/// Pinch-zoom and pan only ever change this; the problem itself never moves.
class SheetView {
  const SheetView({required this.scale, required this.origin});

  /// Pixels per metre.
  final double scale;

  /// Where the world point (0, 0) — the left end of the beam — sits on
  /// screen.
  final Offset origin;

  static const double minScale = 4;
  static const double maxScale = 4000;

  Offset toScreen(double x, [double y = 0]) =>
      Offset(origin.dx + x * scale, origin.dy - y * scale);

  double sx(double x) => origin.dx + x * scale;

  double worldX(double screenX) => (screenX - origin.dx) / scale;

  SheetView pan(Offset delta) =>
      SheetView(scale: scale, origin: origin + delta);

  /// Zooms by [factor] keeping the world point under [focal] fixed.
  SheetView zoom(double factor, Offset focal) {
    final next = (scale * factor).clamp(minScale, maxScale);
    final k = next / scale;
    return SheetView(scale: next, origin: focal - (focal - origin) * k);
  }

  /// Fits a beam of [length] metres across [size], leaving [margin] pixels
  /// on each side, with the beam at [yFraction] of the height.
  static SheetView fit(
    double length,
    Size size, {
    double margin = 48,
    double yFraction = 0.42,
  }) {
    final usable = math.max(40.0, size.width - 2 * margin);
    final scale = (length > 0 ? usable / length : 60.0).clamp(
      minScale,
      maxScale,
    );
    final beamWidth = length * scale;
    return SheetView(
      scale: scale,
      origin: Offset((size.width - beamWidth) / 2, size.height * yFraction),
    );
  }

  @override
  bool operator ==(Object other) =>
      other is SheetView && other.scale == scale && other.origin == origin;

  @override
  int get hashCode => Object.hash(scale, origin);
}
