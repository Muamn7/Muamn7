import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import 'palette.dart';
import 'symbols.dart';
import 'viewport.dart';

/// Sizes of the drawing in pixels. The editor uses roomy ones; the linked
/// diagrams and thumbnails use compact ones.
class SceneMetrics {
  const SceneMetrics({
    this.beamHalf = 5,
    this.loadLength = 56,
    this.reactionLength = 46,
    this.labelSize = 12,
    this.letterOffset = 46,
    this.dimensionOffset = 68,
    this.symbolScale = 1,
  });

  final double beamHalf;
  final double loadLength;
  final double reactionLength;
  final double labelSize;
  final double letterOffset;
  final double dimensionOffset;
  final double symbolScale;

  static const editor = SceneMetrics();
  static const compact = SceneMetrics(
    beamHalf: 4,
    loadLength: 40,
    reactionLength: 34,
    labelSize: 11,
    letterOffset: 40,
    dimensionOffset: 56,
  );
  static const thumbnail = SceneMetrics(
    beamHalf: 3,
    loadLength: 22,
    reactionLength: 20,
    labelSize: 0,
    letterOffset: 0,
    dimensionOffset: 0,
    symbolScale: 0.6,
  );
}

enum SceneMode {
  /// Supports as symbols, loads as arrows: the problem as drawn.
  problem,

  /// The free body diagram: supports faded, their reactions drawn.
  freeBody,
}

/// Paints a beam problem: the beam, supports, loads, reactions, point
/// letters, dimensions and whatever the explanation is pointing at.
class BeamScene {
  BeamScene({
    required this.problem,
    required this.viewport,
    required this.colors,
    required this.units,
    this.metrics = SceneMetrics.editor,
    this.mode = SceneMode.problem,
    this.statics,
    this.reveal,
    this.highlights = const [],
    this.selectedId,
    this.showLabels = true,
    this.showDimensions = false,
    this.pulse = 0,
    this.ghostLength,
  }) : labels = ProblemLabels.of(problem);

  final BeamProblem problem;
  final SheetView viewport;
  final MechColors colors;
  final UnitSystem units;
  final SceneMetrics metrics;
  final SceneMode mode;

  /// Needed for the free body diagram.
  final StaticsSolution? statics;

  /// Which reactions have known values; all of them when null.
  final Reveal? reveal;
  final List<Highlight> highlights;
  final String? selectedId;
  final bool showLabels;
  final bool showDimensions;

  /// 0..1, animates the glow of highlighted things.
  final double pulse;

  /// A beam being drawn but not committed yet.
  final double? ghostLength;
  final ProblemLabels labels;

  double get y0 => viewport.origin.dy;

  String f(double si) => Num.compact(units.toDisplay(si, Dimension.force));
  String fu(double si) => '${f(si)} ${units.force.symbol}';
  String lu(double si) =>
      '${Num.compact(units.toDisplay(si, Dimension.length))} ${units.length.symbol}';
  String mu(double si) =>
      '${Num.compact(units.toDisplay(si, Dimension.moment))} ${units.moment.symbol}';

  bool _hl<T extends Highlight>(bool Function(T) test) =>
      highlights.whereType<T>().any(test);

  Color get _glow => colors.highlight.withValues(alpha: 0.25 + 0.25 * pulse);

  void paint(Canvas canvas, Size size) {
    if (ghostLength != null) _paintGhost(canvas);
    if (!problem.hasBeam) return;

    if (showDimensions) _paintDimensions(canvas);
    for (final s in problem.supports) {
      _paintSupport(canvas, s);
    }
    _paintBeam(canvas);
    for (final h in highlights.whereType<SectionHighlight>()) {
      _paintSection(canvas, size, h.x);
    }
    for (final l in problem.pointLoads) {
      _paintLoad(canvas, l);
    }
    if (mode == SceneMode.freeBody && statics != null) {
      for (final r in statics!.reactions) {
        _paintReaction(canvas, r);
      }
    }
    if (showLabels && metrics.labelSize > 0) _paintLetters(canvas);
    for (final h in highlights.whereType<ArmHighlight>()) {
      _paintArm(canvas, h);
    }
    for (final h in highlights.whereType<MomentCentreHighlight>()) {
      final c = viewport.toScreen(h.x);
      canvas.drawCircle(c, 11, Symbols.fill(_glow));
      canvas.drawCircle(c, 8, Symbols.stroke(colors.highlight, 2.2));
      canvas.drawCircle(c, 2.5, Symbols.fill(colors.highlight));
    }
  }

