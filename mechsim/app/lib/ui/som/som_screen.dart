import 'package:flutter/material.dart';

import '../../state/app_state.dart';

/// Strength of Materials: a placeholder that shows what is planned. Built
/// after the beam section has been fully tested, as agreed for the MVP.
class SomScreen extends StatelessWidget {
  const SomScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(s.somTitle)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(s.somIntro, style: theme.textTheme.bodyLarge),
          const SizedBox(height: 12),
          for (final (name, idea) in s.somPlanned)
            Card(
              child: ListTile(
                leading: const Icon(Icons.lock_clock_outlined),
                title: Text(
                  name,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                subtitle: Text(idea),
              ),
            ),
        ],
      ),
    );
  }
}
