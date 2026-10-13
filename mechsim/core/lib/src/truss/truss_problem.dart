/// The 2D model of a plane truss: joints (pins) at points, straight
/// two-force members between them, supports at joints, and loads applied
/// only at joints. Immutable, like the beam model: an edit makes a new
/// [TrussProblem], which keeps undo/redo a stack of snapshots.
///
/// x runs right and y up, in metres; forces are in newtons.
library;

import 'dart:math' as math;

import '../model/beam_problem.dart' show cosDeg, sinDeg;

class TrussNode {
  const TrussNode({required this.id, required this.x, required this.y});

  final String id;
  final double x;
  final double y;

  TrussNode copyWith({double? x, double? y}) =>
      TrussNode(id: id, x: x ?? this.x, y: y ?? this.y);

  Map<String, Object?> toJson() => {'id': id, 'x': x, 'y': y};

  factory TrussNode.fromJson(Map<String, Object?> json) => TrussNode(
        id: json['id'] as String,
        x: (json['x'] as num).toDouble(),
        y: (json['y'] as num).toDouble(),
      );

  @override
  bool operator ==(Object other) =>
      other is TrussNode && other.id == id && other.x == x && other.y == y;

  @override
  int get hashCode => Object.hash(id, x, y);
}

/// A straight member pinned at both ends: it can only pull (tension) or
/// push (compression) along its own line.
class TrussMember {
  const TrussMember({required this.id, required this.a, required this.b});

  final String id;

  /// The joints at its ends.
  final String a;
  final String b;

  bool joins(String node) => a == node || b == node;

  /// The joint at the other end from [node].
  String other(String node) => node == a ? b : a;

  Map<String, Object?> toJson() => {'id': id, 'a': a, 'b': b};

  factory TrussMember.fromJson(Map<String, Object?> json) => TrussMember(
        id: json['id'] as String,
        a: json['a'] as String,
        b: json['b'] as String,
      );

  @override
  bool operator ==(Object other) =>
      other is TrussMember && other.id == id && other.a == a && other.b == b;

  @override
  int get hashCode => Object.hash(id, a, b);
}

enum TrussSupportType {
  /// Holds the joint in both directions: two reactions.
  pin,

  /// Rests on a horizontal surface: one vertical reaction.
  roller,
}

class TrussSupport {
  const TrussSupport({
    required this.id,
    required this.node,
    required this.type,
  });

  final String id;
  final String node;
  final TrussSupportType type;

  TrussSupport copyWith({TrussSupportType? type, String? node}) =>
      TrussSupport(id: id, node: node ?? this.node, type: type ?? this.type);

  Map<String, Object?> toJson() =>
      {'id': id, 'node': node, 'type': type.name};

  factory TrussSupport.fromJson(Map<String, Object?> json) => TrussSupport(
        id: json['id'] as String,
        node: json['node'] as String,
        type: TrussSupportType.values.byName(json['type'] as String),
      );

  @override
  bool operator ==(Object other) =>
      other is TrussSupport &&
      other.id == id &&
      other.node == node &&
      other.type == type;

  @override
  int get hashCode => Object.hash(id, node, type);
}

/// A force applied at a joint; [angleDeg] counter-clockwise from +x, so
/// −90 points down.
class TrussLoad {
  const TrussLoad({
    required this.id,
    required this.node,
    required this.magnitude,
    this.angleDeg = -90,
  });

  final String id;
  final String node;
  final double magnitude;
  final double angleDeg;

  double get fx => magnitude * cosDeg(angleDeg);
  double get fy => magnitude * sinDeg(angleDeg);

  TrussLoad copyWith({double? magnitude, double? angleDeg, String? node}) =>
      TrussLoad(
        id: id,
        node: node ?? this.node,
        magnitude: magnitude ?? this.magnitude,
        angleDeg: angleDeg ?? this.angleDeg,
      );

