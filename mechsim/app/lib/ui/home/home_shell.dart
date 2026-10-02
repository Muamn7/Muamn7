import 'package:flutter/material.dart';

import '../../state/app_state.dart';
import '../learn/learn_tab.dart';
import '../practice/practice_screen.dart';
import '../saved/saved_tab.dart';
import '../settings/settings_tab.dart';
import '../widgets/layout.dart';
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
    final destinations = [
      (Icons.home_outlined, Icons.home, s.navHome),
      (Icons.quiz_outlined, Icons.quiz, s.navPractice),
      (Icons.bookmark_border, Icons.bookmark, s.navSaved),
      (Icons.school_outlined, Icons.school, s.navLearn),
      (Icons.settings_outlined, Icons.settings, s.navSettings),
    ];
    final body = IndexedStack(
      index: tab,
      children: [
        HomeTab(onGo: go),
        const PracticeView(),
        const SavedTab(),
        const LearnTab(),
        const SettingsTab(),
      ],
    );
    final wide = isWide(context);
    return Scaffold(
      appBar:
          tab == 0
              ? null
              : AppBar(
                title: Text(titles[tab]),
                toolbarHeight: wide ? 48 : null,
              ),
      // Sideways the navigation moves to a rail on the side, leaving the
      // short height to the content.
      body:
          wide
              ? SafeArea(
                child: Row(
                  children: [
                    NavigationRail(
                      selectedIndex: tab,
                      onDestinationSelected: go,
                      labelType: NavigationRailLabelType.all,
                      destinations: [
                        for (final (icon, selected, label) in destinations)
                          NavigationRailDestination(
                            icon: Icon(icon),
                            selectedIcon: Icon(selected),
                            label: Text(label),
                          ),
                      ],
                    ),
                    const VerticalDivider(width: 1),
                    Expanded(child: body),
                  ],
                ),
              )
              : body,
      bottomNavigationBar:
          wide
              ? null
              : NavigationBar(
                selectedIndex: tab,
                onDestinationSelected: go,
                labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
                destinations: [
                  for (final (icon, selected, label) in destinations)
                    NavigationDestination(
                      icon: Icon(icon),
                      selectedIcon: Icon(selected),
                      label: label,
                    ),
                ],
              ),
    );
  }
}
