import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/palette.dart';
import '../../state/app_state.dart';
import '../../state/highlight_controller.dart';
import 'math_view.dart';

/// One step of the solution: its equations with tappable terms, why it is
/// done this way, and an "Explain" button for the longer answer.
class StepCard extends StatefulWidget {
  const StepCard({
    super.key,
    required this.step,
    required this.index,
    required this.highlights,
    this.emphasised = false,
    this.initiallyExplained = false,
  });

  final SolutionStep step;
  final int index;
  final HighlightController highlights;
  final bool emphasised;
  final bool initiallyExplained;

  @override
  State<StepCard> createState() => _StepCardState();
}

class _StepCardState extends State<StepCard> {
  MathToken? _selected;
  late bool _explained = widget.initiallyExplained;

  @override
  void didUpdateWidget(StepCard old) {
    super.didUpdateWidget(old);
    if (old.step != widget.step) {
      _selected = null;
      _explained = widget.initiallyExplained;
    }
  }

  void _tapToken(MathToken t) {
    setState(() => _selected = identical(_selected, t) ? null : t);
    if (t.highlights.isNotEmpty) {
      widget.highlights.show(t.highlights, source: t);
    } else {
      widget.highlights.clear();
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final step = widget.step;
    final colors = MechColors.of(context);
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final unsolvable = step.kind == StepKind.unsolvable;

    Widget prose(String text, {TextStyle? style}) => Text(
      text,
      style: style ?? theme.textTheme.bodyMedium?.copyWith(height: 1.45),
    );

    return Card(
      elevation: widget.emphasised ? 3 : 0.5,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(
          color: widget.emphasised ? colors.highlight : scheme.outlineVariant,
          width: widget.emphasised ? 2 : 1,
        ),
      ),
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            InkWell(
              borderRadius: BorderRadius.circular(8),
              onTap:
                  step.highlights.isEmpty
                      ? null
                      : () =>
                          widget.highlights.show(step.highlights, source: step),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 14,
                    backgroundColor:
                        unsolvable
                            ? scheme.errorContainer
                            : scheme.primaryContainer,
                    child:
                        unsolvable
                            ? Icon(
                              Icons.warning_amber,
                              size: 16,
                              color: scheme.onErrorContainer,
                            )
                            : Text(
                              '${widget.index + 1}',
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w800,
                                color: scheme.onPrimaryContainer,
                              ),
                            ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        MathText(
                          step.title,
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        Text(
                          step.goal,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: scheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            if (step.lines.isNotEmpty) const SizedBox(height: 10),
            for (final line in step.lines) ...[
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: MathLineView(
                  line: line,
                  selected: _selected,
                  onTap: _tapToken,
                ),
              ),
              if (_selected != null &&
                  line.tokens.any((t) => identical(t, _selected)) &&
                  _selected!.explanation != null)
                _Bubble(text: _selected!.explanation!, colors: colors),
              if (line.note != null)
                Padding(
                  padding: const EdgeInsetsDirectional.only(
                    start: 8,
                    bottom: 4,
                  ),
                  child: Text(
                    '↳ ${line.note!}',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                      height: 1.4,
                    ),
                  ),
                ),
            ],
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: scheme.surfaceContainerHighest.withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(10),
              ),
              child: prose(step.explanation),
            ),
            if (step.detail != null && step.detail!.isNotEmpty) ...[
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: TextButton.icon(
                  onPressed: () => setState(() => _explained = !_explained),
                  icon: Icon(
                    _explained ? Icons.expand_less : Icons.lightbulb_outline,
                    size: 18,
                  ),
                  label: Text(_explained ? s.hideExplain : s.explain),
                ),
              ),
              AnimatedCrossFade(
                duration: const Duration(milliseconds: 200),
                crossFadeState:
                    _explained
                        ? CrossFadeState.showSecond
                        : CrossFadeState.showFirst,
                firstChild: const SizedBox(width: double.infinity),
                secondChild: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    border: BorderDirectional(
                      start: BorderSide(color: colors.highlight, width: 3),
                    ),
                    color: colors.highlight.withValues(alpha: 0.08),
                  ),
                  child: prose(step.detail!),
                ),
              ),
            ],
            if (step.results.isNotEmpty && step.kind != StepKind.reactions) ...[
              const SizedBox(height: 6),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final r in step.results)
                    ResultChip(result: r, highlights: widget.highlights),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.text, required this.colors});

  final String text;
  final MechColors colors;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 4, bottom: 6),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: colors.highlight.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: colors.highlight.withValues(alpha: 0.6)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline, size: 18, color: colors.highlight),
          const SizedBox(width: 8),
          Expanded(child: Text(text, style: const TextStyle(height: 1.45))),
        ],
      ),
    );
  }
}

/// A result such as "RB = 10.00 kN ↑": tapping it shows where it is on the
/// drawing.
class ResultChip extends StatelessWidget {
  const ResultChip({super.key, required this.result, required this.highlights});

  final ResultValue result;
  final HighlightController highlights;

  @override
  Widget build(BuildContext context) {
    final colors = MechColors.of(context);
    return ListenableBuilder(
      listenable: highlights,
      builder: (context, _) {
        final active = highlights.source == result;
        return ActionChip(
          avatar: Icon(
            Icons.my_location,
            size: 16,
            color: active ? colors.highlight : colors.reaction,
          ),
          side: BorderSide(
            color:
                active
                    ? colors.highlight
                    : colors.reaction.withValues(alpha: 0.5),
          ),
          backgroundColor:
              active ? colors.highlight.withValues(alpha: 0.15) : null,
          label: Text(
            result.text,
            textDirection: TextDirection.ltr,
            style: const TextStyle(
              fontWeight: FontWeight.w700,
              fontFeatures: [FontFeature.tabularFigures()],
            ),
          ),
          onPressed: () => highlights.show(result.highlights, source: result),
        );
      },
    );
  }
}
