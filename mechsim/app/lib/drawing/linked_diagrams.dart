import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../state/app_state.dart';
import '../state/highlight_controller.dart';
import 'beam_scene.dart';
import 'diagram_painter.dart';
import 'palette.dart';
import 'symbols.dart';
import 'viewport.dart';

/// The free body diagram, the SFD and the BMD stacked on one shared x-axis.
/// Touching any of them puts a cross-hair through all three and reads out
/// x, V and M together; the explanation lights things up through
/// [HighlightController].
class LinkedDiagrams extends StatefulWidget {
  const LinkedDiagrams({
    super.key,
    required this.solution,
    required this.highlights,
    this.reveal,
    this.showCursorHint = true,
  });

  final Solution solution;
  final HighlightController highlights;

  /// What to show; everything when null (the full results view).
  final Reveal? reveal;
  final bool showCursorHint;

  @override
  State<LinkedDiagrams> createState() => _LinkedDiagramsState();
}

class _LinkedDiagramsState extends State<LinkedDiagrams>
    with TickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  );
  late final AnimationController _draw = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1300),
    value: 1,
  );
  DiagramKind? _drawing;
  double? _cursor;

  @override
  void initState() {
    super.initState();
    widget.highlights.addListener(_onHighlight);
    _onHighlight();
  }

  @override
  void didUpdateWidget(LinkedDiagrams old) {
    super.didUpdateWidget(old);
    if (old.highlights != widget.highlights) {
      old.highlights.removeListener(_onHighlight);
      widget.highlights.addListener(_onHighlight);
    }
    if (old.solution != widget.solution) _cursor = null;
    final before = old.reveal, now = widget.reveal;
    if (before != null && now != null) {
      DiagramKind? fresh;
      if (!before.shear && now.shear) fresh = DiagramKind.shear;
      if (!before.moment && now.moment) fresh = DiagramKind.moment;
      if (!before.axial && now.axial) fresh = DiagramKind.axial;
      if (fresh != null) {
        _drawing = fresh;
        _draw.forward(from: 0);
      }
    }
  }

  void _onHighlight() {
    if (widget.highlights.isEmpty) {
      _pulse.stop();
      _pulse.value = 0;
    } else if (!_pulse.isAnimating) {
      _pulse.repeat(reverse: true);
    }
    final point =
        widget.highlights.items.whereType<DiagramPointHighlight>().firstOrNull;
    if (point != null) _cursor = point.x;
    setState(() {});
  }

  @override
  void dispose() {
    widget.highlights.removeListener(_onHighlight);
    _pulse.dispose();
    _draw.dispose();
    super.dispose();
  }

  SheetView _viewport(Size size) => SheetView.fit(
    widget.solution.problem.length,
    size,
    margin: 58,
    yFraction: 0.55,
  );

  void _setCursor(Offset local, Size size) {
    final forces = widget.solution.forces;
    if (forces == null) return;
    final vp = _viewport(size);
    var x = vp.worldX(local.dx).clamp(0.0, widget.solution.problem.length);
    // Snap to a breakpoint within a fingertip, so x = 3 really is 3.
    for (final b in forces.breakpoints) {
      if ((vp.sx(b) - local.dx).abs() < 14) {
        x = b;
        break;
      }
    }
    setState(() => _cursor = x.toDouble());
  }

  @override
  Widget build(BuildContext context) {
    final colors = MechColors.of(context);
    final app = AppScope.of(context);
    return Column(
      children: [
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) {
              final size = Size(constraints.maxWidth, constraints.maxHeight);
              return GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTapDown: (d) => _setCursor(d.localPosition, size),
                onHorizontalDragUpdate:
                    (d) => _setCursor(d.localPosition, size),
                onHorizontalDragStart: (d) => _setCursor(d.localPosition, size),
                child: AnimatedBuilder(
                  animation: Listenable.merge([_pulse, _draw]),
                  builder:
                      (context, _) => CustomPaint(
                        size: size,
                        painter: _LinkedPainter(
                          solution: widget.solution,
                          reveal: widget.reveal,
                          highlights: widget.highlights.items,
                          colors: colors,
                          viewport: _viewport,
                          cursor: _cursor,
                          pulse: _pulse.value,
                          drawing: _drawing,
                          drawProgress: Curves.easeInOut.transform(_draw.value),
                          placeholder: app.s.diagramsWillAppear,
                        ),
                      ),
                ),
              );
            },
          ),
        ),
        // The read-out lives under the drawings so it never hides a load.
        _ReadoutStrip(
          solution: widget.solution,
          x: _cursor,
          reveal: widget.reveal,
          hint: widget.showCursorHint ? app.s.tapDiagramHint : null,
          onClose: () => setState(() => _cursor = null),
        ),
      ],
    );
  }
}

