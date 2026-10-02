import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mechsim_core/mechsim_core.dart';

/// A compact numeric input with a unit suffix. Accepts Arabic-Indic digits
/// and the Arabic decimal separator, commits on submit or when focus
/// leaves, and follows the value when it changes from outside (a drag).
class NumberField extends StatefulWidget {
  const NumberField({
    super.key,
    required this.label,
    required this.value,
    required this.unit,
    required this.onChanged,
    this.validator,
    this.allowNegative = false,
    this.width = 120,
  });

  final String label;
  final double value;
  final String unit;
  final ValueChanged<double> onChanged;

  /// Returns an error message, or null when the value is acceptable.
  final String? Function(double value)? validator;
  final bool allowNegative;
  final double width;

  @override
  State<NumberField> createState() => _NumberFieldState();
}

class _NumberFieldState extends State<NumberField> {
  late final TextEditingController _text = TextEditingController(
    text: Num.compact(widget.value, maxDecimals: 4),
  );
  final FocusNode _focus = FocusNode();
  String? _error;

  @override
  void initState() {
    super.initState();
    _focus.addListener(() {
      if (!_focus.hasFocus) _commit();
    });
  }

  @override
  void didUpdateWidget(NumberField old) {
    super.didUpdateWidget(old);
    if (!_focus.hasFocus && old.value != widget.value) {
      _text.text = Num.compact(
        widget.value,
        maxDecimals: 4,
      ).replaceAll(minus, '-');
      _error = null;
    }
  }

  void _commit() {
    final v = Num.parse(_text.text);
    if (v == null) {
      setState(() => _error = '?');
      return;
    }
    final message = widget.validator?.call(v);
    if (message != null) {
      setState(() => _error = message);
      return;
    }
    setState(() => _error = null);
    if (v != widget.value) widget.onChanged(v);
  }

  @override
  void dispose() {
    _text.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.width,
      child: Directionality(
        textDirection: TextDirection.ltr,
        child: TextField(
          controller: _text,
          focusNode: _focus,
          keyboardType: TextInputType.numberWithOptions(
            decimal: true,
            signed: widget.allowNegative,
          ),
          inputFormatters: [
            FilteringTextInputFormatter.allow(RegExp(r'[0-9٠-٩۰-۹.,٫\-−]')),
          ],
          textInputAction: TextInputAction.done,
          onSubmitted: (_) => _commit(),
          onTapOutside: (_) => _focus.unfocus(),
          decoration: InputDecoration(
            isDense: true,
            labelText: widget.label,
            suffixText: widget.unit,
            errorText: _error,
            errorMaxLines: 2,
            border: const OutlineInputBorder(),
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 10,
              vertical: 10,
            ),
          ),
        ),
      ),
    );
  }
}
