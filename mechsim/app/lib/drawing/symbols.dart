import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Engineering symbols drawn with plain canvas calls, so they stay crisp at
/// any zoom and match the textbook shapes.
abstract final class Symbols {
  /// Font for canvas labels. Null uses the platform's default; tests that
  /// render screenshots set a real font here.
  static String? fontFamily;
  static List<String>? fontFallback;

  static const double supportHeight = 22;
  static const double supportHalfWidth = 14;

  static Paint stroke(Color c, double w) =>
      Paint()
        ..color = c
        ..style = PaintingStyle.stroke
        ..strokeWidth = w
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round;

  static Paint fill(Color c) =>
      Paint()
        ..color = c
        ..style = PaintingStyle.fill;

  /// Ground line with hatching under a support, from [left] to [right].
  static void ground(
    Canvas canvas,
    double left,
    double right,
    double y,
    Color c,
  ) {
    canvas.drawLine(Offset(left, y), Offset(right, y), stroke(c, 1.6));
    final p = stroke(c, 1);
    for (var x = left + 3; x <= right; x += 6) {
      canvas.drawLine(Offset(x, y), Offset(x - 6, y + 6), p);
    }
  }

  /// A pin: a triangle with its apex on the beam and the ground under it.
  static void pin(Canvas canvas, Offset apex, Color c, {double scale = 1}) {
    final h = supportHeight * scale, w = supportHalfWidth * scale;
    final path =
        Path()
          ..moveTo(apex.dx, apex.dy)
          ..lineTo(apex.dx - w, apex.dy + h)
          ..lineTo(apex.dx + w, apex.dy + h)
          ..close();
    canvas.drawPath(path, fill(c.withValues(alpha: 0.12)));
    canvas.drawPath(path, stroke(c, 1.8 * scale));
    canvas.drawCircle(apex, 3.2 * scale, fill(c));
    ground(
      canvas,
      apex.dx - w - 6 * scale,
      apex.dx + w + 6 * scale,
      apex.dy + h,
      c,
    );
  }

  /// A roller: a smaller triangle on two wheels.
  static void roller(Canvas canvas, Offset apex, Color c, {double scale = 1}) {
    final h = (supportHeight - 7) * scale, w = supportHalfWidth * scale;
    final path =
        Path()
          ..moveTo(apex.dx, apex.dy)
          ..lineTo(apex.dx - w, apex.dy + h)
          ..lineTo(apex.dx + w, apex.dy + h)
          ..close();
    canvas.drawPath(path, fill(c.withValues(alpha: 0.12)));
    canvas.drawPath(path, stroke(c, 1.8 * scale));
    canvas.drawCircle(apex, 3.2 * scale, fill(c));
    final r = 3.3 * scale;
    for (final dx in [-w / 2, w / 2]) {
      canvas.drawCircle(
        Offset(apex.dx + dx, apex.dy + h + r),
        r,
        stroke(c, 1.5 * scale),
      );
    }
    ground(
      canvas,
      apex.dx - w - 6 * scale,
      apex.dx + w + 6 * scale,
      apex.dy + h + 2 * r,
      c,
    );
  }

  /// A fixed support: a hatched wall. [facing] is +1 when the beam leaves
  /// the wall to the right (wall on the left end), −1 for the right end.
  static void fixed(
    Canvas canvas,
    Offset at,
    double beamHalf,
    Color c,
    int facing, {
    double scale = 1,
  }) {
    final top = at.dy - 26 * scale, bottom = at.dy + 26 * scale;
    final x = at.dx;
    canvas.drawLine(Offset(x, top), Offset(x, bottom), stroke(c, 2.4 * scale));
    final p = stroke(c, 1.1 * scale);
    for (var y = top + 2; y <= bottom; y += 6 * scale) {
      canvas.drawLine(
        Offset(x, y),
        Offset(x - facing * 7 * scale, y + 7 * scale),
        p,
      );
    }
  }

  /// A straight arrow whose head ends at [head].
  static void arrow(
    Canvas canvas,
    Offset tail,
    Offset head,
    Color c, {
    double width = 2.4,
    double headSize = 10,
  }) {
    final d = head - tail;
    final len = d.distance;
    if (len < 1) return;
    final u = d / len;
    final n = Offset(-u.dy, u.dx);
    final base = head - u * headSize;
    canvas.drawLine(tail, base + u * 1, stroke(c, width));
    final path =
        Path()
          ..moveTo(head.dx, head.dy)
          ..lineTo(
            base.dx + n.dx * headSize * 0.45,
            base.dy + n.dy * headSize * 0.45,
          )
          ..lineTo(
            base.dx - n.dx * headSize * 0.45,
            base.dy - n.dy * headSize * 0.45,
          )
          ..close();
    canvas.drawPath(path, fill(c));
  }

