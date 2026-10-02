import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import 'palette.dart';
import 'symbols.dart';
import 'viewport.dart';

/// Draws one diagram (SFD, BMD or the axial force diagram) inside a band of
/// the screen, sharing its x-axis with the beam above it.
class DiagramBand {
  DiagramBand({
    required this.kind,
    required this.function,
    required this.geometry,
    required this.rect,
    required this.viewport,
    required this.colors,
    required this.color,
    required this.title,
    required this.toDisplay,
    this.progress = 1,
    this.highlights = const [],
    this.pulse = 0,
  });

  final DiagramKind kind;
  final PiecewiseFunction function;
  final DiagramGeometry geometry;
  final Rect rect;
  final SheetView viewport;
  final MechColors colors;
  final Color color;
  final String title;
  final double Function(double si) toDisplay;

  /// 0..1: how much of the diagram, from the left, is drawn (animation).
  final double progress;
  final List<Highlight> highlights;
  final double pulse;

  static const double _top = 24;
  static const double _bottom = 22;

  late final double _maxV = math.max(0, geometry.maxValue);
  late final double _minV = math.min(0, geometry.minValue);

  /// Screen y of the zero line.
  late final double axisY = () {
    final h = rect.height - _top - _bottom;
    final span = _maxV - _minV;
    if (span <= 0) return rect.top + _top + h / 2;
    return rect.top + _top + h * (_maxV / span);
  }();

  late final double _scale = () {
    final h = rect.height - _top - _bottom;
    final span = _maxV - _minV;
    return span <= 0 ? 0.0 : h / span;
  }();

  double vy(double value) => axisY - value * _scale;

  Offset point(double x, double value) => Offset(viewport.sx(x), vy(value));

  String fmt(double si) {
    final v = toDisplay(si);
    final text = Num.compact(v, maxDecimals: 2);
    return v > 0 && kind != DiagramKind.moment ? '+$text' : text;
  }

  void paint(Canvas canvas) {
    final x0 = viewport.sx(0), x1 = viewport.sx(geometry.length);
    Symbols.label(
      canvas,
      title,
      Offset(rect.left + 6, rect.top + 4),
      color,
      fontSize: 11.5,
      weight: FontWeight.w800,
      anchor: Alignment.topLeft,
    );
    canvas.drawLine(
      Offset(x0, axisY),
      Offset(x1, axisY),
      Symbols.stroke(colors.inkSoft, 1.2),
    );
    if (geometry.outline.isEmpty) return;

    canvas.save();
    canvas.clipRect(
      Rect.fromLTRB(
        rect.left,
        rect.top,
        x0 + (x1 - x0) * progress + 1,
        rect.bottom,
      ),
    );
    final path = Path();
    for (var i = 0; i < geometry.outline.length; i++) {
      final p = point(geometry.outline[i].x, geometry.outline[i].value);
      i == 0 ? path.moveTo(p.dx, p.dy) : path.lineTo(p.dx, p.dy);
    }
    canvas.drawPath(path, Symbols.fill(color.withValues(alpha: 0.16)));
    canvas.drawPath(path, Symbols.stroke(color, 2.2));
    _paintHighlights(canvas, path);
    canvas.restore();

    if (progress >= 0.999) _paintKeyValues(canvas);
    _paintPoints(canvas);
  }

  void _paintHighlights(Canvas canvas, Path path) {
    for (final h in highlights.whereType<DiagramRangeHighlight>()) {
      if (h.kind != kind) continue;
      canvas.save();
      canvas.clipRect(
        Rect.fromLTRB(
          viewport.sx(h.x0),
          rect.top,
          viewport.sx(h.x1),
          rect.bottom,
        ),
      );
      canvas.drawPath(
        path,
        Symbols.fill(colors.highlight.withValues(alpha: 0.22 + 0.18 * pulse)),
      );
      canvas.drawPath(path, Symbols.stroke(colors.highlight, 3.4));
      canvas.restore();
    }
  }

