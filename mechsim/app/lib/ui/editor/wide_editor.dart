import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../i18n/strings.dart';
import '../../state/app_state.dart';
import '../../state/editor_controller.dart';
import '../widgets/number_field.dart';
import '../widgets/tool_icons.dart';
import 'panel_card.dart';
import 'properties_panel.dart';

/// The drawing screen sideways: a title bar, the tools listed down one
/// side with their names, the sheet in the middle, a panel of cards down
/// the other side (the selection or the next load's settings, whether the
/// beam can be solved, display switches), and a bottom bar with the
/// problem, the beam's length and ANALYZE.
class WideEditor extends StatefulWidget {
  const WideEditor({
    super.key,
    required this.controller,
    required this.canvas,
    required this.onSave,
    required this.onAnalyze,
    required this.onMessage,
  });

  final EditorController controller;
  final Widget canvas;
  final VoidCallback onSave;

  /// Null until there is a beam to analyse.
  final VoidCallback? onAnalyze;
  final ValueChanged<String> onMessage;

  static const railWidth = 108.0;
  static const panelWidth = 200.0;

  /// Bar buttons: 36 px with a 20 px icon, so the bars stay thin.
  static final barButton = IconButton.styleFrom(
    minimumSize: const Size(36, 36),
    padding: const EdgeInsets.all(8),
    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    iconSize: 20,
  );

  @override
  State<WideEditor> createState() => _WideEditorState();
}

class _WideEditorState extends State<WideEditor> {
  bool _panel = true;

  EditorController get c => widget.controller;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final s = AppScope.of(context).s;
    return Scaffold(
      backgroundColor: scheme.surface,
      drawer: _Drawer(controller: c, onSave: widget.onSave),
      body: SafeArea(
        child: Column(
          children: [
            _TopBar(
              controller: c,
              panel: _panel,
              onTogglePanel: () => setState(() => _panel = !_panel),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(4, 0, 4, 4),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    SizedBox(
                      width: WideEditor.railWidth,
                      child: _ToolRail(controller: c),
                    ),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: scheme.outlineVariant),
                        ),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(11),
                          child: Stack(
                            children: [
                              Positioned.fill(child: widget.canvas),
                              // With the panel hidden its hint moves onto
                              // the sheet.
                              if (!_panel)
                                PositionedDirectional(
                                  top: 6,
                                  start: 8,
                                  end: 8,
                                  child: IgnorePointer(
                                    child: Align(
                                      alignment: AlignmentDirectional.topStart,
                                      child: _HintChip(text: _hint(s, c)),
                                    ),
                                  ),
                                ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    if (_panel) ...[
                      const SizedBox(width: 4),
                      SizedBox(
                        width: WideEditor.panelWidth,
                        child: _SidePanel(
                          controller: c,
                          onMessage: widget.onMessage,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
            _BottomBar(
              controller: c,
              onSave: widget.onSave,
              onAnalyze: widget.onAnalyze,
            ),
          ],
        ),
      ),
    );
  }
}

String _hint(S s, EditorController c) =>
    c.problem.hasBeam ? s.hintFor(c.tool.name) : s.hintEmpty;

class _HintChip extends StatelessWidget {
  const _HintChip({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: theme.colorScheme.secondaryContainer.withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        text,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: theme.textTheme.bodySmall,
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.controller,
    required this.panel,
    required this.onTogglePanel,
  });

  final EditorController controller;
  final bool panel;
  final VoidCallback onTogglePanel;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final scheme = Theme.of(context).colorScheme;
    final b = WideEditor.barButton;
    return SizedBox(
      height: 38,
      child: Row(
        children: [
          Builder(
            builder:
                (context) => IconButton(
                  style: b,
                  tooltip:
                      MaterialLocalizations.of(context).openAppDrawerTooltip,
                  onPressed: () => Scaffold.of(context).openDrawer(),
                  icon: const Icon(Icons.menu),
                ),
          ),
          SizedBox(
            height: 24,
            child: VerticalDivider(width: 12, color: scheme.outlineVariant),
          ),
          Icon(Icons.architecture, color: scheme.primary, size: 20),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              'MechSim 2D',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800),
            ),
          ),
          const Spacer(),
          IconButton(
            style: b,
            tooltip: s.undo,
            onPressed: controller.canUndo ? controller.undo : null,
            icon: const Icon(Icons.undo),
          ),
          IconButton(
            style: b,
            tooltip: s.redo,
            onPressed: controller.canRedo ? controller.redo : null,
            icon: const Icon(Icons.redo),
          ),
          IconButton(
            style: b,
            key: const ValueKey('toggle-panel'),
            tooltip: s.sidePanel,
            isSelected: panel,
            onPressed: onTogglePanel,
            icon: const Icon(Icons.view_sidebar_outlined),
            selectedIcon: const Icon(Icons.view_sidebar),
          ),
          SizedBox(
            height: 24,
            child: VerticalDivider(width: 12, color: scheme.outlineVariant),
          ),
          PopupMenuButton<String>(
            style: b,
            iconSize: 20,
            onSelected: (v) {
              if (v == 'fit') controller.requestFit();
              if (v == 'clear') controller.clear();
            },
            itemBuilder:
                (_) => [
                  PopupMenuItem(value: 'fit', child: Text(s.fitView)),
                  PopupMenuItem(value: 'clear', child: Text(s.clearAll)),
                ],
          ),
        ],
      ),
    );
  }
}

