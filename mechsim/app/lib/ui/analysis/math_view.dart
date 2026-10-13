import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/palette.dart';

/// Renders text such as "ΣM_A = 0" with "A" as a subscript.
class MathText extends StatelessWidget {
  const MathText(this.text, {super.key, this.style});

  final String text;
  final TextStyle? style;

  static final _sub = RegExp(r'_([A-Za-z0-9]+)');

  static InlineSpan span(String text, TextStyle base) {
    final children = <InlineSpan>[];
    var last = 0;
    for (final m in _sub.allMatches(text)) {
      if (m.start > last) {
        children.add(TextSpan(text: text.substring(last, m.start)));
      }
      children.add(
        WidgetSpan(
          alignment: PlaceholderAlignment.baseline,
          baseline: TextBaseline.alphabetic,
          child: Transform.translate(
            offset: Offset(0, (base.fontSize ?? 14) * 0.28),
            child: Text(
              m.group(1)!,
              style: base.copyWith(fontSize: (base.fontSize ?? 14) * 0.72),
            ),
          ),
        ),
      );
      last = m.end;
    }
    if (last < text.length) children.add(TextSpan(text: text.substring(last)));
    return TextSpan(children: children, style: base);
  }

  @override
  Widget build(BuildContext context) {
    final base = DefaultTextStyle.of(context).style.merge(style);
    return Text.rich(span(text, base), textDirection: TextDirection.ltr);
  }
}

/// Prose in either language with symbols such as "F_BC" written with their
/// subscripts. Each symbol is isolated left to right, so it reads the same
/// inside an Arabic sentence.
class ProseText extends StatelessWidget {
  const ProseText(this.text, {super.key, this.style});

  final String text;
  final TextStyle? style;

  static final _symbol = RegExp(r'([A-Za-zΣ]+)_([A-Za-z0-9]+)');
  static final _arabic = RegExp('[\u0600-\u06FF]');

  @override
  Widget build(BuildContext context) {
    if (!text.contains('_')) return Text(text, style: style);
    final base = DefaultTextStyle.of(context).style.merge(style);
    final children = <InlineSpan>[];
    var last = 0;
    for (final m in _symbol.allMatches(text)) {
      if (m.start > last) {
        children.add(TextSpan(text: text.substring(last, m.start)));
      }
      children
        ..add(TextSpan(text: '\u2066${m.group(1)}'))
        ..add(
          WidgetSpan(
            alignment: PlaceholderAlignment.baseline,
            baseline: TextBaseline.alphabetic,
            child: Transform.translate(
              offset: Offset(0, (base.fontSize ?? 14) * 0.28),
              child: Text(
                m.group(2)!,
                textDirection: TextDirection.ltr,
                style: base.copyWith(fontSize: (base.fontSize ?? 14) * 0.72),
              ),
            ),
          ),
        )
        ..add(const TextSpan(text: '\u2069'));
      last = m.end;
    }
    if (last < text.length) children.add(TextSpan(text: text.substring(last)));
    // Only math (no Arabic letters): left to right, so "ΣM_F = 0" is not
    // turned around in an Arabic screen.
    return Text.rich(
      TextSpan(children: children),
      style: style,
      textDirection: _arabic.hasMatch(text) ? null : TextDirection.ltr,
    );
  }
}

/// One line of an equation, laid out left to right whatever the language,
/// with every meaningful term tappable.
class MathLineView extends StatelessWidget {
  const MathLineView({
    super.key,
    required this.line,
    required this.onTap,
    this.selected,
    this.fontSize = 16,
  });

  final MathLine line;
  final void Function(MathToken token) onTap;
  final MathToken? selected;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final colors = MechColors.of(context);
    final scheme = Theme.of(context).colorScheme;

    // Tokens without a space before them stick to the previous one.
    final groups = <List<MathToken>>[];
    for (final t in line.tokens) {
      if (groups.isEmpty || t.spaceBefore) {
        groups.add([t]);
      } else {
        groups.last.add(t);
      }
    }

    Widget token(MathToken t) {
      final interactive = t.isInteractive;
      final isSelected = identical(t, selected);
      final color = switch (t.role) {
        TokenRole.result => colors.reaction,
        TokenRole.term => interactive ? scheme.primary : scheme.onSurface,
        TokenRole.symbol => scheme.onSurface,
        TokenRole.operator || TokenRole.equals => scheme.onSurfaceVariant,
        _ => scheme.onSurface,
      };
      final style = TextStyle(
        fontSize: t.role == TokenRole.text ? fontSize * 0.85 : fontSize,
        fontWeight:
            t.role == TokenRole.result || t.role == TokenRole.symbol
                ? FontWeight.w800
                : FontWeight.w600,
        color: color,
        fontFeatures: const [FontFeature.tabularFigures()],
      );
      final text = Text.rich(
        MathText.span(t.text, style),
        textDirection: TextDirection.ltr,
      );
      if (!interactive) {
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: text,
        );
      }
      return Material(
        color:
            isSelected
                ? colors.highlight.withValues(alpha: 0.22)
                : color.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(6),
        child: InkWell(
          borderRadius: BorderRadius.circular(6),
          onTap: () => onTap(t),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(6),
              border: Border(
                bottom: BorderSide(
                  color:
                      isSelected
                          ? colors.highlight
                          : color.withValues(alpha: 0.5),
                  width: 1.5,
                ),
              ),
            ),
            child: text,
          ),
        ),
      );
    }

    return Directionality(
      textDirection: TextDirection.ltr,
      child: Wrap(
        spacing: 6,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          for (final g in groups)
            g.length == 1
                ? token(g.single)
                : Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [for (final t in g) token(t)],
                ),
        ],
      ),
    );
  }
}