  void _paintPoints(Canvas canvas) {
    for (final h in highlights.whereType<DiagramPointHighlight>()) {
      if (h.kind != kind) continue;
      final sides = h.side == null ? [Side.left, Side.right] : [h.side!];
      final seen = <double>[];
      for (final side in sides) {
        final v = function.valueAt(h.x, side: side);
        if (seen.any((s) => (s - v).abs() < 1e-9)) continue;
        seen.add(v);
        final p = point(h.x, v);
        canvas.drawCircle(
          p,
          10 + 3 * pulse,
          Symbols.fill(colors.highlight.withValues(alpha: 0.3)),
        );
        canvas.drawCircle(p, 5.5, Symbols.fill(colors.highlight));
        canvas.drawCircle(p, 5.5, Symbols.stroke(colors.paper, 1.5));
        Symbols.label(
          canvas,
          fmt(v),
          p + Offset(0, v >= 0 ? -10 : 10),
          colors.highlight,
          fontSize: 12.5,
          weight: FontWeight.w800,
          anchor: v >= 0 ? Alignment.bottomCenter : Alignment.topCenter,
          background: colors.paper.withValues(alpha: 0.92),
        );
      }
    }
  }

  void _paintKeyValues(Canvas canvas) {
    final placed = <Rect>[];
    for (final k in geometry.keyValues) {
      final p = point(k.x, k.value);
      final text = fmt(k.value);
      final size = Symbols.measure(text, 11.5, weight: FontWeight.w700);
      final above = k.value >= 0;
      var anchor = above ? Alignment.bottomCenter : Alignment.topCenter;
      var at = p + Offset(0, above ? -4 : 4);
      if (k.side == Side.left) {
        anchor = above ? Alignment.bottomRight : Alignment.topRight;
        at = at + const Offset(-3, 0);
      } else if (k.side == Side.right) {
        anchor = above ? Alignment.bottomLeft : Alignment.topLeft;
        at = at + const Offset(3, 0);
      }
      final box = Rect.fromLTWH(
        at.dx - size.width * (anchor.x + 1) / 2,
        at.dy - size.height * (anchor.y + 1) / 2,
        size.width,
        size.height,
      );
      if (placed.any((r) => r.inflate(2).overlaps(box))) continue;
      placed.add(box);
      Symbols.label(
        canvas,
        text,
        at,
        colors.ink,
        fontSize: 11.5,
        weight: FontWeight.w700,
        anchor: anchor,
      );
    }
  }

  /// Dots where the cross-hair crosses this diagram.
  void paintCursor(Canvas canvas, double x) {
    final values = <double>{function.leftLimit(x), function.rightLimit(x)};
    if (x > 1e-9 && x < geometry.length - 1e-9) values.add(function.valueAt(x));
    for (final v in values) {
      final p = point(x, v);
      canvas.drawCircle(p, 4.5, Symbols.fill(color));
      canvas.drawCircle(p, 4.5, Symbols.stroke(colors.paper, 1.4));
    }
  }

  /// A band that has not been revealed yet in the step player.
  static void paintPlaceholder(
    Canvas canvas,
    Rect rect,
    String title,
    String text,
    Color color,
    MechColors colors,
    SheetView viewport,
    double length,
  ) {
    Symbols.label(
      canvas,
      title,
      Offset(rect.left + 6, rect.top + 4),
      color.withValues(alpha: 0.5),
      fontSize: 11.5,
      weight: FontWeight.w800,
      anchor: Alignment.topLeft,
    );
    final y = rect.center.dy;
    Symbols.dashed(
      canvas,
      Offset(viewport.sx(0), y),
      Offset(viewport.sx(length), y),
      Symbols.stroke(colors.inkSoft.withValues(alpha: 0.4), 1.2),
    );
    Symbols.label(
      canvas,
      text,
      Offset(rect.center.dx, y - 6),
      colors.inkSoft.withValues(alpha: 0.7),
      fontSize: 11,
      anchor: Alignment.bottomCenter,
    );
  }
}