class _Drawer extends StatelessWidget {
  const _Drawer({required this.controller, required this.onSave});

  final EditorController controller;
  final VoidCallback onSave;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    void then(VoidCallback action) {
      Navigator.pop(context); // the drawer
      action();
    }

    return Drawer(
      width: 280,
      child: SafeArea(
        child: ListView(
          children: [
            ListTile(
              leading: Icon(
                Icons.architecture,
                color: Theme.of(context).colorScheme.primary,
              ),
              title: Text(
                'MechSim 2D',
                style: Theme.of(
                  context,
                ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
              ),
            ),
            const Divider(),
            if (Navigator.canPop(context))
              ListTile(
                leading: const Icon(Icons.home_outlined),
                title: Text(s.navHome),
                onTap: () => then(() => Navigator.maybePop(context)),
              ),
            ListTile(
              leading: const Icon(Icons.add_box_outlined),
              title: Text(s.newProblem),
              onTap: () => then(controller.clear),
            ),
            ListTile(
              leading: const Icon(Icons.save_outlined),
              title: Text(s.save),
              onTap: () => then(onSave),
            ),
            ListTile(
              leading: const Icon(Icons.fit_screen_outlined),
              title: Text(s.fitView),
              onTap: () => then(controller.requestFit),
            ),
          ],
        ),
      ),
    );
  }
}

/// The tools with their names, one per line. Supports and distributed
/// loads are one entry each; which kind is chosen in the side panel.
class _ToolRail extends StatelessWidget {
  const _ToolRail({required this.controller});

