import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../drawing/symbols.dart';
import '../../state/editor_controller.dart';

/// Toolbar icons drawn as the engineering symbols they place.
class ToolIcon extends StatelessWidget {
  const ToolIcon(this.tool, {super.key, this.size = 26, this.color});

  final Tool tool;
  final double size;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = color ?? IconTheme.of(context).color ?? Colors.black;
    final material = switch (tool) {
      Tool.select => Icons.near_me_outlined,
      Tool.delete => Icons.delete_outline,
      _ => null,
    };
    if (material != null) return Icon(material, size: size, color: c);
    return CustomPaint(size: Size.square(size), painter: _ToolPainter(tool, c));
  }
}

class _ToolPainter extends CustomPainter {
  _ToolPainter(this.tool, this.color);

  final Tool tool;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    final s = Symbols.stroke(color, 2);
    final beamY = h * 0.38;
    void beam() => canvas.drawLine(
      Offset(w * 0.08, beamY),
      Offset(w * 0.92, beamY),
      Symbols.stroke(color, 3.2),
    );
    switch (tool) {
      case Tool.beam:
        canvas.drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTRB(w * 0.06, h * 0.42, w * 0.94, h * 0.58),
            const Radius.circular(2),
          ),
          Symbols.fill(color),
        );
      case Tool.pin:
        Symbols.pin(canvas, Offset(w / 2, h * 0.22), color, scale: w / 34);
      case Tool.roller:
        Symbols.roller(canvas, Offset(w / 2, h * 0.2), color, scale: w / 34);
      case Tool.fixed:
        Symbols.fixed(
          canvas,
          Offset(w * 0.3, h / 2),
          2,
          color,
          1,
          scale: w / 60,
        );
        canvas.drawLine(
          Offset(w * 0.3, h / 2),
          Offset(w * 0.95, h / 2),
          Symbols.stroke(color, 3),
        );
      case Tool.pointLoad:
        beam();
        Symbols.arrow(
          canvas,
          Offset(w / 2, h * 0.0),
          Offset(w / 2, beamY - 2),
          color,
          width: 2,
          headSize: 7,
        );
        canvas.drawLine(
          Offset(w * 0.08, beamY),
          Offset(w * 0.92, beamY),
          Symbols.stroke(color, 3),
        );
      case Tool.udl:
        final y = h * 0.62;
        canvas.drawLine(
          Offset(w * 0.08, y),
          Offset(w * 0.92, y),
          Symbols.stroke(color, 3),
        );
        canvas.drawLine(
          Offset(w * 0.12, h * 0.12),
          Offset(w * 0.88, h * 0.12),
          s,
        );
        for (var i = 0; i < 4; i++) {
          final x = w * (0.14 + i * 0.24);
          Symbols.arrow(
            canvas,
            Offset(x, h * 0.12),
            Offset(x, y - 2),
            color,
            width: 1.4,
            headSize: 5,
          );
        }
      case Tool.uvl:
        final y = h * 0.62;
        canvas.drawLine(
          Offset(w * 0.08, y),
          Offset(w * 0.92, y),
          Symbols.stroke(color, 3),
        );
        canvas.drawLine(Offset(w * 0.12, y - 4), Offset(w * 0.88, h * 0.08), s);
        for (var i = 1; i < 4; i++) {
          final x = w * (0.14 + i * 0.24);
          final top = y - 4 - (y - 4 - h * 0.08) * (i * 0.24 + 0.02) / 0.76;
          Symbols.arrow(
            canvas,
            Offset(x, top),
            Offset(x, y - 2),
            color,
            width: 1.4,
            headSize: 5,
          );
        }
      case Tool.moment:
        canvas.drawLine(
          Offset(w * 0.08, h / 2),
          Offset(w * 0.92, h / 2),
          Symbols.stroke(color, 3),
        );
        Symbols.momentArc(
          canvas,
          Offset(w / 2, h / 2),
          w * 0.3,
          true,
          color,
          width: 1.8,
        );
      case Tool.dimension:
        Symbols.dimension(
          canvas,
          w * 0.1,
          w * 0.9,
          h * 0.55,
          '',
          color,
          arrows: true,
        );
        canvas.drawLine(Offset(w * 0.1, h * 0.25), Offset(w * 0.1, h * 0.8), s);
        canvas.drawLine(Offset(w * 0.9, h * 0.25), Offset(w * 0.9, h * 0.8), s);
      case Tool.select || Tool.delete:
        break;
    }
  }

  @override
  bool shouldRepaint(covariant _ToolPainter old) =>
      old.tool != tool || old.color != color;
}

/// A small drawing of a load direction for the direction buttons.
class DirectionGlyph extends StatelessWidget {
  const DirectionGlyph(this.angleDeg, {super.key, this.size = 20});

  final double angleDeg;
  final double size;

  @override
  Widget build(BuildContext context) {
    final c = IconTheme.of(context).color ?? Colors.black;
    return CustomPaint(
      size: Size.square(size),
      painter: _DirPainter(angleDeg, c),
    );
  }
}

class _DirPainter extends CustomPainter {
  _DirPainter(this.angle, this.color);

  final double angle;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final r = size.width * 0.42;
    final c = size.center(Offset.zero);
    final d = Offset(
      math.cos(angle * math.pi / 180),
      -math.sin(angle * math.pi / 180),
    );
    Symbols.arrow(canvas, c - d * r, c + d * r, color, width: 2, headSize: 7);
  }

  @override
  bool shouldRepaint(covariant _DirPainter old) =>
      old.angle != angle || old.color != color;
}
