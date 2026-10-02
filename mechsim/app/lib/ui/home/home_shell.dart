import 'package:flutter/material.dart';

import '../../state/app_state.dart';
import '../learn/learn_tab.dart';
import '../practice/practice_screen.dart';
import '../saved/saved_tab.dart';
import '../settings/settings_tab.dart';
import 'home_tab.dart';

/// The app's frame: five destinations on a bottom navigation bar.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => HomeShellState();
}

class HomeShellState extends State<HomeShell> {
  int tab = 0;

  void go(int index) => setState(() => tab = index);

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final titles = [
      s.appName,
      s.practice,
      s.savedProblems,
      s.tutorials,
      s.settings,
    ];
    return Scaffold(
      appBar: tab == 0 ? null : AppBar(title: Text(titles[tab])),
      body: IndexedStack(
        index: tab,
        children: [
          HomeTab(onGo: go),
          const PracticeView(),
          const SavedTab(),
          const LearnTab(),
          const SettingsTab(),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: go,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.home_outlined),
            selectedIcon: const Icon(Icons.home),
            label: s.navHome,
          ),
          NavigationDestination(
            icon: const Icon(Icons.quiz_outlined),
            selectedIcon: const Icon(Icons.quiz),
            label: s.navPractice,
          ),
          NavigationDestination(
            icon: const Icon(Icons.bookmark_border),
            selectedIcon: const Icon(Icons.bookmark),
            label: s.navSaved,
          ),
          NavigationDestination(
            icon: const Icon(Icons.school_outlined),
            selectedIcon: const Icon(Icons.school),
            label: s.navLearn,
          ),
          NavigationDestination(
            icon: const Icon(Icons.settings_outlined),
            selectedIcon: const Icon(Icons.settings),
            label: s.navSettings,
          ),
        ],
      ),
    );
  }
}