/// How the height is shared between the bands.
List<(String, double)> _bands(bool axial) =>
    axial
        ? [('fbd', 0.36), ('shear', 0.213), ('moment', 0.214), ('axial', 0.213)]
        : [('fbd', 0.42), ('shear', 0.29), ('moment', 0.29)];

class _LinkedPainter extends CustomPainter {
  _LinkedPainter({
    required this.solution,
    required this.reveal,
    required this.highlights,
    required this.colors,
    required this.viewport,
    required this.cursor,
    required this.pulse,
    required this.drawing,
    required this.drawProgress,
    required this.placeholder,
  });

  final Solution solution;
  final Reveal? reveal;
  final List<Highlight> highlights;
  final MechColors colors;
  final SheetView Function(Size) viewport;
  final double? cursor;
  final double pulse;
  final DiagramKind? drawing;
  final double drawProgress;
  final String placeholder;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Symbols.fill(colors.paper));
    final forces = solution.forces;
    final units = solution.units;
    final axial = forces?.hasAxial ?? false;
    final bands = _bands(axial);
    var top = 0.0;
    final rects = <String, Rect>{};
    for (final (name, share) in bands) {
      final h = size.height * share;
      rects[name] = Rect.fromLTWH(0, top, size.width, h);
      top += h;
    }
    final fbdRect = rects['fbd']!;
    final vp = viewport(fbdRect.size);

    // Faint guides at every breakpoint tie the three drawings together.
    if (forces != null) {
      final guide = Symbols.stroke(colors.gridMajor, 1);
      for (final b in forces.breakpoints) {
        Symbols.dashed(
          canvas,
          Offset(vp.sx(b), fbdRect.bottom - 6),
          Offset(vp.sx(b), size.height - 4),
          guide,
          dash: 3,
          gap: 4,
        );
      }
    }

    canvas.save();
    canvas.clipRect(fbdRect);
    final showReactions = reveal?.reactions ?? true;
    BeamScene(
      problem: solution.problem,
      viewport: vp,
      colors: colors,
      units: units,
      metrics: SceneMetrics.compact,
      mode:
          showReactions && solution.statics.isSolved
              ? SceneMode.freeBody
              : SceneMode.problem,
      statics: solution.statics,
      reveal: reveal,
      highlights: highlights,
      pulse: pulse,
    ).paint(canvas, fbdRect.size);
    canvas.restore();
    Symbols.label(
      canvas,
      showReactions ? 'FBD' : 'Beam',
      const Offset(6, 4),
      colors.inkSoft,
      fontSize: 11.5,
      weight: FontWeight.w800,
      anchor: Alignment.topLeft,
    );

    if (forces == null) return;
    final defs = <String, (DiagramKind, Color, String, Dimension, bool)>{
      'shear': (
        DiagramKind.shear,
        colors.shear,
        'SFD  V (${units.force.symbol})',
        Dimension.force,
        reveal?.shear ?? true,
      ),
      'moment': (
        DiagramKind.moment,
        colors.moment,
        'BMD  M (${units.moment.symbol})',
        Dimension.moment,
        reveal?.moment ?? true,
      ),
      'axial': (
        DiagramKind.axial,
        colors.axial,
        'AFD  N (${units.force.symbol})',
        Dimension.force,
        reveal?.axial ?? true,
      ),
    };
    final drawn = <DiagramBand>[];
    for (final entry in defs.entries) {
      final rect = rects[entry.key];
      if (rect == null) continue;
      final (kind, color, title, dim, visible) = entry.value;
      canvas.drawLine(
        Offset(0, rect.top),
        Offset(size.width, rect.top),
        Symbols.stroke(colors.gridMajor, 1),
      );
      if (!visible) {
        DiagramBand.paintPlaceholder(
          canvas,
          rect,
          title,
          placeholder,
          color,
          colors,
          vp,
          solution.problem.length,
        );
        continue;
      }
      final band = DiagramBand(
        kind: kind,
        function: forces.of(kind),
        geometry: GraphEngine.build(forces.of(kind), kind),
        rect: rect,
        viewport: vp,
        colors: colors,
        color: color,
        title: title,
        toDisplay: (si) => units.toDisplay(si, dim),
        progress: drawing == kind ? drawProgress : 1,
        highlights: highlights,
        pulse: pulse,
      );
      band.paint(canvas);
      drawn.add(band);
    }

    for (final h in highlights.whereType<SectionHighlight>()) {
      final sx = vp.sx(h.x);
      Symbols.dashed(
        canvas,
        Offset(sx, fbdRect.bottom),
        Offset(sx, size.height),
        Symbols.stroke(colors.highlight, 1.6),
      );
    }
    if (cursor != null) {
      final sx = vp.sx(cursor!);
      canvas.drawLine(
        Offset(sx, 0),
        Offset(sx, size.height),
        Symbols.stroke(colors.ink.withValues(alpha: 0.55), 1.2),
      );
      for (final band in drawn) {
        band.paintCursor(canvas, cursor!);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _LinkedPainter old) => true;
}

