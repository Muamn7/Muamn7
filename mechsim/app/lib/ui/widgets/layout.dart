import 'package:flutter/widgets.dart';

/// True when the screen is wider than tall and wide enough to put two panes
/// side by side: a phone turned sideways, a tablet, or a desktop window.
bool isWide(BuildContext context) {
  final size = MediaQuery.sizeOf(context);
  return size.width > size.height && size.width >= 560;
}