  Map<String, Object?> toJson() => {
        'id': id,
        'node': node,
        'magnitude': magnitude,
        'angle': angleDeg,
      };

  factory TrussLoad.fromJson(Map<String, Object?> json) => TrussLoad(
        id: json['id'] as String,
        node: json['node'] as String,
        magnitude: (json['magnitude'] as num).toDouble(),
        angleDeg: (json['angle'] as num?)?.toDouble() ?? -90,
      );

  @override
  bool operator ==(Object other) =>
      other is TrussLoad &&
      other.id == id &&
      other.node == node &&
      other.magnitude == magnitude &&
      other.angleDeg == angleDeg;

  @override
  int get hashCode => Object.hash(id, node, magnitude, angleDeg);
}

class TrussProblem {
  const TrussProblem({
    this.nodes = const [],
    this.members = const [],
    this.supports = const [],
    this.loads = const [],
    this.title = '',
  });

  final List<TrussNode> nodes;
  final List<TrussMember> members;
  final List<TrussSupport> supports;
  final List<TrussLoad> loads;
  final String title;

  bool get isEmpty => nodes.isEmpty;

  TrussNode? node(String id) {
    for (final n in nodes) {
      if (n.id == id) return n;
    }
    return null;
  }

  TrussMember? member(String id) {
    for (final m in members) {
      if (m.id == id) return m;
    }
    return null;
  }

  TrussSupport? supportAt(String node) {
    for (final s in supports) {
      if (s.node == node) return s;
    }
    return null;
  }

  TrussLoad? load(String id) {
    for (final l in loads) {
      if (l.id == id) return l;
    }
    return null;
  }

  /// The joint within [tol] of (x, y), if any.
  TrussNode? nodeNear(double x, double y, double tol) {
    TrussNode? best;
    var bestD = tol;
    for (final n in nodes) {
      final d = math.sqrt((n.x - x) * (n.x - x) + (n.y - y) * (n.y - y));
      if (d <= bestD) {
        best = n;
        bestD = d;
      }
    }
    return best;
  }

  /// The member joining [a] and [b], in either order.
  TrussMember? memberBetween(String a, String b) {
    for (final m in members) {
      if ((m.a == a && m.b == b) || (m.a == b && m.b == a)) return m;
    }
    return null;
  }

  Iterable<TrussMember> membersAt(String node) =>
      members.where((m) => m.joins(node));

  double lengthOf(TrussMember m) {
    final a = node(m.a)!, b = node(m.b)!;
    return math.sqrt((b.x - a.x) * (b.x - a.x) + (b.y - a.y) * (b.y - a.y));
  }

  /// A fresh id with [prefix]: n1, n2… for joints, m1… for members.
  String nextId(String prefix) {
    final used = {
      ...nodes.map((e) => e.id),
      ...members.map((e) => e.id),
      ...supports.map((e) => e.id),
      ...loads.map((e) => e.id),
    };
    var i = 1;
    while (used.contains('$prefix$i')) {
      i++;
    }
    return '$prefix$i';
  }

  TrussProblem copyWith({
    List<TrussNode>? nodes,
    List<TrussMember>? members,
    List<TrussSupport>? supports,
    List<TrussLoad>? loads,
    String? title,
  }) =>
      TrussProblem(
        nodes: nodes ?? this.nodes,
        members: members ?? this.members,
        supports: supports ?? this.supports,
        loads: loads ?? this.loads,
        title: title ?? this.title,
      );

  TrussProblem withNode(TrussNode n) => copyWith(nodes: [...nodes, n]);

  /// Adds a member, unless it would join a joint to itself or duplicate one
  /// already there.
  TrussProblem withMember(TrussMember m) {
    if (m.a == m.b || memberBetween(m.a, m.b) != null) return this;
    if (node(m.a) == null || node(m.b) == null) return this;
    return copyWith(members: [...members, m]);
  }