  final EditorController controller;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final scheme = Theme.of(context).colorScheme;
    final tool = controller.tool;
    final items = <(String, Tool, bool, VoidCallback)>[
      (
        s.toolSelect,
        Tool.select,
        tool == Tool.select,
        () => controller.setTool(Tool.select),
      ),
      (
        s.toolPointLoad,
        Tool.pointLoad,
        tool == Tool.pointLoad,
        () => controller.setTool(Tool.pointLoad),
      ),
      (
        s.toolDistributed,
        tool.isDistributed ? tool : controller.lastDistributed,
        tool.isDistributed,
        () => controller.setTool(controller.lastDistributed),
      ),
      (
        s.toolMoment,
        Tool.moment,
        tool == Tool.moment,
        () => controller.setTool(Tool.moment),
      ),
      (
        s.toolBeam,
        Tool.beam,
        tool == Tool.beam,
        () => controller.setTool(Tool.beam),
      ),
      (
        s.toolSupport,
        tool.isSupport ? tool : controller.lastSupport,
        tool.isSupport,
        () => controller.setTool(controller.lastSupport),
      ),
      (
        s.toolDimension,
        Tool.dimension,
        controller.showDimensions,
        () => controller.setTool(Tool.dimension),
      ),
    ];
    return Column(
      children: [
        for (final (label, icon, active, onTap) in items)
          Expanded(
            child: Padding(
              key: ValueKey('tool-$label'),
              padding: const EdgeInsets.symmetric(vertical: 1.5),
              child: Material(
                color: active ? scheme.primary : Colors.transparent,
                borderRadius: BorderRadius.circular(10),
                child: InkWell(
                  borderRadius: BorderRadius.circular(10),
                  onTap: onTap,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    child: Row(
                      children: [
                        ToolIcon(
                          icon,
                          size: 18,
                          color:
                              active
                                  ? scheme.onPrimary
                                  : scheme.onSurfaceVariant,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: FittedBox(
                            fit: BoxFit.scaleDown,
                            alignment: AlignmentDirectional.centerStart,
                            child: Text(
                              label,
                              maxLines: 1,
                              style: TextStyle(
                                fontSize: 12.5,
                                fontWeight:
                                    active ? FontWeight.w800 : FontWeight.w600,
                                color:
                                    active
                                        ? scheme.onPrimary
                                        : scheme.onSurface,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _SidePanel extends StatelessWidget {
  const _SidePanel({required this.controller, required this.onMessage});

  final EditorController controller;
  final ValueChanged<String> onMessage;

  @override
  Widget build(BuildContext context) {
    // A handful of cards: built all at once so each can be scrolled to.
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (controller.selected != null)
            PropertiesPanel(
              controller: controller,
              onMessage: onMessage,
              card: true,
            )
          else
            _NextCard(controller: controller),
          const SizedBox(height: 4),
          _StatusCard(controller: controller),
          const SizedBox(height: 4),
          _DisplayCard(controller: controller),
        ],
      ),
    );
  }
}

/// With nothing selected: what the active tool will place, set before
/// tapping the beam, or what to do next.
class _NextCard extends StatelessWidget {
  const _NextCard({required this.controller});

  final EditorController controller;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final u = app.units;
    final d = controller.defaults;
    final tool = controller.tool;
    const w = PropertiesPanel.cardFieldWidth;
    final hint = Text(
      _hint(s, controller),
      style: Theme.of(context).textTheme.bodySmall,
    );
    ButtonSegment<T> choice<T>(T value, String arrow, String words) =>
        ButtonSegment(value: value, label: Text(arrow), tooltip: words);

    String? positive(double v) => v > 0 ? null : s.mustBePositive;

    switch (tool) {
      case Tool.pointLoad:
        return PanelCard(
          key: const ValueKey('next-pointLoad'),
          icon: const ToolIcon(Tool.pointLoad),
          title: s.loadSettings,
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 10,
              children: [
                NumberField(
                  key: const ValueKey('next-magnitude'),
                  label: s.magnitude,
                  value: u.toDisplay(d.pointMagnitude, Dimension.force),
                  unit: u.force.symbol,
                  width: w,
                  validator: positive,
                  onChanged:
                      (v) => controller.updateDefaults(
                        (d) =>
                            d.pointMagnitude = u.fromDisplay(
                              v,
                              Dimension.force,
                            ),
                      ),
                ),
                SizedBox(
                  width: w,
                  child: DirectionDropdown(
                    label: s.direction,
                    angleDeg: d.pointAngle,
                    onChanged:
                        (a) =>
                            controller.updateDefaults((d) => d.pointAngle = a),
                  ),
                ),
              ],
            ),
            hint,
          ],
        );
      case Tool.udl || Tool.uvl:
        return PanelCard(
          key: const ValueKey('next-distributed'),
          icon: ToolIcon(tool),
          title: s.loadSettings,
          children: [
            SegmentedButton<Tool>(
              showSelectedIcon: false,
              expandedInsets: EdgeInsets.zero,
              style: const ButtonStyle(visualDensity: VisualDensity.compact),
              segments: [
                ButtonSegment(value: Tool.udl, label: Text(s.typeUniform)),
                ButtonSegment(value: Tool.uvl, label: Text(s.typeVarying)),
              ],
              selected: {tool},
              onSelectionChanged: (v) => controller.setTool(v.single),
            ),
            Wrap(
              spacing: 8,
              runSpacing: 10,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                NumberField(
                  key: const ValueKey('next-intensity'),
                  label: s.intensity,
                  value: u.toDisplay(d.intensity, Dimension.intensity),
                  unit: u.intensity.symbol,
                  width: w,
                  validator: positive,
                  onChanged:
                      (v) => controller.updateDefaults(
                        (d) =>
                            d.intensity = u.fromDisplay(v, Dimension.intensity),
                      ),
                ),
                SegmentedButton<bool>(
                  showSelectedIcon: false,
                  style: const ButtonStyle(
                    visualDensity: VisualDensity.compact,
                  ),
                  segments: [
                    choice(false, '↓', s.loadDown),
                    choice(true, '↑', s.loadUp),
                  ],
                  selected: {d.distributedUpward},
                  onSelectionChanged:
                      (v) => controller.updateDefaults(
                        (d) => d.distributedUpward = v.single,
                      ),
                ),
              ],
            ),
            hint,
          ],
        );
      case Tool.moment:
        return PanelCard(
          key: const ValueKey('next-moment'),
          icon: const ToolIcon(Tool.moment),
          title: s.loadSettings,
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 10,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                NumberField(
                  key: const ValueKey('next-moment-value'),
                  label: s.magnitude,
                  value: u.toDisplay(d.moment, Dimension.moment),
                  unit: u.moment.symbol,
                  width: w,
                  validator: positive,
                  onChanged:
                      (v) => controller.updateDefaults(
                        (d) => d.moment = u.fromDisplay(v, Dimension.moment),
                      ),
                ),
                SegmentedButton<bool>(
                  showSelectedIcon: false,
                  style: const ButtonStyle(
                    visualDensity: VisualDensity.compact,
                  ),
                  segments: [
                    choice(true, '↺', s.ccw),
                    choice(false, '↻', s.cw),
                  ],
                  selected: {d.counterClockwise},
                  onSelectionChanged:
                      (v) => controller.updateDefaults(
                        (d) => d.counterClockwise = v.single,
                      ),
                ),
              ],
            ),
            hint,
          ],
        );
      case Tool.pin || Tool.roller || Tool.fixed:
        ButtonSegment<Tool> type(Tool t, String label) => ButtonSegment(
          value: t,
          tooltip: label,
          icon: ToolIcon(t, size: 22),
        );
        return PanelCard(
          key: const ValueKey('next-support'),
          icon: ToolIcon(tool),
          title: s.supportProps,
          children: [
            SegmentedButton<Tool>(
              showSelectedIcon: false,
              expandedInsets: EdgeInsets.zero,
              segments: [
                type(Tool.pin, s.toolPin),
                type(Tool.roller, s.toolRoller),
                type(Tool.fixed, s.toolFixed),
              ],
              selected: {tool},
              onSelectionChanged: (v) => controller.setTool(v.single),
            ),
            Text(
              switch (tool) {
                Tool.pin => s.toolPin,
                Tool.roller => s.toolRoller,
                _ => s.toolFixed,
              },
              textAlign: TextAlign.center,
              style: Theme.of(
                context,
              ).textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w800),
            ),
            hint,
          ],
        );
      case Tool.select || Tool.beam || Tool.dimension || Tool.delete:
        return PanelCard(
          key: const ValueKey('next-hint'),
          icon: ToolIcon(tool == Tool.dimension ? Tool.select : tool),
          title: switch (tool) {
            Tool.beam => s.toolBeam,
            Tool.delete => s.toolDelete,
            _ => s.toolSelect,
          },
          children: [hint],
        );
    }
  }
}

/// Whether the beam as drawn can be solved, and if not, why.
class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.controller});

  final EditorController controller;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final t = Texts.of(app.settings.lang);
    final report = StaticsSolver.solve(controller.problem).stability;
    final ok = report.isDeterminate;
    final message =
        ok
            ? s.readyToAnalyze
            : t.stabilityMessage(report.reason, report.unknowns, report.degree);
    final advice = ok ? '' : t.stabilityAdvice(report.reason);
    final color = ok ? const Color(0xFF2EB67D) : const Color(0xFFF2A93B);
    return PanelCard(
      key: const ValueKey('status-card'),
      icon: const ToolIcon(Tool.beam),
      title: s.beamStatus,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              ok ? Icons.check_circle : Icons.warning_amber_rounded,
              color: color,
              size: 20,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                [message, if (advice.isNotEmpty) advice].join('\n'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _DisplayCard extends StatelessWidget {
  const _DisplayCard({required this.controller});

  final EditorController controller;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    Widget row(String key, String label, bool value, ValueChanged<bool> f) =>
        SizedBox(
          height: 28,
          child: Row(
            children: [
              Expanded(
                child: Text(label, style: const TextStyle(fontSize: 13)),
              ),
              Transform.scale(
                scale: 0.7,
                child: Switch(
                  key: ValueKey('switch-$key'),
                  value: value,
                  onChanged: f,
                ),
              ),
            ],
          ),
        );
    return PanelCard(
      icon: const Icon(Icons.visibility_outlined),
      title: s.display,
      children: [
        row('grid', s.grid, controller.showGrid, controller.setShowGrid),
        row('snap', s.snapLabel, controller.snap, controller.setSnap),
        row(
          'dimensions',
          s.dimensions,
          controller.showDimensions,
          controller.setShowDimensions,
        ),
      ],
    );
  }
}

class _BottomBar extends StatelessWidget {
  const _BottomBar({
    required this.controller,
    required this.onSave,
    required this.onAnalyze,
  });

  final EditorController controller;
  final VoidCallback onSave;
  final VoidCallback? onAnalyze;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final u = app.units;
    final scheme = Theme.of(context).colorScheme;
    final p = controller.problem;
    return Container(
      height: 44,
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        border: Border(top: BorderSide(color: scheme.outlineVariant)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Row(
        children: [
          Flexible(
            child: PopupMenuButton<String>(
              key: const ValueKey('project-menu'),
              tooltip: s.projectMenu,
              onSelected: (v) {
                if (v == 'new') controller.clear();
                if (v == 'save') onSave();
                if (v == 'fit') controller.requestFit();
              },
              itemBuilder:
                  (_) => [
                    PopupMenuItem(value: 'new', child: Text(s.newProblem)),
                    PopupMenuItem(value: 'save', child: Text(s.save)),
                    PopupMenuItem(value: 'fit', child: Text(s.fitView)),
                  ],
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.description_outlined, size: 18),
                    const SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        controller.name ?? s.untitled,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    const Icon(Icons.arrow_drop_down, size: 20),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),
          const ToolIcon(Tool.dimension, size: 18),
          const SizedBox(width: 6),
          NumberField(
            key: const ValueKey('bottom-length'),
            dense: true,
            label: s.length,
            value: p.hasBeam ? u.toDisplay(p.length, Dimension.length) : 0,
            unit: u.length.symbol,
            width: 104,
            validator: (v) => v > 0 ? null : s.mustBePositive,
            onChanged: (v) {
              final length = u.fromDisplay(v, Dimension.length);
              // Typing a length on an empty sheet draws the beam.
              p.hasBeam
                  ? controller.setLength(length)
                  : controller.setBeam(length);
            },
          ),
          const SizedBox(width: 8),
          FilledButton.icon(
            key: const ValueKey('analyze'),
            onPressed: onAnalyze,
            style: FilledButton.styleFrom(
              minimumSize: const Size(112, 34),
              padding: const EdgeInsets.symmetric(horizontal: 14),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(9),
              ),
            ),
            icon: const Icon(Icons.play_arrow_rounded, size: 18),
            label: Text(
              s.analyze,
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w900,
                letterSpacing: 1,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
