import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/beam_scene.dart';
import '../../drawing/diagram_painter.dart';
import '../../drawing/palette.dart';
import '../../drawing/symbols.dart';
import '../../drawing/viewport.dart';
import '../../state/app_state.dart';
import '../analysis/math_view.dart';
import '../widgets/layout.dart';

/// "How to draw the SFD and BMD": a cut walks along the beam. Left of it
/// the beam stays bright, right of it fades; at the cut the internal V and M
/// that hold the left part in balance are drawn, and the SFD and BMD are
/// traced up to the cut. Beside it, the segment's V(x) and M(x) and their
/// values at x; at every support, load and V = 0 the walk pauses to say what
/// happens there.
class TourScreen extends StatefulWidget {
  const TourScreen({super.key, required this.problem, this.autoplay = true});

  final BeamProblem problem;

  /// Start walking as soon as the screen opens.
  final bool autoplay;

  @override
  State<TourScreen> createState() => _TourScreenState();
}

class _TourScreenState extends State<TourScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _anim =
      AnimationController(vsync: this)
        ..addListener(_onTick)
        ..addStatusListener((status) {
          if (status == AnimationStatus.completed) _arrived();
        });
  Tween<double> _tween = Tween(begin: 0, end: 0);
  Timer? _hold;

  DiagramTour? _tour;
  AppSettings? _builtWith;
  DiagramGeometry? _shearGeo, _momentGeo;

  double _x = 0;

  /// Where the cut is, in metres.
  @visibleForTesting
  double get cut => _x;
  int _target = 0;
  bool _playing = false;
  double _speed = 1;
  bool _started = false;

  DiagramTour? _tourFor(AppState app) {
    if (_tour == null || !identical(_builtWith, app.settings)) {
      _tour = DiagramTour.of(app.solve(widget.problem));
      _builtWith = app.settings;
      final t = _tour;
      if (t != null) {
        _shearGeo = GraphEngine.build(t.forces.shear, DiagramKind.shear);
        _momentGeo = GraphEngine.build(t.forces.moment, DiagramKind.moment);
      }
    }
    return _tour;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_started && widget.autoplay) {
      _started = true;
      // A moment on the introduction, then walk.
      _hold = Timer(const Duration(milliseconds: 1800), () {
        if (mounted && !_playing) _play();
      });
    }
  }

  @override
  void dispose() {
    _hold?.cancel();
    _anim.dispose();
    super.dispose();
  }

  double get _eps => 1e-6 * math.max(1.0, _tour?.length ?? 1);

  void _onTick() => setState(() => _x = _tween.evaluate(_anim));

  void _moveTo(int index, {bool fast = false}) {
    final tour = _tour!;
    _hold?.cancel();
    final to = tour.stops[index].x;
    final share = (to - _x).abs() / tour.length;
    final ms = fast ? 380.0 : (share * 9000 / _speed).clamp(300.0, 9000.0);
    _tween = Tween(begin: _x, end: to);
    _target = index;
    _anim.duration = Duration(milliseconds: ms.round());
    _anim.forward(from: 0);
  }

  void _arrived() {
    final tour = _tour!;
    setState(() => _x = tour.stops[_target].x);
    if (!_playing) return;
    if (_target >= tour.stops.length - 1) {
      setState(() => _playing = false);
      return;
    }
    // Stay long enough on a stop to read what happens there.
    final stop = tour.stops[_target];
    final ms = (stop.lines.isEmpty ? 700 : 3200) / _speed;
    _hold = Timer(Duration(milliseconds: ms.round()), () {
      if (mounted && _playing) _moveTo(_target + 1);
    });
  }

  int? _nextIndex() {
    final i = _tour!.stops.indexWhere((s) => s.x > _x + _eps);
    return i < 0 ? null : i;
  }

  int? _prevIndex() {
    final i = _tour!.stops.lastIndexWhere((s) => s.x < _x - _eps);
    return i < 0 ? null : i;
  }

  void _play() {
    final tour = _tour;
    if (tour == null) return;
    if (_x >= tour.length - _eps) _x = 0;
    setState(() => _playing = true);
    final next = _nextIndex();
    if (next != null) _moveTo(next);
  }

  void _pause() {
    _hold?.cancel();
    _anim.stop();
    setState(() => _playing = false);
  }

  void _step(int? index) {
    if (index == null) return;
    _pause();
    _moveTo(index, fast: true);
  }

  void _scrub(double x) {
    _pause();
    final tour = _tour!;
    // Settle on a stop within a fingertip, so its explanation shows.
    for (final s in tour.stops) {
      if ((s.x - x).abs() < tour.length * 0.012) {
        x = s.x;
        break;
      }
    }
    setState(() => _x = x.clamp(0.0, tour.length).toDouble());
  }

  void _cycleSpeed() {
    setState(() => _speed = _speed == 1 ? 2 : (_speed == 2 ? 0.5 : 1));
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final tour = _tourFor(app);
    final wide = isWide(context);
    if (tour == null) {
      return Scaffold(
        appBar: AppBar(title: Text(s.tourTitle)),
        body: Center(child: Text(s.diagramsWillAppear)),
      );
    }
    final diagrams = LayoutBuilder(
      builder: (context, constraints) {
        final size = constraints.biggest;
        SheetView vp() => SheetView.fit(
          tour.length,
          Size(size.width, size.height * 0.42),
          margin: 58,
          yFraction: 0.55,
        );
        void touch(Offset p) => _scrub(vp().worldX(p.dx));
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapDown: (d) => touch(d.localPosition),
          onHorizontalDragStart: (d) => touch(d.localPosition),
          onHorizontalDragUpdate: (d) => touch(d.localPosition),
          child: CustomPaint(
            key: const ValueKey('tour-canvas'),
            size: size,
            painter: _TourPainter(
              tour: tour,
              x: _x,
              colors: MechColors.of(context),
              units: app.units,
              shearGeo: _shearGeo!,
              momentGeo: _momentGeo!,
              leftPart: s.tourLeftPart,
            ),
          ),
        );
      },
    );
    final panel = _TourPanel(tour: tour, x: _x, onStart: !_playing && _x == 0);
    final controls = _Controls(
      back: wide,
      x: _x,
      length: tour.length,
      playing: _playing,
      speed: _speed,
      onPlay: _playing ? _pause : _play,
      onNext: _nextIndex() == null ? null : () => _step(_nextIndex()),
      onPrev: _prevIndex() == null ? null : () => _step(_prevIndex()),
      onScrub: _scrub,
      onSpeed: _cycleSpeed,
    );
    final height = MediaQuery.sizeOf(context).height;
    return Scaffold(
      // Sideways the height is short: no title bar (the way back sits in
      // the controls), so the drawing gets it.
      appBar:
          wide
              ? null
              : AppBar(
                title: Text(s.tourTitle, overflow: TextOverflow.ellipsis),
              ),
      body: SafeArea(
        child:
            wide
                ? Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(flex: 11, child: diagrams),
                    const VerticalDivider(width: 1),
                    Expanded(flex: 9, child: panel),
                  ],
                )
                : Column(
                  children: [
                    SizedBox(
                      height: (height * 0.44).clamp(260.0, 440.0),
                      child: diagrams,
                    ),
                    const Divider(height: 1),
                    Expanded(child: panel),
                  ],
                ),
      ),
      bottomNavigationBar: SafeArea(child: controls),
    );
  }
}