  /// A curved moment arrow around [centre]; counter-clockwise when [ccw].
  static void momentArc(
    Canvas canvas,
    Offset centre,
    double radius,
    bool ccw,
    Color c, {
    double width = 2.4,
  }) {
    // Screen y points down, so a positive sweep turns clockwise on screen.
    const start = math.pi * 0.25;
    final sweep = ccw ? -math.pi * 1.5 : math.pi * 1.5;
    canvas.drawArc(
      Rect.fromCircle(center: centre, radius: radius),
      start,
      sweep,
      false,
      stroke(c, width),
    );
    final end = start + sweep;
    final tip = centre + Offset(math.cos(end), math.sin(end)) * radius;
    final dir =
        ccw
            ? Offset(math.sin(end), -math.cos(end))
            : Offset(-math.sin(end), math.cos(end));
    final n = Offset(-dir.dy, dir.dx);
    const h = 10.0;
    final path =
        Path()
          ..moveTo(tip.dx + dir.dx * h * 0.5, tip.dy + dir.dy * h * 0.5)
          ..lineTo(
            tip.dx - dir.dx * h * 0.5 + n.dx * h * 0.45,
            tip.dy - dir.dy * h * 0.5 + n.dy * h * 0.45,
          )
          ..lineTo(
            tip.dx - dir.dx * h * 0.5 - n.dx * h * 0.45,
            tip.dy - dir.dy * h * 0.5 - n.dy * h * 0.45,
          )
          ..close();
    canvas.drawPath(path, fill(c));
  }

  /// A dashed line.
  static void dashed(
    Canvas canvas,
    Offset a,
    Offset b,
    Paint paint, {
    double dash = 5,
    double gap = 4,
  }) {
    final d = b - a;
    final len = d.distance;
    if (len == 0) return;
    final u = d / len;
    var t = 0.0;
    while (t < len) {
      final e = math.min(t + dash, len);
      canvas.drawLine(a + u * t, a + u * e, paint);
      t = e + gap;
    }
  }

  /// A dimension line between two x positions at height [y], with ticks and
  /// [text] centred above it.
  static void dimension(
    Canvas canvas,
    double x0,
    double x1,
    double y,
    String text,
    Color c, {
    double fontSize = 11,
    bool arrows = false,
  }) {
    final p = stroke(c, 1);
    canvas.drawLine(Offset(x0, y), Offset(x1, y), p);
    if (arrows) {
      final dir = x1 >= x0 ? 1.0 : -1.0;
      for (final (x, s) in [(x0, dir), (x1, -dir)]) {
        final path =
            Path()
              ..moveTo(x, y)
              ..lineTo(x + s * 7, y - 3.5)
              ..lineTo(x + s * 7, y + 3.5)
              ..close();
        canvas.drawPath(path, fill(c));
      }
    }
    for (final x in [x0, x1]) {
      canvas.drawLine(Offset(x, y - 5), Offset(x, y + 5), p);
    }
    label(
      canvas,
      text,
      Offset((x0 + x1) / 2, y - 3),
      c,
      fontSize: fontSize,
      anchor: Alignment.bottomCenter,
    );
  }

  /// Text anchored at [at]; [anchor] says which point of the text box sits
  /// there. Returns the box drawn.
  static Rect label(
    Canvas canvas,
    String text,
    Offset at,
    Color c, {
    double fontSize = 12,
    FontWeight weight = FontWeight.w500,
    Alignment anchor = Alignment.center,
    Color? background,
  }) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          color: c,
          fontSize: fontSize,
          fontWeight: weight,
          height: 1.1,
          fontFamily: fontFamily,
          fontFamilyFallback: fontFallback,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    final dx = at.dx - tp.width * (anchor.x + 1) / 2;
    final dy = at.dy - tp.height * (anchor.y + 1) / 2;
    final rect = Rect.fromLTWH(dx, dy, tp.width, tp.height);
    if (background != null) {
      canvas.drawRRect(
        RRect.fromRectAndRadius(rect.inflate(3), const Radius.circular(4)),
        fill(background),
      );
    }
    tp.paint(canvas, Offset(dx, dy));
    return rect;
  }

  static Size measure(
    String text,
    double fontSize, {
    FontWeight weight = FontWeight.w500,
  }) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          fontSize: fontSize,
          fontWeight: weight,
          height: 1.1,
          fontFamily: fontFamily,
          fontFamilyFallback: fontFallback,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    return tp.size;
  }
}