  /// Puts a support at a joint, replacing any support already there.
  TrussProblem withSupport(TrussSupport s) => copyWith(supports: [
        for (final e in supports)
          if (e.node != s.node && e.id != s.id) e,
        s,
      ]);

  TrussProblem withLoad(TrussLoad l) => copyWith(loads: [
        for (final e in loads)
          if (e.id != l.id) e,
        l,
      ]);

  TrussProblem replaceNode(TrussNode n) =>
      copyWith(nodes: [for (final e in nodes) e.id == n.id ? n : e]);

  TrussProblem moveNode(String id, double x, double y) {
    final n = node(id);
    return n == null ? this : replaceNode(n.copyWith(x: x, y: y));
  }

  TrussProblem replaceSupport(TrussSupport s) =>
      copyWith(supports: [for (final e in supports) e.id == s.id ? s : e]);

  TrussProblem replaceLoad(TrussLoad l) =>
      copyWith(loads: [for (final e in loads) e.id == l.id ? l : e]);

  /// Removes anything by id; removing a joint takes its members, support
  /// and loads with it.
  TrussProblem remove(String id) {
    if (node(id) != null) {
      return copyWith(
        nodes: nodes.where((n) => n.id != id).toList(),
        members: members.where((m) => !m.joins(id)).toList(),
        supports: supports.where((s) => s.node != id).toList(),
        loads: loads.where((l) => l.node != id).toList(),
      );
    }
    return copyWith(
      members: members.where((m) => m.id != id).toList(),
      supports: supports.where((s) => s.id != id).toList(),
      loads: loads.where((l) => l.id != id).toList(),
    );
  }

  bool contains(String id) =>
      node(id) != null ||
      member(id) != null ||
      supports.any((s) => s.id == id) ||
      load(id) != null;

  Map<String, Object?> toJson() => {
        'kind': 'truss',
        'title': title,
        'nodes': [for (final n in nodes) n.toJson()],
        'members': [for (final m in members) m.toJson()],
        'supports': [for (final s in supports) s.toJson()],
        'loads': [for (final l in loads) l.toJson()],
      };

  factory TrussProblem.fromJson(Map<String, Object?> json) {
    List<Map<String, Object?>> list(String key) => [
          for (final e in (json[key] as List?) ?? const [])
            (e as Map).cast<String, Object?>(),
        ];
    return TrussProblem(
      title: json['title'] as String? ?? '',
      nodes: [for (final e in list('nodes')) TrussNode.fromJson(e)],
      members: [for (final e in list('members')) TrussMember.fromJson(e)],
      supports: [for (final e in list('supports')) TrussSupport.fromJson(e)],
      loads: [for (final e in list('loads')) TrussLoad.fromJson(e)],
    );
  }

  @override
  bool operator ==(Object other) =>
      other is TrussProblem &&
      other.title == title &&
      _listEq(other.nodes, nodes) &&
      _listEq(other.members, members) &&
      _listEq(other.supports, supports) &&
      _listEq(other.loads, loads);

  @override
  int get hashCode => Object.hash(title, Object.hashAll(nodes),
      Object.hashAll(members), Object.hashAll(supports), Object.hashAll(loads));
}

bool _listEq<T>(List<T> a, List<T> b) {
  if (a.length != b.length) return false;
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}

/// Names for a truss: joints lettered A, B, C… in the order they were
/// placed; a member is named by its two joints (AB), a reaction by its
/// joint and direction (Ax, Ay).
class TrussLabels {
  TrussLabels._(this._letters);

  factory TrussLabels.of(TrussProblem p) => TrussLabels._({
        for (var i = 0; i < p.nodes.length; i++) p.nodes[i].id: _letter(i),
      });

  final Map<String, String> _letters;

  static String _letter(int i) {
    const abc = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    return i < abc.length ? abc[i] : '${abc[i % 26]}${i ~/ 26}';
  }