class _ReadoutStrip extends StatelessWidget {
  const _ReadoutStrip({
    required this.solution,
    required this.x,
    required this.reveal,
    required this.hint,
    required this.onClose,
  });

  final Solution solution;
  final double? x;
  final Reveal? reveal;
  final String? hint;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = MechColors.of(context);
    final forces = solution.forces;
    final x = this.x;
    Widget content;
    if (x == null || forces == null) {
      if (hint == null) return const SizedBox.shrink();
      content = Row(
        children: [
          Icon(Icons.touch_app_outlined, size: 16, color: colors.inkSoft),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              hint!,
              style: theme.textTheme.bodySmall,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      );
    } else {
      final u = solution.units;
      String value(PiecewiseFunction f, Dimension d) {
        final l = f.leftLimit(x), r = f.rightLimit(x);
        String one(double si) => Num.signed(u.toDisplay(si, d));
        if (x < 1e-9) return one(r);
        if ((x - solution.problem.length).abs() < 1e-9) return one(l);
        if ((l - r).abs() > 1e-9 * math.max(1, l.abs())) {
          return '${one(l)} → ${one(r)}';
        }
        return one(f.valueAt(x));
      }

      final rows = <(String, String, Color)>[
        (
          'x',
          '${Num.fixed(u.toDisplay(x, Dimension.length))} ${u.length.symbol}',
          colors.ink,
        ),
        if (reveal?.shear ?? true)
          (
            'V',
            '${value(forces.shear, Dimension.force)} ${u.force.symbol}',
            colors.shear,
          ),
        if (reveal?.moment ?? true)
          (
            'M',
            '${value(forces.moment, Dimension.moment)} ${u.moment.symbol}',
            colors.moment,
          ),
        if (forces.hasAxial && (reveal?.axial ?? true))
          (
            'N',
            '${value(forces.axial, Dimension.force)} ${u.force.symbol}',
            colors.axial,
          ),
      ];
      content = Directionality(
        textDirection: TextDirection.ltr,
        child: Row(
          children: [
            Expanded(
              child: FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text.rich(
                  TextSpan(
                    children: [
                      for (final (name, text, color) in rows) ...[
                        TextSpan(
                          text: '$name = ',
                          style: TextStyle(
                            color: color,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        TextSpan(text: '$text     '),
                      ],
                    ],
                  ),
                  style: const TextStyle(
                    fontSize: 13.5,
                    fontFeatures: [FontFeature.tabularFigures()],
                  ),
                ),
              ),
            ),
            InkWell(
              onTap: onClose,
              customBorder: const CircleBorder(),
              child: const Padding(
                padding: EdgeInsets.all(4),
                child: Icon(Icons.close, size: 16),
              ),
            ),
          ],
        ),
      );
    }
    return Container(
      height: 32,
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      alignment: Alignment.centerLeft,
      color: theme.colorScheme.surfaceContainerHigh,
      child: content,
    );
  }
}
