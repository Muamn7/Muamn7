import 'package:flutter/foundation.dart';
import 'package:mechsim_core/mechsim_core.dart';

/// Links the calculation to the drawing: whatever the student taps in the
/// explanation (a term, a result, a step) is published here, and every
/// drawing of the problem shows it.
class HighlightController extends ChangeNotifier {
  List<Highlight> _items = const [];
  Object? _source;

  List<Highlight> get items => _items;
  Object? get source => _source;
  bool get isEmpty => _items.isEmpty;

  /// Shows [items]. Tapping the same [source] again turns it off.
  void show(List<Highlight> items, {Object? source}) {
    if (source != null && identical(source, _source) ||
        (source != null && source == _source)) {
      clear();
      return;
    }
    _items = List.unmodifiable(items);
    _source = source;
    notifyListeners();
  }

  void clear() {
    if (_items.isEmpty && _source == null) return;
    _items = const [];
    _source = null;
    notifyListeners();
  }
}
