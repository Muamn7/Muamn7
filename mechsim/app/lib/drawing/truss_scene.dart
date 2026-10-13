import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import 'beam_scene.dart' show paintGrid;
import 'palette.dart';
import 'symbols.dart';
import 'viewport.dart';

/// Fits the whole truss into [size] with [margin] pixels around it.
SheetView fitTruss(TrussProblem p, Size size, {double margin = 56}) {
  if (p.nodes.isEmpty) {
    return SheetView(scale: 40, origin: Offset(margin, size.height * 0.7));
  }
  var minX = p.nodes.first.x, maxX = minX;
  var minY = p.nodes.first.y, maxY = minY;
  for (final n in p.nodes) {
    minX = math.min(minX, n.x);
    maxX = math.max(maxX, n.x);
    minY = math.min(minY, n.y);
    maxY = math.max(maxY, n.y);
  }
  final w = math.max(1.0, maxX - minX), h = math.max(1.0, maxY - minY);
  // Room below for supports and reactions, above for loads.
  final usableW = math.max(40.0, size.width - 2 * margin);
  final usableH = math.max(40.0, size.height - 2 * margin - 40);
  final scale =
      math
          .min(usableW / w, usableH / h)
          .clamp(SheetView.minScale, 400.0)
          .toDouble();
  final cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  return SheetView(
    scale: scale,
    origin: Offset(
      size.width / 2 - cx * scale,
      size.height / 2 + cy * scale - 4,
    ),
  );
}

/// Draws a truss: members (by their force, once solved: tension blue,
/// compression red, thicker for more force), joints with their letters,
/// supports, loads, reactions, and for the method of sections the cut and
/// the part kept.
class TrussScene {
  TrussScene({
    required this.problem,
    required this.view,
    required this.colors,
    required this.units,
    this.solution,
    this.highlights = const [],
    this.selectedId,
    this.pending,
    this.ghost,
    this.cut = const {},
    this.side,
    this.points = const [],
    this.pulse = 0,
  }) : labels = TrussLabels.of(problem);

  final TrussProblem problem;
  final SheetView view;
  final MechColors colors;
  final UnitSystem units;
  final TrussLabels labels;

  /// Forces and reactions to show; none in the editor.
  final TrussSolution? solution;
  final List<Highlight> highlights;
  final String? selectedId;

  /// A joint a member is being drawn from.
  final String? pending;

  /// A member being dragged out: from a joint to the finger.
  final (Offset, Offset)? ghost;

  /// Members cut by a section, and the joints of the part kept.
  final Set<String> cut;
  final Set<String>? side;

  /// Named points off the truss that moments are taken about.
  final List<(String, double, double)> points;
  final double pulse;

  Offset at(String nodeId) {
    final n = problem.node(nodeId)!;
    return view.toScreen(n.x, n.y);
  }

  Color get _glow => colors.highlight.withValues(alpha: 0.25 + 0.3 * pulse);

  bool _lit<T extends Highlight>(bool Function(T) test) =>
      highlights.whereType<T>().any(test);

  String f(double si) =>
      Num.compact(units.toDisplay(si, Dimension.force), maxDecimals: 2);

  /// Three significant figures, short enough to sit on a member: 21.2,
  /// 7.07, 15.
  String short(double si) {
    final v = units.toDisplay(si, Dimension.force);
    final a = v.abs();
    return Num.compact(v, maxDecimals: a >= 100 ? 0 : (a >= 10 ? 1 : 2));
  }

  /// Whether something at [nodeId] is on the part a section throws away.
  bool _away(String nodeId) => side != null && !side!.contains(nodeId);

