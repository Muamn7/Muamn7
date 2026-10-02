/// Renders a [Solution] as plain text: for the command line, for a calculator
/// with a text screen, or for copying a solution out of the app.
library;

import '../units/format.dart';
import 'solution.dart';

abstract final class TextRenderer {
  static String render(Solution solution, {bool withDetail = false}) {
    final b = StringBuffer();
    for (var i = 0; i < solution.steps.length; i++) {
      final step = solution.steps[i];
      b.writeln(_strip('${i + 1}. ${step.title}  —  ${step.goal}'));
      for (final line in step.lines) {
        b.writeln('     ${_strip(line.plain)}');
        if (line.note != null) {
          for (final note in line.note!.split('\n')) {
            b.writeln('       ↳ ${_strip(note)}');
          }
        }
      }
      b.writeln('   ${_strip(step.explanation)}');
      if (withDetail && step.detail != null && step.detail!.isNotEmpty) {
        b.writeln('   ${_strip(step.detail!)}');
      }
      b.writeln();
    }
    final validation = solution.validation;
    if (validation != null) {
      b.writeln(validation.allPassed ? 'All checks passed ✓' : 'Some checks FAILED ✗');
      for (final item in validation.items) {
        b.writeln('   ${item.passed ? '✓' : '✗'} ${item.kind.name}'
            '  (residual ${Num.compact(item.residual, maxDecimals: 9)})');
      }
    }
    return b.toString();
  }

  /// Removes the directional isolates, which a terminal shows as boxes.
  static String _strip(String s) => s.replaceAll(RegExp('[\u2066-\u2069]'), '');
}
