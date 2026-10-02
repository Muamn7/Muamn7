import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../state/app_state.dart';
import '../../state/editor_controller.dart';
import '../widgets/number_field.dart';
import '../widgets/tool_icons.dart';

/// Exact values for the selected element: the beam's length, a support's
/// type and position, a load's magnitude, position and direction.
///
/// Upright it is a panel above the tools. Sideways ([compact]) it is one
/// strip under the sheet, so the drawing keeps the whole width and nearly
/// all of the height.
class PropertiesPanel extends StatelessWidget {
  const PropertiesPanel({
    super.key,
    required this.controller,
    required this.onMessage,
    this.compact = false,
  });

  final EditorController controller;
  final ValueChanged<String> onMessage;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final props = _props(context);
    if (props == null) return const SizedBox.shrink();
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final s = AppScope.of(context).s;
    final id = controller.selected!;

    final close = IconButton(
      visualDensity: VisualDensity.compact,
      tooltip: s.cancel,
      onPressed: () => controller.select(null),
      icon: const Icon(Icons.close),
    );
    final delete = IconButton(
      visualDensity: VisualDensity.compact,
      tooltip: s.delete,
      onPressed: () => controller.delete(id),
      icon: const Icon(Icons.delete_outline),
    );
    Widget note(String value) => Directionality(
      textDirection: TextDirection.ltr,
      child: Text(
        value,
        style: text.bodySmall?.copyWith(fontWeight: FontWeight.w700),
      ),
    );
    final border = BoxDecoration(
      border: Border(top: BorderSide(color: scheme.outlineVariant)),
    );