  String node(String id) => _letters[id] ?? '?';

  /// "AB", with the joints in alphabetical order.
  String member(TrussMember m) {
    final a = node(m.a), b = node(m.b);
    return a.compareTo(b) <= 0 ? '$a$b' : '$b$a';
  }
}

/// Ready-made trusses to start from: span [span] split into [panels]
/// panels of height [height], pinned at the left end and on a roller at the
/// right, with a load on each inner bottom joint.
abstract final class TrussTemplates {
  static const kinds = ['triangle', 'warren', 'pratt', 'howe'];

  static TrussProblem build(String kind,
      {double span = 12, int panels = 4, double height = 3, double load = 10000}) {
    var p = const TrussProblem();
    String add(double x, double y) {
      final id = p.nextId('n');
      p = p.withNode(TrussNode(id: id, x: x, y: y));
      return id;
    }

    void bar(String a, String b) =>
        p = p.withMember(TrussMember(id: p.nextId('m'), a: a, b: b));

    void support(String node, TrussSupportType type) => p =
        p.withSupport(TrussSupport(id: p.nextId('s'), node: node, type: type));

    if (kind == 'triangle') {
      final a = add(0, 0), b = add(span / 2, height), c = add(span, 0);
      bar(a, b);
      bar(b, c);
      bar(a, c);
      support(a, TrussSupportType.pin);
      support(c, TrussSupportType.roller);
      p = p.withLoad(TrussLoad(id: p.nextId('f'), node: b, magnitude: load));
      return p;
    }

    final d = span / panels;
    if (kind == 'warren') {
      // Bottom chord joints, then top joints over the middle of each panel.
      final bottom = [for (var i = 0; i <= panels; i++) add(i * d, 0)];
      final top = [for (var i = 0; i < panels; i++) add(i * d + d / 2, height)];
      for (var i = 0; i < panels; i++) {
        bar(bottom[i], bottom[i + 1]);
        bar(bottom[i], top[i]);
        bar(top[i], bottom[i + 1]);
        if (i < panels - 1) bar(top[i], top[i + 1]);
      }
      support(bottom.first, TrussSupportType.pin);
      support(bottom.last, TrussSupportType.roller);
      for (var i = 1; i < panels; i++) {
        p = p.withLoad(TrussLoad(id: p.nextId('f'), node: bottom[i], magnitude: load));
      }
      return p;
    }

    // Pratt and Howe: a top chord over the inner bottom joints, verticals,
    // and diagonals leaning towards (Pratt) or away from (Howe) the middle.
    final bottom = [for (var i = 0; i <= panels; i++) add(i * d, 0)];
    final top = <int, String>{
      for (var i = 1; i < panels; i++) i: add(i * d, height),
    };
    for (var i = 0; i < panels; i++) {
      bar(bottom[i], bottom[i + 1]);
    }
    for (var i = 1; i < panels - 1; i++) {
      bar(top[i]!, top[i + 1]!);
    }
    bar(bottom.first, top[1]!);
    bar(top[panels - 1]!, bottom.last);
    for (var i = 1; i < panels; i++) {
      bar(bottom[i], top[i]!);
    }
    final half = panels / 2;
    for (var i = 1; i < panels - 1; i++) {
      // Panel between i and i + 1.
      final leftHalf = i + 0.5 < half;
      final pratt = kind == 'pratt';
      // Pratt diagonals slope down towards the middle; Howe's up.
      if (leftHalf == pratt) {
        bar(top[i]!, bottom[i + 1]);
      } else {
        bar(bottom[i], top[i + 1]!);
      }
    }
    support(bottom.first, TrussSupportType.pin);
    support(bottom.last, TrussSupportType.roller);
    for (var i = 1; i < panels; i++) {
      p = p.withLoad(TrussLoad(id: p.nextId('f'), node: bottom[i], magnitude: load));
    }
    return p;
  }
}