class _Controls extends StatelessWidget {
  const _Controls({
    required this.back,
    required this.x,
    required this.length,
    required this.playing,
    required this.speed,
    required this.onPlay,
    required this.onNext,
    required this.onPrev,
    required this.onScrub,
    required this.onSpeed,
  });

  /// A back button first, when there is no title bar.
  final bool back;
  final double x;
  final double length;
  final bool playing;
  final double speed;
  final VoidCallback onPlay;
  final VoidCallback? onNext;
  final VoidCallback? onPrev;
  final ValueChanged<double> onScrub;
  final VoidCallback onSpeed;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surfaceContainer,
      child: Directionality(
        // A timeline runs left to right, like the beam.
        textDirection: TextDirection.ltr,
        // A fixed height: a slider left to itself takes all it is given.
        child: Container(
          height: 56,
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
          child: Row(
            children: [
              if (back) const BackButton(),
              IconButton(
                key: const ValueKey('tour-prev'),
                tooltip: s.tourPrev,
                onPressed: onPrev,
                icon: const Icon(Icons.skip_previous_rounded),
              ),
              IconButton.filled(
                key: const ValueKey('tour-play'),
                tooltip: playing ? s.tourPause : s.tourPlay,
                onPressed: onPlay,
                icon: Icon(
                  playing ? Icons.pause_rounded : Icons.play_arrow_rounded,
                ),
              ),
              IconButton(
                key: const ValueKey('tour-next'),
                tooltip: s.tourNext,
                onPressed: onNext,
                icon: const Icon(Icons.skip_next_rounded),
              ),
              Expanded(
                child: Slider(
                  key: const ValueKey('tour-slider'),
                  value: x.clamp(0.0, length).toDouble(),
                  max: length,
                  onChanged: onScrub,
                ),
              ),
              TextButton(
                key: const ValueKey('tour-speed'),
                onPressed: onSpeed,
                child: Text(
                  '${speed == 0.5 ? '½' : Num.compact(speed)}×',
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The words beside the drawing: what happens at the stop the cut is on,
/// then V(x) and M(x) for the segment it is in, with their values at x.
class _TourPanel extends StatelessWidget {
  const _TourPanel({
    required this.tour,
    required this.x,
    required this.onStart,
  });

  final DiagramTour tour;
  final double x;
  final bool onStart;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final u = app.units;
    final colors = MechColors.of(context);
    final theme = Theme.of(context);
    final stop = tour.stopAt(x);
    final seg = tour.segmentAt(x);
    String len(double si) =>
        '${Num.fixed(u.toDisplay(si, Dimension.length))} ${u.length.symbol}';
    final xText = Num.fixed(u.toDisplay(x, Dimension.length));
    final v = tour.shearAt(x), m = tour.momentAt(x);

    void explain(MathToken t) {
      final e = t.explanation;
      if (e == null) return;
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
          SnackBar(content: Text(e), duration: const Duration(seconds: 6)),
        );
    }

    Widget line(MathLine l, {double size = 15}) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Directionality(
            textDirection: TextDirection.ltr,
            child: Align(
              alignment: Alignment.centerLeft,
              child: MathLineView(line: l, onTap: explain, fontSize: size),
            ),
          ),
          if (l.note != null)
            Padding(
              padding: const EdgeInsets.only(top: 2, bottom: 4),
              child: Text('↳ ${l.note}', style: theme.textTheme.bodySmall),
            ),
        ],
      ),
    );

    Widget value(String name, double si, Dimension d, Color color) {
      final text =
          '$name($xText) = ${Num.signed(u.toDisplay(si, d))} ${u.unitFor(d).symbol}';
      return Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Directionality(
          textDirection: TextDirection.ltr,
          child: Align(
            alignment: Alignment.centerLeft,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                text,
                style: TextStyle(
                  color: color,
                  fontWeight: FontWeight.w800,
                  fontSize: 15,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ),
          ),
        ),
      );
    }

    Widget heading(String text, Color color) => Padding(
      padding: const EdgeInsets.only(top: 10, bottom: 2),
      child: Text(
        text,
        style: theme.textTheme.titleSmall?.copyWith(
          color: color,
          fontWeight: FontWeight.w800,
        ),
      ),
    );

    final stopTitle = switch (stop?.kind) {
      TourStopKind.start => s.tourStart,
      TourStopKind.end => s.tourEnd,
      TourStopKind.zeroShear => s.tourZero,
      _ => s.tourPoint,
    };

    // A few cards only: all built, so any of them can be scrolled to.
    return SingleChildScrollView(
      key: const ValueKey('tour-panel'),
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (onStart && x == 0)
            Card(
              color: theme.colorScheme.secondaryContainer,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(s.tourIntro, style: theme.textTheme.bodyMedium),
              ),
            ),
          if (stop != null && stop.lines.isNotEmpty)
            AnimatedContainer(
              key: ValueKey('tour-stop-${stop.x}'),
              duration: const Duration(milliseconds: 250),
              margin: const EdgeInsets.only(bottom: 6),
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: colors.highlight.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: colors.highlight, width: 1.4),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '$stopTitle   ·   x = ${len(stop.x)}',
                    style: theme.textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 4),
                  for (final l in stop.lines) line(l, size: 14.5),
                ],
              ),
            ),
          Directionality(
            textDirection: TextDirection.ltr,
            child: Text(
              '${Num.compact(u.toDisplay(seg.x0, Dimension.length))} '
              '< x < ${Num.compact(u.toDisplay(seg.x1, Dimension.length))} ${u.length.symbol}'
              '      x = ${len(x)}',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          heading(s.tourShearHow, colors.shear),
          for (final l in seg.shear) line(l),
          value('V', v, Dimension.force, colors.shear),
          heading(s.tourMomentHow, colors.moment),
          for (final l in seg.moment) line(l),
          value('M', m, Dimension.moment, colors.moment),
          if (seg.shearRule.isNotEmpty || seg.momentRule.isNotEmpty) ...[
            heading(s.tourRules, theme.colorScheme.onSurfaceVariant),
            for (final l in [...seg.shearRule, ...seg.momentRule])
              line(l, size: 13.5),
          ],
        ],
      ),
    );
  }
}