    if (compact) {
      final items = [
        for (final group in props.groups) ...group,
        if (props.note != null) note(props.note!),
      ];
      return Material(
        color: scheme.surfaceContainerLow,
        child: Container(
          decoration: border,
          child: Row(
            children: [
              close,
              ToolIcon(props.icon, size: 22),
              const SizedBox(width: 4),
              Text(
                props.short,
                style: text.titleSmall?.copyWith(fontWeight: FontWeight.w800),
              ),
              // Everything stays in view: a second line rather than
              // controls hidden off the edge.
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 6, 12, 6),
                  child: Wrap(
                    spacing: 10,
                    runSpacing: 6,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: items,
                  ),
                ),
              ),
              delete,
            ],
          ),
        ),
      );
    }

    return Material(
      color: scheme.surfaceContainerLow,
      child: Container(
        width: double.infinity,
        decoration: border,
        padding: const EdgeInsets.fromLTRB(14, 4, 6, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    props.title,
                    style: text.titleSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                delete,
                close,
              ],
            ),
            for (var i = 0; i < props.groups.length; i++) ...[
              if (i > 0) const SizedBox(height: 8),
              props.groups[i].length == 1
                  ? props.groups[i].single
                  : Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: props.groups[i],
                  ),
            ],
            if (props.note != null)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: note(props.note!),
              ),
            if (props.help != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(props.help!, style: text.bodySmall),
              ),
          ],
        ),
      ),
    );
  }

  _Props? _props(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final u = app.units;
    final p = controller.problem;
    final id = controller.selected!;
    final labels = ProblemLabels.of(p);

    double toL(double si) => u.toDisplay(si, Dimension.length);
    double fromL(double v) => u.fromDisplay(v, Dimension.length);
    String? onBeam(double v) {
      final x = fromL(v);
      if (x < -1e-9 || x > p.length + 1e-9) {
        return '0 … ${Num.compact(toL(p.length))} ${u.length.symbol}';
      }
      return null;
    }

    String? positive(double v) => v > 0 ? null : s.mustBePositive;

    // Narrower fields sideways, so a whole load fits in one or two lines.
    final width = compact ? 100.0 : 120.0;

    /// Upright, a two-way choice spells itself out; sideways the arrow
    /// alone, with the words as a tooltip.
    ButtonSegment<T> choice<T>(T value, String arrow, String words) =>
        ButtonSegment(
          value: value,
          label: Text(compact ? arrow : words),
          tooltip: compact ? words : null,
        );

    if (id == 'beam') {
      return _Props(
        title: s.beamProps,
        short: s.toolBeam,
        icon: Tool.beam,
        groups: [
          [
            NumberField(
              width: width,
              key: const ValueKey('beam-length'),
              label: s.length,
              value: toL(p.length),
              unit: u.length.symbol,
              validator: positive,
              onChanged: (v) => controller.setLength(fromL(v)),
            ),
          ],
        ],
      );
    }

    if (p.supportById(id) case final support?) {
      ButtonSegment<SupportType> segment(SupportType t, Tool tool, String l) =>
          ButtonSegment(
            value: t,
            label: compact ? null : Text(l),
            tooltip: compact ? l : null,
            icon: ToolIcon(tool, size: 18),
          );
      return _Props(
        title: '${s.supportProps} ${labels.pointOf(id)}',
        short: labels.pointOf(id),
        icon: switch (support.type) {
          SupportType.pin => Tool.pin,
          SupportType.roller => Tool.roller,
          SupportType.fixed => Tool.fixed,
        },
        groups: [
          [
            SegmentedButton<SupportType>(
              showSelectedIcon: false,
              style: const ButtonStyle(visualDensity: VisualDensity.compact),
              segments: [
                segment(SupportType.pin, Tool.pin, s.toolPin),
                segment(SupportType.roller, Tool.roller, s.toolRoller),
                segment(SupportType.fixed, Tool.fixed, s.toolFixed),
              ],
              selected: {support.type},
              onSelectionChanged:
                  (v) => controller.updateSupport(
                    support.copyWith(type: v.single),
                  ),
            ),
            NumberField(
              width: width,
              key: ValueKey('pos-$id'),
              label: '${s.position} x',
              value: toL(support.x),
              unit: u.length.symbol,
              validator: onBeam,
              onChanged:
                  (v) =>
                      controller.updateSupport(support.copyWith(x: fromL(v))),
            ),
          ],
        ],
      );
    }

    switch (p.loadById(id)) {
      case final PointLoad load:
        const directions = [-90.0, 90.0, 0.0, 180.0, -45.0, -135.0];
        final picker = Directionality(
          textDirection: TextDirection.ltr,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final a in directions)
                Padding(
                  padding: const EdgeInsets.only(right: 4),
                  child: IconButton.filledTonal(
                    isSelected:
                        normaliseAngle(load.angleDeg) == normaliseAngle(a),
                    visualDensity: VisualDensity.compact,
                    onPressed:
                        () => controller.updateLoad(load.copyWith(angleDeg: a)),
                    icon: DirectionGlyph(a),
                  ),
                ),
              const SizedBox(width: 6),
              NumberField(
                key: ValueKey('ang-$id'),
                label: s.angle,
                value: normaliseAngle(load.angleDeg),
                unit: '°',
                width: compact ? 84 : 96,
                allowNegative: true,
                onChanged:
                    (v) => controller.updateLoad(
                      load.copyWith(angleDeg: normaliseAngle(v)),
                    ),
              ),
            ],
          ),
        );
        return _Props(
          title: '${s.loadProps} ${labels.loadName(id)}',
          short: labels.loadName(id),
          icon: Tool.pointLoad,
          help: s.angleHelp,
          groups: [
            [
              NumberField(
                width: width,
                key: ValueKey('mag-$id'),
                label: s.magnitude,
                value: u.toDisplay(load.magnitude, Dimension.force),
                unit: u.force.symbol,
                validator: positive,
                onChanged:
                    (v) => controller.updateLoad(
                      load.copyWith(
                        magnitude: u.fromDisplay(v, Dimension.force),
                      ),
                    ),
              ),
              NumberField(
                width: width,
                key: ValueKey('pos-$id'),
                label: '${s.position} x',
                value: toL(load.x),
                unit: u.length.symbol,
                validator: onBeam,
                onChanged:
                    (v) => controller.updateLoad(load.copyWith(x: fromL(v))),
              ),
            ],
            [
              if (compact)
                picker
              else
                Row(
                  children: [
                    Text(
                      '${s.direction}:  ',
                      style: Theme.of(context).textTheme.labelLarge,
                    ),
                    Expanded(
                      child: SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: picker,
                      ),
                    ),
                  ],
                ),
            ],
          ],
        );

      case final DistributedLoad load:
        double toW(double si) => u.toDisplay(si, Dimension.intensity);
        double fromW(double v) => u.fromDisplay(v, Dimension.intensity);
        final wUnit = u.intensity.symbol;
        String? nonNegative(double v) => v >= 0 ? null : s.mustBePositive;
        void update(DistributedLoad next) => controller.updateAnyLoad(next);
        final name = labels.loadName(id);
        return _Props(
          title: '${load.isUniform ? s.udlProps : s.uvlProps}  $name',
          short: name,
          icon: load.isUniform ? Tool.udl : Tool.uvl,
          // The single force it is equivalent to, and where it acts.
          note:
              '$name = ${Num.compact(u.toDisplay(load.resultant, Dimension.force))} ${u.force.symbol}'
              '   @  x̄ = ${Num.compact(toL(load.centroid))} ${u.length.symbol}',
          groups: [
            [
              NumberField(
                width: width,
                key: ValueKey('from-$id'),
                label: s.startX,
                value: toL(load.x),
                unit: u.length.symbol,
                validator:
                    (v) =>
                        onBeam(v) ??
                        (fromL(v) < load.x2 - 1e-9
                            ? null
                            : '< ${Num.compact(toL(load.x2))}'),
                onChanged: (v) => update(load.copyWith(x: fromL(v))),
              ),
              NumberField(
                width: width,
                key: ValueKey('to-$id'),
                label: s.endX,
                value: toL(load.x2),
                unit: u.length.symbol,
                validator:
                    (v) =>
                        onBeam(v) ??
                        (fromL(v) > load.x + 1e-9
                            ? null
                            : '> ${Num.compact(toL(load.x))}'),
                onChanged: (v) => update(load.copyWith(x2: fromL(v))),
              ),
              if (load.isUniform)
                NumberField(
                  width: width,
                  key: ValueKey('w-$id'),
                  label: s.intensity,
                  value: toW(load.w1),
                  unit: wUnit,
                  validator: positive,
                  onChanged:
                      (v) => update(load.copyWith(w1: fromW(v), w2: fromW(v))),
                ),
            ],
            if (!load.isUniform)
              [
                NumberField(
                  width: width,
                  key: ValueKey('w1-$id'),
                  label: s.intensityStart,
                  value: toW(load.w1),
                  unit: wUnit,
                  validator:
                      (v) =>
                          nonNegative(v) ??
                          (v > 0 || load.w2 > 0 ? null : s.mustBePositive),
                  onChanged: (v) => update(load.copyWith(w1: fromW(v))),
                ),
                NumberField(
                  width: width,
                  key: ValueKey('w2-$id'),
                  label: s.intensityEnd,
                  value: toW(load.w2),
                  unit: wUnit,
                  validator:
                      (v) =>
                          nonNegative(v) ??
                          (v > 0 || load.w1 > 0 ? null : s.mustBePositive),
                  onChanged: (v) => update(load.copyWith(w2: fromW(v))),
                ),
              ],
            [
              FilterChip(
                key: ValueKey('uniform-$id'),
                label: Text(s.uniformToggle),
                selected: load.isUniform,
                onSelected: (on) {
                  final w = load.w1 > load.w2 ? load.w1 : load.w2;
                  update(load.copyWith(w1: on ? w : 0, w2: w));
                },
              ),
              SegmentedButton<bool>(
                showSelectedIcon: false,
                style: const ButtonStyle(visualDensity: VisualDensity.compact),
                segments: [
                  choice(false, '↓', s.loadDown),
                  choice(true, '↑', s.loadUp),
                ],
                selected: {load.upward},
                onSelectionChanged:
                    (v) => update(load.copyWith(upward: v.single)),
              ),
            ],
          ],
        );

      case final PointMoment load:
        return _Props(
          title: '${s.momentProps}  ${labels.loadName(id)}',
          short: labels.loadName(id),
          icon: Tool.moment,
          groups: [
            [
              NumberField(
                width: width,
                key: ValueKey('mag-$id'),
                label: s.magnitude,
                value: u.toDisplay(load.magnitude, Dimension.moment),
                unit: u.moment.symbol,
                validator: positive,
                onChanged:
                    (v) => controller.updateAnyLoad(
                      load.copyWith(
                        magnitude: u.fromDisplay(v, Dimension.moment),
                      ),
                    ),
              ),
              NumberField(
                width: width,
                key: ValueKey('pos-$id'),
                label: '${s.position} x',
                value: toL(load.x),
                unit: u.length.symbol,
                validator: onBeam,
                onChanged:
                    (v) => controller.updateAnyLoad(load.copyWith(x: fromL(v))),
              ),
              SegmentedButton<bool>(
                showSelectedIcon: false,
                style: const ButtonStyle(visualDensity: VisualDensity.compact),
                segments: [choice(true, '↺', s.ccw), choice(false, '↻', s.cw)],
                selected: {load.counterClockwise},
                onSelectionChanged:
                    (v) => controller.updateAnyLoad(
                      load.copyWith(counterClockwise: v.single),
                    ),
              ),
            ],
          ],
        );

      case null:
        return null;
    }
  }
}

/// What the panel shows for one kind of element, laid out upright or
/// sideways by [PropertiesPanel.build].
class _Props {
  const _Props({
    required this.title,
    required this.short,
    required this.icon,
    required this.groups,
    this.note,
    this.help,
  });

  /// The full heading, upright.
  final String title;

  /// The element's name alone (W1, A, Beam), sideways.
  final String short;
  final Tool icon;

  /// Controls in rows: a row each upright, all in one line sideways.
  final List<List<Widget>> groups;

  /// A result worth seeing in both layouts (a resultant and its x̄).
  final String? note;

  /// A how-to line, upright only.
  final String? help;
}