  void paint(Canvas canvas, Size size, {bool grid = true}) {
    if (grid) paintGrid(canvas, size, view, colors);
    final forces = solution?.isSolved == true ? solution : null;
    final maxForce =
        forces == null
            ? 0.0
            : forces.forces.values.fold(0.0, (m, v) => math.max(m, v.abs()));

    bool faded(TrussMember m) =>
        side != null &&
        !cut.contains(m.id) &&
        !(side!.contains(m.a) && side!.contains(m.b));

    // Members.
    for (final m in problem.members) {
      final a = at(m.a), b = at(m.b);
      final lit =
          _lit<MemberHighlight>((h) => h.memberId == m.id) ||
          selectedId == m.id;
      if (lit) canvas.drawLine(a, b, Symbols.stroke(_glow, 14));
      var color = colors.beam;
      var width = 4.5;
      final v = forces?.forces[m.id];
      if (v != null) {
        if (v.abs() < 1e-9) {
          color = colors.inkSoft;
          width = 2.5;
        } else {
          color = v > 0 ? colors.shear : colors.load;
          width = 3 + 5 * (maxForce == 0 ? 0 : v.abs() / maxForce);
        }
      }
      if (faded(m)) color = color.withValues(alpha: 0.22);
      if (cut.contains(m.id)) {
        Symbols.dashed(
          canvas,
          a,
          b,
          Symbols.stroke(colors.highlight, 3),
          dash: 8,
          gap: 5,
        );
      } else {
        canvas.drawLine(
          a,
          b,
          Symbols.stroke(color, width)..strokeCap = StrokeCap.round,
        );
      }
      if (selectedId == m.id) {
        canvas.drawLine(a, b, Symbols.stroke(colors.selection, 1.5));
      }
      if (forces != null && v != null && !faded(m) && !cut.contains(m.id)) {
        final mid = (a + b) / 2;
        final text =
            v.abs() < 1e-9 ? '0' : '${short(v.abs())} ${v > 0 ? 'T' : 'C'}';
        Symbols.label(
          canvas,
          text,
          mid,
          v.abs() < 1e-9
              ? colors.inkSoft
              : (v > 0 ? colors.shear : colors.load),
          fontSize: 11,
          weight: FontWeight.w800,
          background: colors.paper.withValues(alpha: 0.88),
        );
      }
    }

    // A cut: each cut member's force, assumed tension, pulling the part
    // kept towards the other one.
    if (side != null) {
      for (final id in cut) {
        final m = problem.member(id);
        if (m == null) continue;
        final keep = side!.contains(m.a) ? m.a : m.b;
        final from = at(keep), to = at(m.other(keep));
        final mid = (from + to) / 2;
        final dir = (to - from) / (to - from).distance;
        Symbols.arrow(
          canvas,
          mid - dir * 26,
          mid + dir * 4,
          colors.highlight,
          width: 2.6,
          headSize: 10,
        );
        Symbols.label(
          canvas,
          labels.member(m),
          mid - dir * 26 + Offset(-dir.dy, dir.dx) * 12,
          colors.highlight,
          fontSize: 11,
          weight: FontWeight.w800,
          background: colors.paper.withValues(alpha: 0.88),
        );
      }
    }

    if (ghost != null) {
      Symbols.dashed(
        canvas,
        ghost!.$1,
        ghost!.$2,
        Symbols.stroke(colors.selection, 3),
        dash: 7,
        gap: 5,
      );
    }

    // Supports, under their joints.
    for (final s in problem.supports) {
      if (problem.node(s.node) == null) continue;
      final p = at(s.node);
      final lit =
          _lit<SupportHighlight>((h) => h.supportId == s.id) ||
          selectedId == s.id;
      final c = lit ? colors.highlight : colors.support;
      if (s.type == TrussSupportType.pin) {
        Symbols.pin(canvas, p, c, scale: 0.85);
      } else {
        Symbols.roller(canvas, p, c, scale: 0.85);
      }
    }

    // Reactions, once solved.
    if (forces != null) {
      for (final r in forces.reactions) {
        final v = forces.reactionValues[r.id] ?? 0;
        if (v.abs() < 1e-9) continue;
        final p = at(r.node);
        final lit = _lit<ReactionHighlight>((h) => h.reactionId == r.id);
        var c = lit ? colors.highlight : colors.reaction;
        if (_away(r.node)) c = c.withValues(alpha: 0.22);
        final (Offset tail, Offset head, Offset label, Alignment anchor) =
            r.axis == TrussAxis.y
                ? (v > 0
                    ? (
                      p + const Offset(0, 74),
                      p + const Offset(0, 36),
                      p + const Offset(0, 78),
                      Alignment.topCenter,
                    )
                    : (
                      p + const Offset(0, 36),
                      p + const Offset(0, 74),
                      p + const Offset(0, 78),
                      Alignment.topCenter,
                    ))
                : (v > 0
                    ? (
                      p + const Offset(-62, 0),
                      p + const Offset(-24, 0),
                      p + const Offset(-64, -4),
                      Alignment.bottomRight,
                    )
                    : (
                      p + const Offset(-24, 0),
                      p + const Offset(-62, 0),
                      p + const Offset(-64, -4),
                      Alignment.bottomRight,
                    ));
        if (lit) canvas.drawLine(tail, head, Symbols.stroke(_glow, 10));
        Symbols.arrow(canvas, tail, head, c, width: 2.6, headSize: 10);
        Symbols.label(
          canvas,
          '${r.symbol} = ${f(v.abs())}',
          label,
          c,
          fontSize: 11,
          weight: FontWeight.w800,
          anchor: anchor,
          background: colors.paper.withValues(alpha: 0.85),
        );
      }
    }

    // Loads: arrows ending at their joints.
    for (final l in problem.loads) {
      if (problem.node(l.node) == null) continue;
      final p = at(l.node);
      final d = Offset(
        math.cos(l.angleDeg * math.pi / 180),
        -math.sin(l.angleDeg * math.pi / 180),
      );
      final tail = p - d * 54, head = p - d * 7;
      final lit =
          _lit<LoadHighlight>((h) => h.loadId == l.id) || selectedId == l.id;
      var c = lit ? colors.highlight : colors.load;
      if (_away(l.node)) c = c.withValues(alpha: 0.22);
      if (lit) canvas.drawLine(tail, head, Symbols.stroke(_glow, 10));
      Symbols.arrow(canvas, tail, head, c, width: 2.6, headSize: 11);
      Symbols.label(
        canvas,
        '${f(l.magnitude)} ${units.force.symbol}',
        tail - d * 4,
        c,
        fontSize: 11.5,
        weight: FontWeight.w800,
        // On the far side of the tail, away from the joint.
        anchor: Alignment(d.dx, d.dy),
        background: colors.paper.withValues(alpha: 0.85),
      );
    }

    // Joints and their letters.
    for (final n in problem.nodes) {
      final p = view.toScreen(n.x, n.y);
      final lit =
          _lit<JointHighlight>((h) => h.nodeId == n.id) ||
          selectedId == n.id ||
          pending == n.id;
      final keep = side == null || side!.contains(n.id);
      if (lit) canvas.drawCircle(p, 13, Symbols.fill(_glow));
      canvas.drawCircle(p, 5.5, Symbols.fill(colors.paper));
      canvas.drawCircle(
        p,
        5.5,
        Symbols.stroke(
          keep ? colors.ink : colors.ink.withValues(alpha: 0.3),
          2,
        ),
      );
      if (selectedId == n.id || pending == n.id) {
        canvas.drawCircle(p, 10, Symbols.stroke(colors.selection, 1.6));
      }
      Symbols.label(
        canvas,
        labels.node(n.id),
        p + const Offset(-9, -9),
        keep ? colors.ink : colors.ink.withValues(alpha: 0.3),
        fontSize: 13,
        weight: FontWeight.w900,
        anchor: Alignment.bottomRight,
        background: colors.paper.withValues(alpha: 0.7),
      );
    }

    // Points moments are taken about.
    for (final h in highlights.whereType<PlanePointHighlight>()) {
      final p = view.toScreen(h.x, h.y);
      canvas.drawCircle(p, 12, Symbols.fill(_glow));
      canvas.drawCircle(p, 8, Symbols.stroke(colors.highlight, 2.2));
      canvas.drawCircle(p, 2.5, Symbols.fill(colors.highlight));
      for (final (name, x, y) in points) {
        if ((x - h.x).abs() < 1e-9 && (y - h.y).abs() < 1e-9) {
          Symbols.label(
            canvas,
            name,
            p + const Offset(10, -10),
            colors.highlight,
            fontSize: 13,
            weight: FontWeight.w900,
            anchor: Alignment.bottomLeft,
            background: colors.paper.withValues(alpha: 0.85),
          );
        }
      }
    }
  }