class _TourPainter extends CustomPainter {
  _TourPainter({
    required this.tour,
    required this.x,
    required this.colors,
    required this.units,
    required this.shearGeo,
    required this.momentGeo,
    required this.leftPart,
  });

  final DiagramTour tour;
  final double x;
  final MechColors colors;
  final UnitSystem units;
  final DiagramGeometry shearGeo;
  final DiagramGeometry momentGeo;
  final String leftPart;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Symbols.fill(colors.paper));
    final fbd = Rect.fromLTWH(0, 0, size.width, size.height * 0.42);
    final sfd = Rect.fromLTWH(0, fbd.bottom, size.width, size.height * 0.29);
    final bmd = Rect.fromLTWH(0, sfd.bottom, size.width, size.height * 0.29);
    final vp = SheetView.fit(
      tour.length,
      fbd.size,
      margin: 58,
      yFraction: 0.55,
    );
    final sx = vp.sx(x);
    final progress = (x / tour.length).clamp(0.0, 1.0);

    // The beam with every force on it, the part right of the cut faded.
    canvas.save();
    canvas.clipRect(fbd);
    BeamScene(
      problem: tour.solution.problem,
      viewport: vp,
      colors: colors,
      units: units,
      metrics: SceneMetrics.compact,
      mode: SceneMode.freeBody,
      statics: tour.solution.statics,
    ).paint(canvas, fbd.size);
    // A force right at the cut belongs to the left part (V and M are
    // taken just right of it), so the fading starts a little after it.
    canvas.drawRect(
      Rect.fromLTRB(sx + 9, fbd.top, fbd.right, fbd.bottom),
      Symbols.fill(colors.paper.withValues(alpha: 0.72)),
    );
    _paintInternal(canvas, vp, sx);
    canvas.restore();

    // The diagrams, traced up to the cut.
    for (final (rect, kind, geo, function, color, title, dim) in [
      (
        sfd,
        DiagramKind.shear,
        shearGeo,
        tour.forces.shear,
        colors.shear,
        'SFD  V (${units.force.symbol})',
        Dimension.force,
      ),
      (
        bmd,
        DiagramKind.moment,
        momentGeo,
        tour.forces.moment,
        colors.moment,
        'BMD  M (${units.moment.symbol})',
        Dimension.moment,
      ),
    ]) {
      canvas.drawLine(
        Offset(0, rect.top),
        Offset(size.width, rect.top),
        Symbols.stroke(colors.gridMajor, 1),
      );
      final band = DiagramBand(
        kind: kind,
        function: function,
        geometry: geo,
        rect: rect,
        viewport: vp,
        colors: colors,
        color: color,
        title: title,
        toDisplay: (si) => units.toDisplay(si, dim),
        progress: progress,
      );
      band.paint(canvas);
      band.paintCursor(canvas, x);
      final value =
          kind == DiagramKind.shear ? tour.shearAt(x) : tour.momentAt(x);
      final p = band.point(x, value);
      Symbols.label(
        canvas,
        Num.compact(units.toDisplay(value, dim), maxDecimals: 2),
        p + Offset(8, value >= 0 ? -10 : 10),
        color,
        fontSize: 12,
        weight: FontWeight.w800,
        anchor: Alignment.centerLeft,
        background: colors.paper.withValues(alpha: 0.85),
      );
    }

    // The cut, through all three.
    Symbols.dashed(
      canvas,
      Offset(sx, 6),
      Offset(sx, size.height - 18),
      Symbols.stroke(colors.highlight, 2),
      dash: 6,
      gap: 4,
    );
    // At the foot of the cut, clear of the loads' labels above the beam.
    Symbols.label(
      canvas,
      'x = ${Num.fixed(units.toDisplay(x, Dimension.length))} ${units.length.symbol}',
      Offset(sx, size.height - 2),
      colors.highlight,
      fontSize: 12,
      weight: FontWeight.w800,
      anchor: Alignment.bottomCenter,
      background: colors.paper.withValues(alpha: 0.9),
    );
  }

  /// At the cut, on the face of the left part: the shear V (drawn the way
  /// it really acts; positive acts down) and the moment M (positive turns
  /// counter-clockwise there, which sags the beam).
  void _paintInternal(Canvas canvas, SheetView vp, double sx) {
    final y0 = vp.origin.dy;
    final v = tour.shearAt(x), m = tour.momentAt(x);
    final down = v >= 0;
    final ax = sx + 7;
    final (tail, head) =
        down
            ? (Offset(ax, y0 - 30), Offset(ax, y0 - 4))
            : (Offset(ax, y0 + 30), Offset(ax, y0 + 4));
    if (v.abs() > 1e-9) {
      Symbols.arrow(canvas, tail, head, colors.shear, width: 2.4, headSize: 9);
    }
    Symbols.label(
      canvas,
      'V = ${Num.compact(units.toDisplay(v.abs(), Dimension.force), maxDecimals: 2)}',
      Offset(ax + 5, down ? y0 - 30 : y0 + 30),
      colors.shear,
      fontSize: 11.5,
      weight: FontWeight.w800,
      anchor: down ? Alignment.bottomLeft : Alignment.topLeft,
      background: colors.paper.withValues(alpha: 0.85),
    );
    if (m.abs() > 1e-9) {
      Symbols.momentArc(
        canvas,
        Offset(sx, y0),
        15,
        m >= 0,
        colors.moment,
        width: 2.2,
      );
    }
    Symbols.label(
      canvas,
      'M = ${Num.compact(units.toDisplay(m.abs(), Dimension.moment), maxDecimals: 2)}',
      Offset(ax + 5, down ? y0 + 22 : y0 - 22),
      colors.moment,
      fontSize: 11.5,
      weight: FontWeight.w800,
      anchor: down ? Alignment.topLeft : Alignment.bottomLeft,
      background: colors.paper.withValues(alpha: 0.85),
    );
    if (sx < 90) return; // no room left of the cut yet
    Symbols.label(
      canvas,
      '← $leftPart',
      Offset(sx - 6, vp.origin.dy + 34),
      colors.inkSoft,
      fontSize: 11,
      weight: FontWeight.w700,
      anchor: Alignment.topRight,
      background: colors.paper.withValues(alpha: 0.8),
    );
  }

  @override
  bool shouldRepaint(covariant _TourPainter old) =>
      old.x != x || old.tour != tour || old.colors != colors;
}