  // ---- beam --------------------------------------------------------------

  void _paintBeam(Canvas canvas) {
    final a = viewport.sx(0), b = viewport.sx(problem.length);
    final rect = Rect.fromLTRB(
      a,
      y0 - metrics.beamHalf,
      b,
      y0 + metrics.beamHalf,
    );
    final selected = selectedId == 'beam';
    if (selected) {
      canvas.drawRRect(
        RRect.fromRectAndRadius(rect.inflate(6), const Radius.circular(6)),
        Symbols.fill(colors.selection.withValues(alpha: 0.15)),
      );
    }
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, const Radius.circular(2.5)),
      Symbols.fill(colors.beam),
    );
    canvas.drawLine(
      Offset(a + 2, y0 - metrics.beamHalf + 1.5),
      Offset(b - 2, y0 - metrics.beamHalf + 1.5),
      Symbols.stroke(Colors.white.withValues(alpha: 0.25), 1),
    );
    if (selected) {
      canvas.drawRRect(
        RRect.fromRectAndRadius(rect.inflate(6), const Radius.circular(6)),
        Symbols.stroke(colors.selection, 1.5),
      );
    }
  }

  void _paintGhost(Canvas canvas) {
    final a = viewport.sx(0), b = viewport.sx(ghostLength!);
    final rect = Rect.fromLTRB(
      a,
      y0 - metrics.beamHalf,
      b,
      y0 + metrics.beamHalf,
    );
    canvas.drawRect(rect, Symbols.fill(colors.beam.withValues(alpha: 0.45)));
    Symbols.label(
      canvas,
      'L = ${lu(ghostLength!)}',
      Offset((a + b) / 2, y0 - 16),
      colors.ink,
      fontSize: 14,
      weight: FontWeight.w700,
      anchor: Alignment.bottomCenter,
      background: colors.paper.withValues(alpha: 0.9),
    );
  }

  // ---- supports ----------------------------------------------------------

  void _paintSupport(Canvas canvas, Support s) {
    final faded = mode == SceneMode.freeBody;
    final highlighted = _hl<SupportHighlight>((h) => h.supportId == s.id);
    var c = faded ? colors.support.withValues(alpha: 0.22) : colors.support;
    if (highlighted) c = colors.highlight;
    final x = viewport.sx(s.x);
    final scale = metrics.symbolScale;
    if (highlighted) {
      canvas.drawCircle(
        Offset(x, y0 + 14 * scale),
        22 * scale,
        Symbols.fill(_glow),
      );
    }
    switch (s.type) {
      case SupportType.pin:
        Symbols.pin(canvas, Offset(x, y0 + metrics.beamHalf), c, scale: scale);
      case SupportType.roller:
        Symbols.roller(
          canvas,
          Offset(x, y0 + metrics.beamHalf),
          c,
          scale: scale,
        );
      case SupportType.fixed:
        final facing = s.x <= problem.length / 2 ? 1 : -1;
        Symbols.fixed(
          canvas,
          Offset(x, y0),
          metrics.beamHalf,
          c,
          facing,
          scale: scale,
        );
    }
    if (selectedId == s.id) {
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          supportBounds(s).inflate(4),
          const Radius.circular(6),
        ),
        Symbols.stroke(colors.selection, 1.5),
      );
    }
  }

  Rect supportBounds(Support s) {
    final x = viewport.sx(s.x);
    final k = metrics.symbolScale;
    if (s.type == SupportType.fixed) {
      return Rect.fromLTRB(x - 12 * k, y0 - 28 * k, x + 12 * k, y0 + 28 * k);
    }
    return Rect.fromLTRB(
      x - 20 * k,
      y0 + metrics.beamHalf - 2,
      x + 20 * k,
      y0 + metrics.beamHalf + Symbols.supportHeight * k + 8,
    );
  }

  // ---- loads -------------------------------------------------------------

  /// Tail and head of a load arrow on screen. A load with a downward part
  /// pushes on the top face (head on the beam); one with an upward part
  /// pulls from the top face (tail on the beam); a horizontal load sits on
  /// the axis, outside the beam at an end.
  (Offset tail, Offset head) loadArrow(PointLoad l) {
    final x = viewport.sx(l.x);
    final rad = l.angleDeg * math.pi / 180;
    final dir = Offset(cosDeg(l.angleDeg), -sinDeg(l.angleDeg));
    final len = metrics.loadLength;
    if (l.fy < 0) {
      final head = Offset(x, y0 - metrics.beamHalf - 1);
      return (head - dir * len, head);
    }
    if (l.fy > 0) {
      final tail = Offset(x, y0 - metrics.beamHalf - 1);
      return (tail, tail + dir * len);
    }
    // Horizontal.
    final atLeft = l.x < 1e-9;
    final atRight = (l.x - problem.length).abs() < 1e-9;
    final pointsRight = math.cos(rad) > 0;
    if (atLeft) {
      final end = Offset(x - 2, y0);
      return pointsRight ? (end - dir * len, end) : (end, end + dir * len);
    }
    if (atRight) {
      final end = Offset(x + 2, y0);
      return pointsRight ? (end, end + dir * len) : (end - dir * len, end);
    }
    final head = Offset(x, y0 - metrics.beamHalf - 10);
    return (head - dir * len, head);
  }

  void _paintLoad(Canvas canvas, PointLoad l) {
    final (tail, head) = loadArrow(l);
    final highlighted = _hl<LoadHighlight>((h) => h.loadId == l.id);
    final c = highlighted ? colors.highlight : colors.load;
    if (highlighted) {
      canvas.drawLine(tail, head, Symbols.stroke(_glow, 10));
    }
    Symbols.arrow(
      canvas,
      tail,
      head,
      c,
      width: 2.6 * math.max(0.7, metrics.symbolScale),
      headSize: 11 * math.max(0.7, metrics.symbolScale),
    );
    if (selectedId == l.id) {
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromPoints(tail, head).inflate(9),
          const Radius.circular(6),
        ),
        Symbols.stroke(colors.selection, 1.5),
      );
    }
    if (metrics.labelSize <= 0) return;
    final text = '${labels.loadName(l.id)} = ${fu(l.magnitude)}';
    final away = tail - head;
    final anchor =
        away.dy < -4
            ? Alignment.bottomCenter
            : away.dy > 4
            ? Alignment.topCenter
            : (away.dx < 0 ? Alignment.centerRight : Alignment.centerLeft);
    final at = tail + Offset(anchor.x * -4, anchor.y * -4);
    Symbols.label(
      canvas,
      text,
      at,
      c,
      fontSize: metrics.labelSize,
      weight: FontWeight.w700,
      anchor: anchor,
    );
  }

  Rect loadBounds(PointLoad l) {
    final (tail, head) = loadArrow(l);
    return Rect.fromPoints(tail, head).inflate(14);
  }

  // ---- reactions ---------------------------------------------------------

  bool _known(Reaction r) => reveal == null || reveal!.solved.contains(r.id);

  void _paintReaction(Canvas canvas, Reaction r) {
    final s = statics!;
    final known = _known(r) && s.values.containsKey(r.id);
    final value = known ? s.valueOf(r.id) : 1.0;
    final zero = known && value == 0;
    final highlighted = _hl<ReactionHighlight>((h) => h.reactionId == r.id);
    var c = highlighted ? colors.highlight : colors.reaction;
    if (zero && !highlighted) c = c.withValues(alpha: 0.45);
    final x = viewport.sx(r.x);
    final len = metrics.reactionLength;
    final text =
        known
            ? (zero
                ? '${r.symbol} = 0'
                : '${r.symbol} = ${r.kind == ReactionKind.moment ? mu(value.abs()) : fu(value.abs())}')
            : '${r.symbol} = ?';
    final fs = metrics.labelSize;

    switch (r.kind) {
      case ReactionKind.vertical:
        final up = value >= 0;
        final bottom = Offset(x, y0 + metrics.beamHalf + 1);
        final far = bottom + Offset(0, len);
        final (tail, head) = up ? (far, bottom) : (bottom, far);
        if (highlighted) canvas.drawLine(tail, head, Symbols.stroke(_glow, 10));
        Symbols.arrow(canvas, tail, head, c, width: 2.6, headSize: 11);
        if (fs > 0) {
          Symbols.label(
            canvas,
            text,
            far + const Offset(0, 4),
            c,
            fontSize: fs,
            weight: FontWeight.w700,
            anchor: Alignment.topCenter,
            background: colors.paper.withValues(alpha: 0.85),
          );
        }
      case ReactionKind.horizontal:
        final right = value >= 0;
        final atRightEnd = (r.x - problem.length).abs() < 1e-9 && r.x > 0;
        final midSpan = r.x > 1e-9 && !atRightEnd;
        final y = midSpan ? y0 + metrics.beamHalf + len * 0.55 : y0;
        final end = Offset(atRightEnd ? x + 3 : x - 3, y);
        final outward = atRightEnd ? 1.0 : -1.0;
        final far = end + Offset(outward * len, 0);
        // The arrow points the way the force acts; it sits outside the beam.
        final pointsAtBeam = (right && !atRightEnd) || (!right && atRightEnd);
        final (tail, head) = pointsAtBeam ? (far, end) : (end, far);
        if (highlighted) canvas.drawLine(tail, head, Symbols.stroke(_glow, 10));
        Symbols.arrow(canvas, tail, head, c, width: 2.6, headSize: 11);
        if (fs > 0) {
          Symbols.label(
            canvas,
            text,
            Offset((end.dx + far.dx) / 2, y - 6),
            c,
            fontSize: fs,
            weight: FontWeight.w700,
            anchor: Alignment.bottomCenter,
            background: colors.paper.withValues(alpha: 0.85),
          );
        }
      case ReactionKind.moment:
        final ccw = value >= 0;
        final centre = Offset(x, y0);
        if (highlighted) {
          canvas.drawCircle(centre, 26, Symbols.stroke(_glow, 8));
        }
        Symbols.momentArc(canvas, centre, 22, ccw, c);
        if (fs > 0) {
          final outward = r.x <= problem.length / 2 ? -1.0 : 1.0;
          Symbols.label(
            canvas,
            text,
            centre + Offset(outward * 28, -26),
            c,
            fontSize: fs,
            weight: FontWeight.w700,
            anchor: outward < 0 ? Alignment.bottomRight : Alignment.bottomLeft,
            background: colors.paper.withValues(alpha: 0.85),
          );
        }
    }
  }

  // ---- letters, dimensions, highlights -----------------------------------

  void _paintLetters(Canvas canvas) {
    final fbd = mode == SceneMode.freeBody;
    for (final p in labels.points) {
      // Under the supports on the problem; beside the point on the FBD,
      // where the reaction arrows take the space below the beam.
      final at =
          fbd
              ? Offset(viewport.sx(p.x) + 7, y0 - metrics.beamHalf - 3)
              : Offset(viewport.sx(p.x), y0 + metrics.letterOffset);
      Symbols.label(
        canvas,
        p.letter,
        at,
        colors.inkSoft,
        fontSize: metrics.labelSize + 1,
        weight: FontWeight.w800,
        anchor: fbd ? Alignment.bottomLeft : Alignment.center,
      );
    }
  }

  List<double> get keyPositions {
    final xs =
        <double>{
            0,
            problem.length,
            for (final s in problem.supports) s.x,
            for (final l in problem.loads) l.x,
          }.toList()
          ..sort();
    final unique = <double>[];
    for (final x in xs) {
      if (unique.isEmpty || (x - unique.last).abs() > 1e-9) unique.add(x);
    }
    return unique;
  }

  void _paintDimensions(Canvas canvas) {
    final y = y0 + metrics.dimensionOffset;
    final xs = keyPositions;
    for (var i = 0; i < xs.length - 1; i++) {
      final a = viewport.sx(xs[i]), b = viewport.sx(xs[i + 1]);
      final text = lu(xs[i + 1] - xs[i]);
      final fits = Symbols.measure(text, 11).width + 6 < (b - a);
      Symbols.dimension(canvas, a, b, y, fits ? text : '', colors.inkSoft);
    }
    if (xs.length > 2) {
      Symbols.dimension(
        canvas,
        viewport.sx(0),
        viewport.sx(problem.length),
        y + 24,
        'L = ${lu(problem.length)}',
        colors.ink,
        fontSize: 12,
        arrows: true,
      );
    }
  }

  void _paintArm(Canvas canvas, ArmHighlight h) {
    // Across the load arrows, below their labels, so it stays inside even
    // a compact drawing.
    final y = y0 - metrics.beamHalf - metrics.loadLength * 0.55;
    final a = viewport.sx(h.fromX), b = viewport.sx(h.toX);
    final dash = Symbols.stroke(colors.highlight, 1.2);
    Symbols.dashed(canvas, Offset(a, y0 - 4), Offset(a, y - 6), dash);
    Symbols.dashed(canvas, Offset(b, y0 - 4), Offset(b, y - 6), dash);
    canvas.drawLine(Offset(a, y), Offset(b, y), Symbols.stroke(_glow, 7));
    Symbols.dimension(canvas, a, b, y, '', colors.highlight, arrows: true);
    Symbols.label(
      canvas,
      lu((h.toX - h.fromX).abs()),
      Offset((a + b) / 2, y - 4),
      colors.highlight,
      fontSize: metrics.labelSize + 1,
      weight: FontWeight.w800,
      anchor: Alignment.bottomCenter,
      background: colors.paper.withValues(alpha: 0.9),
    );
  }

  void _paintSection(Canvas canvas, Size size, double x) {
    final sx = viewport.sx(x);
    // Fade everything right of the cut: the left part is the free body.
    canvas.drawRect(
      Rect.fromLTRB(sx, 0, size.width, size.height),
      Symbols.fill(colors.paper.withValues(alpha: 0.55)),
    );
    canvas.drawRect(
      Rect.fromLTRB(
        viewport.sx(0),
        y0 - metrics.beamHalf - 3,
        sx,
        y0 + metrics.beamHalf + 3,
      ),
      Symbols.fill(colors.highlight.withValues(alpha: 0.18)),
    );
    Symbols.dashed(
      canvas,
      Offset(sx, y0 - metrics.loadLength - 6),
      Offset(sx, y0 + metrics.reactionLength + 4),
      Symbols.stroke(colors.highlight, 2),
    );
    Symbols.label(
      canvas,
      'x',
      Offset(sx + 4, y0 - metrics.loadLength - 4),
      colors.highlight,
      fontSize: metrics.labelSize + 1,
      weight: FontWeight.w800,
      anchor: Alignment.bottomLeft,
    );
  }

  // ---- hit testing -------------------------------------------------------

  /// The element under a touch at [p]: a load, a support, or "beam".
  String? hitTest(Offset p) {
    for (final l in problem.pointLoads.reversed) {
      final (tail, head) = loadArrow(l);
      if (_distanceToSegment(p, tail, head) < 20) return l.id;
    }
    for (final s in problem.supports.reversed) {
      if (supportBounds(s).inflate(10).contains(p)) return s.id;
    }
    if (problem.hasBeam &&
        (p.dy - y0).abs() < 22 &&
        p.dx > viewport.sx(0) - 14 &&
        p.dx < viewport.sx(problem.length) + 14) {
      return 'beam';
    }
    return null;
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

/// A [CustomPainter] around a [BeamScene].
class BeamScenePainter extends CustomPainter {
  BeamScenePainter(this.scene, {this.grid = false});

  final BeamScene scene;
  final bool grid;

  @override
  void paint(Canvas canvas, Size size) {
    if (grid) paintGrid(canvas, size, scene.viewport, scene.colors);
    scene.paint(canvas, size);
  }

  @override
  bool shouldRepaint(covariant BeamScenePainter old) => true;
}

/// Engineering paper: minor and major lines on a metric grid that adapts
/// to the zoom so lines never get denser than a few pixels.
void paintGrid(Canvas canvas, Size size, SheetView vp, MechColors colors) {
  canvas.drawRect(Offset.zero & size, Symbols.fill(colors.paper));
  const steps = [
    0.01,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    25.0,
    50.0,
    100.0,
  ];
  final minor = steps.firstWhere((s) => s * vp.scale >= 9, orElse: () => 100.0);
  final major = minor * (minor == 0.25 ? 4 : 5);
  final minorPaint = Symbols.stroke(colors.gridMinor, 1);
  final majorPaint = Symbols.stroke(colors.gridMajor, 1);

  void lines(double step, Paint paint) {
    final startX = (vp.worldX(0) / step).floor() * step;
    for (var x = startX; vp.sx(x) <= size.width; x += step) {
      final sx = vp.sx(x);
      canvas.drawLine(Offset(sx, 0), Offset(sx, size.height), paint);
    }
    final topY =
        ((vp.origin.dy) / vp.scale / step).ceil() *
        step; // world y at screen top
    for (var y = topY; vp.origin.dy - y * vp.scale <= size.height; y -= step) {
      final sy = vp.origin.dy - y * vp.scale;
      canvas.drawLine(Offset(0, sy), Offset(size.width, sy), paint);
    }
  }

  lines(minor, minorPaint);
  lines(major, majorPaint);
}
