import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../state/app_state.dart';
import '../../state/editor_controller.dart';
import '../widgets/number_field.dart';
import '../widgets/tool_icons.dart';

/// Exact values for the selected element: the beam's length, a support's
/// type and position, a load's magnitude, position and direction.
class PropertiesPanel extends StatelessWidget {
  const PropertiesPanel({
    super.key,
    required this.controller,
    required this.onMessage,
  });

  final EditorController controller;
  final ValueChanged<String> onMessage;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final u = app.units;
    final p = controller.problem;
    final id = controller.selected!;
    final scheme = Theme.of(context).colorScheme;
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

    Widget header(String title, {VoidCallback? onDelete}) => Row(
      children: [
        Expanded(
          child: Text(
            title,
            style: Theme.of(
              context,
            ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
          ),
        ),
        if (onDelete != null)
          IconButton(
            visualDensity: VisualDensity.compact,
            tooltip: s.delete,
            onPressed: onDelete,
            icon: const Icon(Icons.delete_outline),
          ),
        IconButton(
          visualDensity: VisualDensity.compact,
          onPressed: () => controller.select(null),
          icon: const Icon(Icons.close),
        ),
      ],
    );

    Widget content;
    if (id == 'beam') {
      content = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          header(s.beamProps, onDelete: () => controller.delete('beam')),
          NumberField(
            key: const ValueKey('beam-length'),
            label: s.length,
            value: toL(p.length),
            unit: u.length.symbol,
            validator: positive,
            onChanged: (v) => controller.setLength(fromL(v)),
          ),
        ],
      );
    } else if (p.supportById(id) case final support?) {
      content = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          header(
            '${s.supportProps} ${labels.pointOf(id)}',
            onDelete: () => controller.delete(id),
          ),
          Wrap(
            spacing: 10,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SegmentedButton<SupportType>(
                showSelectedIcon: false,
                style: const ButtonStyle(visualDensity: VisualDensity.compact),
                segments: [
                  ButtonSegment(
                    value: SupportType.pin,
                    label: Text(s.toolPin),
                    icon: const ToolIcon(Tool.pin, size: 18),
                  ),
                  ButtonSegment(
                    value: SupportType.roller,
                    label: Text(s.toolRoller),
                    icon: const ToolIcon(Tool.roller, size: 18),
                  ),
                  ButtonSegment(
                    value: SupportType.fixed,
                    label: Text(s.toolFixed),
                    icon: const ToolIcon(Tool.fixed, size: 18),
                  ),
                ],
                selected: {support.type},
                onSelectionChanged:
                    (v) => controller.updateSupport(
                      support.copyWith(type: v.single),
                    ),
              ),
              NumberField(
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
          ),
        ],
      );
    } else if (p.loadById(id) case final PointLoad load) {
      const directions = [-90.0, 90.0, 0.0, 180.0, -45.0, -135.0];
      content = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          header(
            '${s.loadProps} ${labels.loadName(id)}',
            onDelete: () => controller.delete(id),
          ),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              NumberField(
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
                key: ValueKey('pos-$id'),
                label: '${s.position} x',
                value: toL(load.x),
                unit: u.length.symbol,
                validator: onBeam,
                onChanged:
                    (v) => controller.updateLoad(load.copyWith(x: fromL(v))),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Text(
                '${s.direction}:  ',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              Expanded(
                child: Directionality(
                  textDirection: TextDirection.ltr,
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: [
                        for (final a in directions)
                          Padding(
                            padding: const EdgeInsets.only(right: 4),
                            child: IconButton.filledTonal(
                              isSelected:
                                  normaliseAngle(load.angleDeg) ==
                                  normaliseAngle(a),
                              visualDensity: VisualDensity.compact,
                              onPressed:
                                  () => controller.updateLoad(
                                    load.copyWith(angleDeg: a),
                                  ),
                              icon: DirectionGlyph(a),
                            ),
                          ),
                        const SizedBox(width: 6),
                        NumberField(
                          key: ValueKey('ang-$id'),
                          label: s.angle,
                          value: normaliseAngle(load.angleDeg),
                          unit: '°',
                          width: 96,
                          allowNegative: true,
                          onChanged:
                              (v) => controller.updateLoad(
                                load.copyWith(angleDeg: normaliseAngle(v)),
                              ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              s.angleHelp,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      );
    } else if (p.loadById(id) case final DistributedLoad load) {
      double toW(double si) => u.toDisplay(si, Dimension.intensity);
      double fromW(double v) => u.fromDisplay(v, Dimension.intensity);
      final wUnit = u.intensity.symbol;
      String? nonNegative(double v) => v >= 0 ? null : s.mustBePositive;
      void update(DistributedLoad next) => controller.updateAnyLoad(next);
      content = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          header(
            '${load.isUniform ? s.udlProps : s.uvlProps}  ${labels.loadName(id)}',
            onDelete: () => controller.delete(id),
          ),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              NumberField(
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
                  key: ValueKey('w-$id'),
                  label: s.intensity,
                  value: toW(load.w1),
                  unit: wUnit,
                  validator: positive,
                  onChanged:
                      (v) => update(load.copyWith(w1: fromW(v), w2: fromW(v))),
                ),
            ],
          ),
          if (!load.isUniform) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                NumberField(
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
            ),
          ],
          const SizedBox(height: 8),
          Wrap(
            spacing: 10,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
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
                  ButtonSegment(value: false, label: Text(s.loadDown)),
                  ButtonSegment(value: true, label: Text(s.loadUp)),
                ],
                selected: {load.upward},
                onSelectionChanged:
                    (v) => update(load.copyWith(upward: v.single)),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Directionality(
              textDirection: TextDirection.ltr,
              child: Text(
                // The single force it is equivalent to, and where it acts.
                '${labels.loadName(id)} = ${Num.compact(u.toDisplay(load.resultant, Dimension.force))} ${u.force.symbol}'
                '   @  x̄ = ${Num.compact(toL(load.centroid))} ${u.length.symbol}',
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w700),
              ),
            ),
          ),
        ],
      );
    } else if (p.loadById(id) case final PointMoment load) {
      content = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          header(
            '${s.momentProps}  ${labels.loadName(id)}',
            onDelete: () => controller.delete(id),
          ),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              NumberField(
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
                segments: [
                  ButtonSegment(value: true, label: Text(s.ccw)),
                  ButtonSegment(value: false, label: Text(s.cw)),
                ],
                selected: {load.counterClockwise},
                onSelectionChanged:
                    (v) => controller.updateAnyLoad(
                      load.copyWith(counterClockwise: v.single),
                    ),
              ),
            ],
          ),
        ],
      );
    } else {
      return const SizedBox.shrink();
    }

    return Material(
      color: scheme.surfaceContainerLow,
      child: Container(
        width: double.infinity,
        decoration: BoxDecoration(
          border: Border(top: BorderSide(color: scheme.outlineVariant)),
        ),
        padding: const EdgeInsets.fromLTRB(14, 4, 6, 10),
        child: content,
      ),
    );
  }
}
