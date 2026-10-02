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
