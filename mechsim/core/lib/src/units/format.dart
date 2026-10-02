/// Number formatting and parsing shared by every renderer.
library;

/// The typographic minus sign. Equations use it instead of the hyphen so that
/// "−10" reads as a negative number and not as a dash.
const String minus = '−';

abstract final class Num {
  /// Rounds to [maxDecimals] places and trims trailing zeros: 10, 2.5, 0.333.
  /// Never prints "−0".
  static String compact(double value, {int maxDecimals = 3}) {
    final text = _round(value, maxDecimals).toStringAsFixed(maxDecimals);
    return _withMinus(_trim(text));
  }

  /// Fixed number of decimals, the format of read-outs: 10.00, −10.00.
  static String fixed(double value, [int decimals = 2]) =>
      _withMinus(_round(value, decimals).toStringAsFixed(decimals));

  /// Like [fixed] but always carries a sign: +10.00, −10.00, 0.00.
  static String signed(double value, [int decimals = 2]) {
    final rounded = _round(value, decimals);
    final text = fixed(rounded, decimals);
    return rounded > 0 ? '+$text' : text;
  }

  /// True when [value] prints as zero at [decimals] places.
  static bool isZeroAt(double value, int decimals) =>
      _round(value, decimals) == 0;

  /// Parses what a person types. Accepts a hyphen or a typographic minus,
  /// a comma or the Arabic decimal separator, and Arabic-Indic or Persian
  /// digits, so an Arabic keyboard works without switching layouts.
  static double? parse(String input) {
    final buffer = StringBuffer();
    for (final rune in input.trim().runes) {
      if (rune >= 0x0660 && rune <= 0x0669) {
        buffer.writeCharCode(0x30 + rune - 0x0660);
      } else if (rune >= 0x06F0 && rune <= 0x06F9) {
        buffer.writeCharCode(0x30 + rune - 0x06F0);
      } else if (rune == 0x066B || rune == 0x2C) {
        buffer.write('.');
      } else if (rune == 0x2212 || rune == 0x2013) {
        buffer.write('-');
      } else if (rune == 0x066C || rune == 0x20 || rune == 0xA0) {
        // thousands separators and spaces are ignored
      } else {
        buffer.writeCharCode(rune);
      }
    }
    final text = buffer.toString();
    if (text.isEmpty) return null;
    final value = double.tryParse(text);
    if (value == null || value.isNaN || value.isInfinite) return null;
    return value;
  }

  static double _round(double value, int decimals) {
    if (value.isNaN || value.isInfinite) return value;
    var factor = 1.0;
    for (var i = 0; i < decimals; i++) {
      factor *= 10;
    }
    final rounded = (value * factor).roundToDouble() / factor;
    return rounded == 0 ? 0 : rounded; // folds −0 into 0
  }

  static String _trim(String text) {
    if (!text.contains('.')) return text;
    var end = text.length;
    while (text[end - 1] == '0') {
      end--;
    }
    if (text[end - 1] == '.') end--;
    return text.substring(0, end);
  }

  static String _withMinus(String text) =>
      text.startsWith('-') ? '$minus${text.substring(1)}' : text;
}