  /// What is under the finger: a joint first, then a load, a support, a
  /// member.
  String? hitTest(Offset p) {
    for (final n in problem.nodes.reversed) {
      if ((view.toScreen(n.x, n.y) - p).distance < 18) return n.id;
    }
    for (final l in problem.loads.reversed) {
      if (problem.node(l.node) == null) continue;
      final j = at(l.node);
      final d = Offset(
        math.cos(l.angleDeg * math.pi / 180),
        -math.sin(l.angleDeg * math.pi / 180),
      );
      if (_distanceToSegment(p, j - d * 54, j) < 12) return l.id;
    }
    for (final s in problem.supports.reversed) {
      if (problem.node(s.node) == null) continue;
      final j = at(s.node);
      if (Rect.fromLTRB(
        j.dx - 22,
        j.dy + 4,
        j.dx + 22,
        j.dy + 34,
      ).contains(p)) {
        return s.id;
      }
    }
    String? best;
    var bestD = 14.0;
    for (final m in problem.members) {
      final d = _distanceToSegment(p, at(m.a), at(m.b));
      if (d < bestD) {
        bestD = d;
        best = m.id;
      }
    }
    return best;
  }

  static double _distanceToSegment(Offset p, Offset a, Offset b) {
    final ab = b - a;
    final len2 = ab.dx * ab.dx + ab.dy * ab.dy;
    if (len2 == 0) return (p - a).distance;
    final t = (((p - a).dx * ab.dx + (p - a).dy * ab.dy) / len2).clamp(
      0.0,
      1.0,
    );
    return (p - (a + ab * t)).distance;
  }
}

class TrussPainter extends CustomPainter {
  TrussPainter(this.scene, {this.grid = true});

  final TrussScene scene;
  final bool grid;

  @override
  void paint(Canvas canvas, Size size) => scene.paint(canvas, size, grid: grid);

  @override
  bool shouldRepaint(covariant TrussPainter old) => true;
}
