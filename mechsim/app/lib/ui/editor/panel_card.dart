import 'package:flutter/material.dart';

import '../widgets/tool_icons.dart';

/// One rounded card of the sideways editor's side panel: an icon and a
/// title, optional actions, then the card's content.
class PanelCard extends StatelessWidget {
  const PanelCard({
    super.key,
    required this.icon,
    required this.title,
    required this.children,
    this.actions = const [],
  });

  final Widget icon;
  final String title;
  final List<Widget> actions;
  final List<Widget> children;

  /// A 32 px icon button for card headers.
  static final smallButton = IconButton.styleFrom(
    minimumSize: const Size(32, 32),
    padding: const EdgeInsets.all(6),
    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
  );

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(8, 2, 4, 8),
      decoration: BoxDecoration(
        color: scheme.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: scheme.outlineVariant.withValues(alpha: 0.6)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            height: 32,
            child: Row(
              children: [
                IconTheme(
                  data: IconThemeData(color: scheme.onSurface, size: 18),
                  child: icon,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 13.5,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                ...actions,
              ],
            ),
          ),
          const SizedBox(height: 4),
          Padding(
            padding: const EdgeInsetsDirectional.only(end: 4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (var i = 0; i < children.length; i++) ...[
                  if (i > 0) const SizedBox(height: 8),
                  children[i],
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// A load's direction as a drop-down of the usual six, as in the side
/// panel (any other angle is typed in the θ field beside it).
class DirectionDropdown extends StatelessWidget {
  const DirectionDropdown({
    super.key,
    required this.angleDeg,
    required this.onChanged,
    required this.label,
  });

  static const angles = [-90.0, 90.0, 0.0, 180.0, -45.0, -135.0];

  final double angleDeg;
  final ValueChanged<double> onChanged;
  final String label;

  @override
  Widget build(BuildContext context) {
    final current = angles.where((a) => a == angleDeg).firstOrNull;
    String degrees(double a) => '${a.round()}°'.replaceFirst('-', '−');
    return Directionality(
      textDirection: TextDirection.ltr,
      child: DropdownButtonFormField<double>(
        key: ValueKey('direction-$angleDeg'),
        initialValue: current,
        isExpanded: true,
        isDense: true,
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
          isDense: true,
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 8,
            vertical: 8,
          ),
        ),
        hint: Text(degrees(angleDeg)),
        // The field is narrow and θ sits beside it: the arrow says enough.
        selectedItemBuilder:
            (_) => [
              for (final a in angles)
                Align(
                  alignment: Alignment.centerLeft,
                  child: DirectionGlyph(a, size: 18),
                ),
            ],
        items: [
          for (final a in angles)
            DropdownMenuItem(
              value: a,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  DirectionGlyph(a, size: 16),
                  const SizedBox(width: 4),
                  Flexible(
                    child: Text(
                      degrees(a),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
        ],
        onChanged: (v) {
          if (v != null) onChanged(v);
        },
      ),
    );
  }
}
