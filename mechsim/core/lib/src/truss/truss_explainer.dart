/// The truss explanation: the reactions from the whole truss, then the
/// method of joints joint by joint (always a joint with at most two unknown
/// members, ΣFx = 0 and ΣFy = 0 there), a check at an unused joint and the
/// table of member forces; and, for any cut the student draws, the method
/// of sections with moments about where two cut members' lines meet.
///
/// Every number is computed from the problem. The answers the steps reach
/// are the ones [TrussSolver] gets from all the equations at once, and the
/// tests hold the two to each other.
library;

import 'dart:math' as math;

import '../explain/highlight.dart';
import '../explain/lang.dart';
import '../explain/solution.dart';
import '../units/format.dart';
import '../units/unit.dart';
import 'truss_lang.dart';
import 'truss_problem.dart';
import 'truss_solver.dart';

class TrussExplanation {
  const TrussExplanation({
    required this.problem,
    required this.solution,
    required this.steps,
    this.members = const [],
    this.reactions = const [],
  });

  final TrussProblem problem;
  final TrussSolution solution;
  final List<SolutionStep> steps;

  /// Each member's force, in the order of [TrussProblem.members].
  final List<ResultValue> members;
  final List<ResultValue> reactions;

  bool get isSolved => solution.isSolved;
}

/// The method of sections for one cut.
class TrussSection {
  const TrussSection({
    required this.cut,
    required this.side,
    required this.steps,
    this.error,
    this.points = const [],
  });

  /// The members cut, by id.
  final List<String> cut;

  /// The joints of the part kept.
  final Set<String> side;
  final List<SolutionStep> steps;

  /// Why this cut cannot be solved; null when it can.
  final String? error;

  /// Points moments were taken about that are not joints, with their
  /// names (O, O2…), for the drawing.
  final List<(String, double, double)> points;

  bool get isValid => error == null;
}

class TrussExplainer {
  const TrussExplainer({this.lang = Lang.ar, this.units = UnitSystem.knM});

  final Lang lang;
  final UnitSystem units;

  TrussExplanation explain(TrussProblem problem) {
    final s = TrussSolver.solve(problem);
    final w = _Writer(s, TrussTexts.of(lang), units);
    if (!s.isSolved) {
      return TrussExplanation(
        problem: problem,
        solution: s,
        steps: [if (!problem.isEmpty) w.given(), w.unsolvable()],
      );
    }
    return TrussExplanation(
      problem: problem,
      solution: s,
      steps: w.joints(),
      members: [for (final m in problem.members) w.memberResult(m.id)],
      reactions: [for (final r in s.reactions) w.reactionResult(r)],
    );
  }

  TrussSection section(TrussProblem problem, List<String> cut,
      {bool otherSide = false}) {
    final s = TrussSolver.solve(problem);
    final w = _Writer(s, TrussTexts.of(lang), units);
    return w.section(cut, otherSide: otherSide);
  }
}

/// One term of an equation: what is written, the sign it is written with,
/// and its value (for a known term) or coefficient (for an unknown one).
class _Term {
  const _Term.known(this.text, this.sign, this.value,
      {this.explanation, this.highlights = const []})
      : unknown = null,
        coef = 0;

  const _Term.unknown(this.text, this.unknown, this.coef,
      {this.explanation, this.highlights = const []})
      : sign = coef < 0 ? -1 : 1,
        value = 0;

  final String text;

  /// +1 or −1, as written.
  final int sign;

  /// The term's contribution in SI (known terms).
  final double value;

  /// The id of the unknown it multiplies, and by how much (SI).
  final String? unknown;
  final double coef;
  final String? explanation;
  final List<Highlight> highlights;
}

class _Eq {
  _Eq(this.header, this.terms, {this.moment = false, this.headerHl = const []});

  /// "ΣFx = 0", "ΣM_A = 0".
  final String header;
  final List<_Term> terms;
  final bool moment;
  final List<Highlight> headerHl;

  Set<String> get unknowns => {
        for (final t in terms)
          if (t.unknown != null) t.unknown!,
      };

  double get knownSum => terms
      .where((t) => t.unknown == null)
      .fold(0.0, (s, t) => s + t.value);

  double coefOf(String id) => terms
      .where((t) => t.unknown == id)
      .fold(0.0, (s, t) => s + t.coef);
}

class _Writer {
  _Writer(this.s, this.t, this.units)
      : p = s.problem,
        labels = s.labels;

  final TrussSolution s;
  final TrussTexts t;
  final UnitSystem units;
  final TrussProblem p;
  final TrussLabels labels;

  // ---- numbers -----------------------------------------------------------

  String get fu => units.force.symbol;
  String get lu => units.length.symbol;
  double fd(double si) => units.toDisplay(si, Dimension.force);
  double ld(double si) => units.toDisplay(si, Dimension.length);
  double fld(double si) => si / (units.force.toSi * units.length.toSi);
  String f(double si) => Num.compact(fd(si));
  String l(double si) => Num.compact(ld(si));
  String fU(double si) => '${f(si)} $fu';
  String lU(double si) => '${l(si)} $lu';
  String readout(double si) => '${Num.fixed(fd(si))} $fu';

  /// A value in an equation's own units: force, or force × length.
  String eqValue(double si, bool moment) =>
      Num.compact(moment ? fld(si) : fd(si));

  String node(String id) => labels.node(id);
  String name(String memberId) => 'F_${labels.member(p.member(memberId)!)}';
  String nameOf(TrussMember m) => 'F_${labels.member(m)}';

  String arrowX(double v) => v >= 0 ? '→' : '←';
  String arrowY(double v) => v >= 0 ? '↑' : '↓';

  /// cos or sin of a member's angle, written the way a textbook would:
  /// (3/5) when the length is a round number, cos 45° when the angle is,
  /// else the decimal.
  String ratio(double part, double dx, double dy, double len,
      {required bool cos}) {
    final lenD = ld(len);
    if ((lenD * 100 - (lenD * 100).roundToDouble()).abs() < 1e-6) {
      return '(${l(part)}/${l(len)})';
    }
    final deg = math.atan2(dy.abs(), dx.abs()) * 180 / math.pi;
    if ((deg - deg.roundToDouble()).abs() < 1e-6) {
      return '${cos ? 'cos' : 'sin'} ${deg.round()}°';
    }
    return Num.compact(part / len, maxDecimals: 4);
  }

  String tc(double v) => v.abs() < 1e-9
      ? t.zeroForce
      : v > 0
          ? t.tension
          : t.compression;

  ResultValue memberResult(String id) {
    final v = s.force(id);
    final n = name(id);
    final text = v.abs() < 1e-9
        ? '$n = 0 (${t.zeroForce})'
        : v > 0
            ? '$n = ${readout(v)} (T)'
            : '$n = ${readout(v)} ⇒ ${readout(-v)} (C)';
    return ResultValue(
      symbol: n,
      si: v,
      dimension: Dimension.force,
      text: text,
      direction: v.abs() < 1e-9 ? null : (v > 0 ? 'T' : 'C'),
      highlights: [MemberHighlight(id)],
    );
  }

  ResultValue reactionResult(TrussReaction r) {
    final v = s.reaction(r.id);
    final arrow = r.axis == TrussAxis.x ? arrowX(v) : arrowY(v);
    final text = v == 0
        ? '${r.symbol} = 0'
        : v > 0
            ? '${r.symbol} = ${readout(v)} $arrow'
            : '${r.symbol} = ${readout(v)} ⇒ ${readout(-v)} $arrow';
    return ResultValue(
      symbol: r.symbol,
      si: v,
      dimension: Dimension.force,
      text: text,
      direction: v == 0 ? null : arrow,
      highlights: [ReactionHighlight(r.id)],
    );
  }

  // ---- steps -------------------------------------------------------------

  SolutionStep given() {
    return SolutionStep(
      kind: StepKind.given,
      title: t.givenTitle,
      goal: t.givenGoal,
      lines: [
        MathLine([
          for (var i = 0; i < p.nodes.length; i++)
            MathToken(
              '${node(p.nodes[i].id)}(${l(p.nodes[i].x)}, ${l(p.nodes[i].y)})',
              role: TokenRole.value,
              highlights: [JointHighlight(p.nodes[i].id)],
            ),
        ]),
        for (final sup in p.supports)
          MathLine([
            MathToken('${node(sup.node)}:', role: TokenRole.symbol),
            MathToken(sup.type == TrussSupportType.pin ? 'Pin' : 'Roller',
                role: TokenRole.term,
                highlights: [SupportHighlight(sup.id)]),
          ], highlights: [SupportHighlight(sup.id)]),
        for (final load in p.loads)
          MathLine([
            MathToken(
                '${fU(load.magnitude)} ${_loadArrow(load)} @ ${node(load.node)}',
                role: TokenRole.term,
                highlights: [LoadHighlight(load.id)]),
          ], highlights: [LoadHighlight(load.id)]),
      ],
      explanation:
          t.givenExplanation(p.nodes.length, p.members.length, p.loads.length),
    );
  }

  String _loadArrow(TrussLoad l) {
    final dx = l.fx, dy = l.fy;
    if (dx.abs() < 1e-9 * l.magnitude) return arrowY(dy);
    if (dy.abs() < 1e-9 * l.magnitude) return arrowX(dx);
    if (dx > 0) return dy > 0 ? '↗' : '↘';
    return dy > 0 ? '↖' : '↙';
  }

  SolutionStep unsolvable() {
    final st = s.stability;
    return SolutionStep(
      kind: StepKind.unsolvable,
      title: t.unsolvableTitle(st.reason),
      goal: '',
      lines: [
        if (st.reason != TrussReason.empty)
          MathLine([
            MathToken('m + r = ${st.members} + ${st.reactions} = ${st.members + st.reactions}',
                role: TokenRole.value),
            const MathToken('vs', role: TokenRole.text),
            MathToken('2j = ${2 * st.joints}', role: TokenRole.value),
          ]),
      ],
      explanation: t.stabilityMessage(st),
      detail: t.stabilityAdvice(st.reason).isEmpty
          ? null
          : t.stabilityAdvice(st.reason),
    );
  }

  SolutionStep determinacy() {
    final st = s.stability;
    return SolutionStep(
      kind: StepKind.trussDeterminacy,
      title: t.determinacyTitle,
      goal: t.determinacyGoal,
      lines: [
        MathLine([
          MathToken('m = ${st.members}', role: TokenRole.value),
          const MathToken(',', role: TokenRole.operator, spaceBefore: false),
          MathToken('r = ${st.reactions}', role: TokenRole.value),
          const MathToken(',', role: TokenRole.operator, spaceBefore: false),
          MathToken('j = ${st.joints}', role: TokenRole.value),
        ]),
        MathLine([
          MathToken('m + r = ${st.members + st.reactions}',
              role: TokenRole.term),
          const MathToken('=', role: TokenRole.equals),
          MathToken('2j = ${2 * st.joints}', role: TokenRole.term),
          const MathToken('✓', role: TokenRole.result),
        ]),
      ],
      explanation:
          t.determinacyExplanation(st.members, st.reactions, st.joints),
      detail: t.determinacyDetail,
    );
  }

  // ---- writing equations -------------------------------------------------

  List<MathToken> _terms(_Eq eq, Map<String, double> known) {
    final tokens = <MathToken>[];
    var first = true;
    for (final term in eq.terms) {
      var text = term.text, sign = term.sign;
      var explanation = term.explanation;
      final id = term.unknown;
      if (id != null && known.containsKey(id)) {
        // Substitute the value, keeping the sign the term is written with.
        final v = known[id]!;
        final factor = term.coef.abs();
        final value = eq.moment ? fld(v) : fd(v);
        final number = Num.compact(value);
        final wrapped = value < 0 ? '($number)' : number;
        text = _isOne(factor, eq.moment)
            ? wrapped
            : '$wrapped × ${eq.moment ? l(factor) : _factorText(term)}';
        explanation = _knownExplanation(id, v);
        sign = term.coef < 0 ? -1 : 1;
      }
      if (first) {
        if (sign < 0) {
          tokens.add(const MathToken(minus, role: TokenRole.operator));
        }
        tokens.add(MathToken(text,
            role: TokenRole.term,
            explanation: explanation,
            highlights: term.highlights,
            spaceBefore: sign >= 0));
        first = false;
      } else {
        tokens
          ..add(MathToken(sign < 0 ? minus : '+', role: TokenRole.operator))
          ..add(MathToken(text,
              role: TokenRole.term,
              explanation: explanation,
              highlights: term.highlights));
      }
    }
    if (tokens.isEmpty) tokens.add(const MathToken('0', role: TokenRole.value));
    return tokens;
  }

  bool _isOne(double factor, bool moment) => (factor - 1).abs() < 1e-12 && !moment;

  /// The direction-cosine part of a member term's text: "F_AB·(3/5)" →
  /// "(3/5)".
  String _factorText(_Term term) {
    final i = term.text.indexOf('·');
    return i < 0 ? '1' : term.text.substring(i + 1);
  }

  String _knownExplanation(String id, double v) {
    final m = p.member(id);
    if (m != null) return t.termKnownMember(nameOf(m), fU(v));
    final r = s.reactions.where((x) => x.id == id).firstOrNull;
    return t.termKnownReaction(r?.symbol ?? id, fU(v));
  }

  MathLine _equationLine(_Eq eq, Map<String, double> known) => MathLine([
        ..._terms(eq, known),
        const MathToken('=', role: TokenRole.equals),
        const MathToken('0', role: TokenRole.value),
      ]);

  MathLine _header(_Eq eq, String convention) => MathLine([
        MathToken(eq.header.replaceFirst(' = 0', ''),
            role: TokenRole.symbol, highlights: eq.headerHl),
        const MathToken('=', role: TokenRole.equals),
        const MathToken('0', role: TokenRole.value),
        MathToken('($convention +)', role: TokenRole.text),
      ]);

  /// Lines that solve [eq] for its one unknown [id], given [known].
  (List<MathLine>, double) _solveOne(
      _Eq eq, String id, Map<String, double> known, String symbol,
      List<Highlight> hl) {
    final coef = eq.coefOf(id);
    var rest = eq.knownSum;
    for (final term in eq.terms) {
      final u = term.unknown;
      if (u != null && u != id && known.containsKey(u)) {
        rest += term.coef * known[u]!;
      }
    }
    final value = -rest / coef;
    final lines = <MathLine>[];
    final c = coef.abs();
    final rhs = -rest * coef.sign;
    final rhsText = eqValue(rhs, eq.moment);
    final unknownTerm = eq.terms.firstWhere((x) => x.unknown == id);
    final cText = eq.moment ? l(c) : _factorText(unknownTerm);
    final result = MathToken(fU(value), role: TokenRole.result, highlights: hl);
    final sym = MathToken(symbol, role: TokenRole.symbol, highlights: hl);
    const eqs = MathToken('=', role: TokenRole.equals);
    if (_isOne(c, eq.moment)) {
      lines.add(MathLine([sym, eqs, result]));
    } else {
      lines.add(MathLine([
        MathToken('$symbol × $cText', role: TokenRole.term, highlights: hl),
        eqs,
        MathToken(rhsText, role: TokenRole.value),
      ]));
      lines.add(MathLine([
        sym,
        eqs,
        MathToken('$rhsText ÷ $cText', role: TokenRole.value),
        eqs,
        result,
      ]));
    }
    return (lines, value);
  }

  // ---- whole-truss equilibrium -------------------------------------------

  /// Terms of the forces from outside the members acting at joints in
  /// [nodes] (loads, and reactions as unknowns or knowns), for ΣFx, ΣFy, or
  /// ΣM about (px, py).
  List<_Term> _externalTerms(Iterable<String> nodes, String which,
      {double px = 0, double py = 0, String about = '', bool reactionsKnown = false}) {
    final set = nodes.toSet();
    final terms = <_Term>[];
    for (final r in s.reactions) {
      if (!set.contains(r.node)) continue;
      final at = p.node(r.node)!;
      final horizontal = r.axis == TrussAxis.x;
      double coef;
      double arm = 0;
      switch (which) {
        case 'x':
          if (!horizontal) continue;
          coef = 1;
        case 'y':
          if (horizontal) continue;
          coef = 1;
        default:
          coef = horizontal ? -(at.y - py) : (at.x - px);
          arm = horizontal ? (at.y - py).abs() : (at.x - px).abs();
          if (coef.abs() < 1e-12) continue;
      }
      final hl = [ReactionHighlight(r.id), if (which == 'm') JointHighlight(r.node)];
      if (reactionsKnown) {
        final v = s.reaction(r.id);
        if (v == 0) continue;
        final contrib = coef * v;
        terms.add(_Term.known(
          which == 'm' ? '${f(v.abs())} × ${l(arm)}' : f(v.abs()),
          contrib < 0 ? -1 : 1,
          contrib,
          explanation: t.termKnownReaction(r.symbol, fU(v)),
          highlights: hl,
        ));
      } else {
        final arrow = horizontal ? '→' : '↑';
        terms.add(_Term.unknown(
          which == 'm' ? '${r.symbol} × ${l(arm)}' : r.symbol,
          r.id,
          coef,
          explanation: which == 'm'
              ? t.termReactionMoment(r.symbol, lU(arm), about, coef > 0, coef > 0)
              : t.termReaction(r.symbol, arrow, coef > 0),
          highlights: hl,
        ));
      }
    }
    for (final load in p.loads) {
      if (!set.contains(load.node)) continue;
      final at = p.node(load.node)!;
      final name = 'P@${node(load.node)}';
      void add(double component, bool horizontal) {
        if (component.abs() < 1e-12) return;
        final arrow = horizontal ? arrowX(component) : arrowY(component);
        final hl = [LoadHighlight(load.id)];
        switch (which) {
          case 'x' when horizontal:
          case 'y' when !horizontal:
            terms.add(_Term.known(
              f(component.abs()),
              component < 0 ? -1 : 1,
              component,
              explanation: t.termLoad(name, fU(component.abs()), arrow, component > 0),
              highlights: hl,
            ));
          case 'm':
            final arm = horizontal ? (at.y - py) : (at.x - px);
            final moment = horizontal ? -arm * component : arm * component;
            if (moment.abs() < 1e-12) return;
            terms.add(_Term.known(
              '${f(component.abs())} × ${l(arm.abs())}',
              moment < 0 ? -1 : 1,
              moment,
              explanation: t.termLoadMoment(name, fU(component.abs()), lU(arm.abs()),
                  about, moment > 0, moment > 0),
              highlights: hl,
            ));
          default:
            break;
        }
      }

      add(load.fx, true);
      add(load.fy, false);
    }
    return terms;
  }

  SolutionStep reactions(Map<String, double> known) {
    final all = p.nodes.map((n) => n.id);
    final lines = <MathLine>[];
    final unknownIds = {for (final r in s.reactions) r.id};
    // Candidate equations: moments about each support's joint (the one
    // holding most reactions first), then ΣFx and ΣFy.
    final supportNodes = [...p.supports]..sort((a, b) {
        int count(TrussSupport x) =>
            s.reactions.where((r) => r.supportId == x.id).length;
        return count(b).compareTo(count(a));
      });
    final moments = <(_Eq, String?, String?)>[
      for (final sup in supportNodes)
        () {
          final at = p.node(sup.node)!;
          final letter = node(sup.node);
          return (
            _Eq('ΣM_$letter = 0',
                _externalTerms(all, 'm', px: at.x, py: at.y, about: letter),
                moment: true, headerHl: [JointHighlight(sup.node)]),
            letter,
            sup.node,
          );
        }(),
    ];
    // A textbook's order: moments about the pin (two reactions drop out),
    // then ΣFx, then ΣFy; the other moments only if those do not finish.
    final candidates = <(_Eq, String?, String?)>[
      if (moments.isNotEmpty) moments.first,
      (_Eq('ΣFx = 0', _externalTerms(all, 'x')), null, null),
      (_Eq('ΣFy = 0', _externalTerms(all, 'y')), null, null),
      ...moments.skip(1),
    ];
    final used = <int>{};
    var progressed = true;
    while (progressed && !unknownIds.every(known.containsKey)) {
      progressed = false;
      for (var i = 0; i < candidates.length; i++) {
        if (used.contains(i)) continue;
        final (eq, letter, centre) = candidates[i];
        final left = eq.unknowns.difference(known.keys.toSet());
        if (left.length != 1) continue;
        used.add(i);
        final id = left.single;
        final r = s.reactions.firstWhere((x) => x.id == id);
        final hl = [ReactionHighlight(id)];
        final convention = eq.moment ? '↺' : (eq.header.contains('Fx') ? '→' : '↑');
        lines.add(_header(eq, convention));
        // "Ax = 0" needs no solving: the equation is the answer.
        final bare = eq.terms.length == 1 && eq.coefOf(id).abs() == 1;
        if (!bare) lines.add(_equationLine(eq, known));
        final (solve, value) = _solveOne(eq, id, known, r.symbol, hl);
        lines.addAll(solve);
        // The reactions at the moment centre drop out of the equation.
        final through = [
          for (final x in s.reactions)
            if (x.node == centre) x.symbol,
        ];
        final last = lines.removeLast();
        lines.add(MathLine(last.tokens,
            note: eq.moment
                ? t.whyMoment(letter!, r.symbol, through.isEmpty ? ['—'] : through)
                : t.whyForce(eq.header.contains('Fx'), r.symbol)));
        known[id] = s.reaction(id);
        // Rounding in the step must not drift from the solver's answer.
        assert((value - s.reaction(id)).abs() <= 1e-6 * (1 + value.abs()));
        progressed = true;
        break;
      }
    }
    if (!unknownIds.every(known.containsKey)) {
      for (final r in s.reactions) {
        known[r.id] = s.reaction(r.id);
      }
      lines.add(MathLine([
        for (final r in s.reactions)
          MathToken(reactionResult(r).text,
              role: TokenRole.result, highlights: [ReactionHighlight(r.id)]),
      ], note: t.reactionsTogether));
    }
    return SolutionStep(
      kind: StepKind.trussReactions,
      title: t.reactionsTitle,
      goal: t.reactionsGoal([for (final r in s.reactions) r.symbol]),
      lines: lines,
      explanation: t.reactionsExplanation,
      highlights: [for (final r in s.reactions) ReactionHighlight(r.id)],
      reveal: Reveal(reactions: true, solved: {for (final r in s.reactions) r.id}),
      results: [for (final r in s.reactions) reactionResult(r)],
    );
  }

  // ---- method of joints --------------------------------------------------

  /// ΣFx or ΣFy at a joint: its members (unknown, or known by their value)
  /// and the loads and reactions there.
  _Eq _jointEq(String nodeId, bool x) {
    final at = p.node(nodeId)!;
    final terms = <_Term>[];
    for (final mem in p.membersAt(nodeId)) {
      final o = p.node(mem.other(nodeId))!;
      final dx = o.x - at.x, dy = o.y - at.y;
      final len = p.lengthOf(mem);
      final part = x ? dx : dy;
      if (part.abs() < 1e-12 * len) continue;
      final coef = part / len;
      final n = nameOf(mem);
      final straight = (x ? dy : dx).abs() < 1e-12 * len;
      final text = straight ? n : '$n·${ratio(part.abs(), dx, dy, len, cos: x)}';
      terms.add(_Term.unknown(
        text,
        mem.id,
        coef,
        explanation: t.termMember(n, node(nodeId), node(o.id),
            straight ? n : '$n × ${ratio(part.abs(), dx, dy, len, cos: x)}', coef > 0),
        highlights: [MemberHighlight(mem.id)],
      ));
    }
    terms.addAll(_externalTerms([nodeId], x ? 'x' : 'y', reactionsKnown: true));
    return _Eq(x ? 'ΣFx = 0' : 'ΣFy = 0', terms,
        headerHl: [JointHighlight(nodeId)]);
  }

  List<SolutionStep> joints() {
    final steps = <SolutionStep>[given(), determinacy()];
    final known = <String, double>{};
    steps.add(reactions(known));

    final unknownMembers = {for (final m in p.members) m.id};
    final usedJoints = <String>{};
    while (unknownMembers.isNotEmpty) {
      // A joint with one or two unknown members; one unknown first, then a
      // joint where one of the two equations has a single unknown.
      String? best;
      var bestScore = 1 << 30;
      for (final n in p.nodes) {
        final u = p.membersAt(n.id).where((m) => unknownMembers.contains(m.id)).length;
        if (u == 0 || u > 2) continue;
        final ex = _jointEq(n.id, true), ey = _jointEq(n.id, false);
        bool single(_Eq e) =>
            e.unknowns.where(unknownMembers.contains).length == 1;
        final score = u * 10 + (single(ex) || single(ey) ? 0 : 5);
        if (score < bestScore) {
          bestScore = score;
          best = n.id;
        }
      }
      if (best == null) break;
      steps.add(_jointStep(best, known, unknownMembers));
      usedJoints.add(best);
    }

    if (unknownMembers.isNotEmpty) {
      for (final id in unknownMembers) {
        known[id] = s.force(id);
      }
      steps.add(SolutionStep(
        kind: StepKind.trussJoint,
        title: t.remainingTitle,
        goal: '',
        lines: [
          for (final id in unknownMembers)
            MathLine([
              MathToken(memberResult(id).text,
                  role: TokenRole.result, highlights: [MemberHighlight(id)]),
            ]),
        ],
        explanation: t.remainingExplanation,
      ));
      unknownMembers.clear();
    }

    final check = _check(usedJoints, known);
    if (check != null) steps.add(check);
    steps.add(_summary());
    return steps;
  }

  SolutionStep _jointStep(
      String nodeId, Map<String, double> known, Set<String> unknownMembers) {
    final letter = node(nodeId);
    final ex = _jointEq(nodeId, true), ey = _jointEq(nodeId, false);
    final unknowns = [
      for (final m in p.membersAt(nodeId))
        if (unknownMembers.contains(m.id)) m,
    ]..sort((a, b) => labels.member(a).compareTo(labels.member(b)));
    final knownMembers = [
      for (final m in p.membersAt(nodeId))
        if (!unknownMembers.contains(m.id)) nameOf(m),
    ];
    final lines = <MathLine>[];

    bool single(_Eq e) =>
        e.unknowns.where(unknownMembers.contains).length == 1;

    void write(_Eq e) => lines
      ..add(_header(e, identical(e, ex) ? '→' : '↑'))
      ..add(_equationLine(e, known));

    void solveFrom(_Eq e, TrussMember m) {
      final hl = [MemberHighlight(m.id)];
      final (solve, _) = _solveOne(e, m.id, known, nameOf(m), hl);
      final last = solve.removeLast();
      final v = s.force(m.id);
      lines
        ..addAll(solve)
        ..add(MathLine([
          ...last.tokens,
          MathToken('(${v.abs() < 1e-9 ? t.zeroForce : (v > 0 ? 'T' : 'C')})',
              role: TokenRole.text),
        ], note: v < -1e-9 ? t.negativeMeansCompression(nameOf(m)) : null));
      known[m.id] = v;
      unknownMembers.remove(m.id);
    }

    /// The equation not used to solve anything, with every value in: it
    /// must come out zero.
    void confirm(_Eq e) {
      var sum = e.knownSum;
      for (final term in e.terms) {
        if (term.unknown != null) sum += term.coef * (known[term.unknown] ?? 0);
      }
      lines
        ..add(_header(e, identical(e, ex) ? '→' : '↑'))
        ..add(MathLine([
          ..._terms(e, known),
          const MathToken('=', role: TokenRole.equals),
          MathToken('${Num.compact(fd(sum))} ${Num.isZeroAt(fd(sum), 3) ? '✓' : '✗'}',
              role: TokenRole.result),
        ]));
    }

    if (unknowns.length == 1) {
      final m = unknowns.single;
      final first = ex.coefOf(m.id).abs() >= ey.coefOf(m.id).abs() ? ex : ey;
      final second = identical(first, ex) ? ey : ex;
      write(first);
      solveFrom(first, m);
      confirm(second);
    } else if (single(ex) || single(ey)) {
      final first = single(ex) ? ex : ey;
      final second = identical(first, ex) ? ey : ex;
      final a = unknowns.firstWhere((m) => first.unknowns.contains(m.id));
      write(first);
      solveFrom(first, a);
      final b = unknowns.firstWhere((m) => m.id != a.id);
      write(second);
      solveFrom(second, b);
    } else {
      // Two equations, two unknowns in each: solve them together.
      write(ex);
      write(ey);
      final results = <MathToken>[];
      for (final m in unknowns) {
        final v = s.force(m.id);
        results.add(MathToken(
            '${nameOf(m)} = ${fU(v)} (${v.abs() < 1e-9 ? t.zeroForce : (v > 0 ? 'T' : 'C')})',
            role: TokenRole.result,
            highlights: [MemberHighlight(m.id)]));
        known[m.id] = v;
        unknownMembers.remove(m.id);
      }
      lines.add(MathLine(results, note: t.solveTogether));
    }

    return SolutionStep(
      kind: StepKind.trussJoint,
      title: t.jointTitle(letter),
      goal: t.jointGoal([for (final m in unknowns) nameOf(m)]),
      lines: lines,
      explanation: t.jointExplanation(
          letter, [for (final m in unknowns) nameOf(m)], knownMembers),
      detail: '${t.jointDetail}\n${t.assumeTension}',
      highlights: [
        JointHighlight(nodeId),
        for (final m in unknowns) MemberHighlight(m.id),
      ],
      results: [for (final m in unknowns) memberResult(m.id)],
    );
  }

  /// ΣFx and ΣFy at a joint not used to solve anything: both must be zero.
  SolutionStep? _check(Set<String> used, Map<String, double> known) {
    final candidates = [
      for (final n in p.nodes)
        if (!used.contains(n.id)) n,
    ];
    if (candidates.isEmpty) return null;
    final n = candidates.last;
    final lines = <MathLine>[];
    for (final x in [true, false]) {
      final eq = _jointEq(n.id, x);
      var sum = eq.knownSum;
      for (final term in eq.terms) {
        if (term.unknown != null) sum += term.coef * known[term.unknown]!;
      }
      final ok = Num.isZeroAt(fd(sum), 3);
      lines
        ..add(_header(eq, x ? '→' : '↑'))
        ..add(MathLine([
          ..._terms(eq, known),
          const MathToken('=', role: TokenRole.equals),
          MathToken('${Num.compact(fd(sum))} ${ok ? '✓' : '✗'}',
              role: TokenRole.result),
        ]));
    }
    return SolutionStep(
      kind: StepKind.trussCheck,
      title: '${t.checkTitle}: ${t.jointTitle(node(n.id))}',
      goal: '',
      lines: lines,
      explanation: t.checkExplanation(node(n.id)),
      highlights: [JointHighlight(n.id)],
    );
  }

  SolutionStep _summary() {
    final members = [...p.members]
      ..sort((a, b) => labels.member(a).compareTo(labels.member(b)));
    var tension = 0, compression = 0, zero = 0;
    for (final m in members) {
      final v = s.force(m.id);
      if (v.abs() < 1e-9) {
        zero++;
      } else if (v > 0) {
        tension++;
      } else {
        compression++;
      }
    }
    return SolutionStep(
      kind: StepKind.trussMembers,
      title: t.summaryTitle,
      goal: t.summaryGoal,
      lines: [
        for (final m in members)
          MathLine([
            MathToken(memberResult(m.id).text,
                role: TokenRole.result, highlights: [MemberHighlight(m.id)]),
          ]),
      ],
      explanation: t.summaryExplanation(tension, compression, zero),
      highlights: [for (final m in members) MemberHighlight(m.id)],
      results: [for (final m in members) memberResult(m.id)],
    );
  }

  // ---- method of sections ------------------------------------------------

  TrussSection section(List<String> cutIds, {required bool otherSide}) {
    final cut = [
      for (final id in cutIds)
        if (p.member(id) != null) id,
    ]..sort((a, b) =>
        labels.member(p.member(a)!).compareTo(labels.member(p.member(b)!)));
    TrussSection invalid(bool separates, [Set<String> side = const {}]) =>
        TrussSection(
          cut: cut,
          side: side,
          steps: const [],
          error: s.isSolved
              ? t.sectionInvalid(cut.length, separates)
              : t.stabilityMessage(s.stability),
        );
    if (!s.isSolved || cut.isEmpty || cut.length > 3) return invalid(true);

    // The parts left when the cut members are removed.
    final parent = {for (final n in p.nodes) n.id: n.id};
    String find(String a) {
      while (parent[a] != a) {
        parent[a] = parent[parent[a]]!;
        a = parent[a]!;
      }
      return a;
    }

    for (final m in p.members) {
      if (cut.contains(m.id)) continue;
      parent[find(m.a)] = find(m.b);
    }
    final leftmost = [...p.nodes]..sort((a, b) {
        final byX = a.x.compareTo(b.x);
        return byX != 0 ? byX : a.y.compareTo(b.y);
      });
    final root = find(leftmost.first.id);
    final left = {
      for (final n in p.nodes)
        if (find(n.id) == root) n.id,
    };
    final side = otherSide
        ? {for (final n in p.nodes) if (!left.contains(n.id)) n.id}
        : left;
    final crosses = cut.every((id) {
      final m = p.member(id)!;
      return side.contains(m.a) != side.contains(m.b);
    });
    if (side.isEmpty || side.length == p.nodes.length || !crosses) {
      return invalid(false, side);
    }

    final sideNames = [for (final n in p.nodes) if (side.contains(n.id)) node(n.id)];
    final cutNames = [for (final id in cut) name(id)];

    // Each cut member pulls its joint on this side towards the other side.
    ({double qx, double qy, double ux, double uy}) lineOf(String id) {
      final m = p.member(id)!;
      final q = p.node(side.contains(m.a) ? m.a : m.b)!;
      final o = p.node(m.other(q.id))!;
      final len = p.lengthOf(m);
      return (qx: q.x, qy: q.y, ux: (o.x - q.x) / len, uy: (o.y - q.y) / len);
    }

    final points = <(String, double, double)>[];
    final steps = <SolutionStep>[
      SolutionStep(
        kind: StepKind.trussSection,
        title: t.sectionTitle(cutNames),
        goal: t.sectionGoal,
        lines: [
          MathLine([
            for (final id in cut)
              MathToken(name(id),
                  role: TokenRole.term, highlights: [MemberHighlight(id)]),
          ]),
          MathLine([
            for (final id in side)
              MathToken(node(id),
                  role: TokenRole.value, highlights: [JointHighlight(id)]),
          ]),
        ],
        explanation: t.sectionExplanation(cutNames, sideNames),
        detail: t.sectionDetail,
        highlights: [for (final id in cut) MemberHighlight(id)],
      ),
    ];

    for (final id in cut) {
      final others = [for (final o in cut) if (o != id) o];
      _Eq? eq;
      String? why;
      String? pointNote;
      List<Highlight> extra = const [];
      final me = lineOf(id);

      _Eq momentAbout(double px, double py, String label) {
        final terms = <_Term>[];
        final arm = (me.qx - px) * me.uy - (me.qy - py) * me.ux;
        terms.add(_Term.unknown(
          '${name(id)} × ${l(arm.abs())}',
          id,
          arm,
          explanation: t.termCutMember(name(id), lU(arm.abs()), arm > 0),
          highlights: [MemberHighlight(id)],
        ));
        terms.addAll(_externalTerms(side, 'm',
            px: px, py: py, about: label, reactionsKnown: true));
        return _Eq('ΣM_$label = 0', terms,
            moment: true, headerHl: [PlanePointHighlight(px, py)]);
      }

      _Eq forceEq(bool horizontal) {
        final part = horizontal ? me.ux : me.uy;
        final m = p.member(id)!;
        final o = p.node(m.other(side.contains(m.a) ? m.a : m.b))!;
        final q = p.node(side.contains(m.a) ? m.a : m.b)!;
        final dx = o.x - q.x, dy = o.y - q.y, len = p.lengthOf(m);
        final straight = (horizontal ? dy : dx).abs() < 1e-12 * len;
        final text = straight
            ? name(id)
            : '${name(id)}·${ratio((horizontal ? dx : dy).abs(), dx, dy, len, cos: horizontal)}';
        return _Eq(horizontal ? 'ΣFx = 0' : 'ΣFy = 0', [
          _Term.unknown(text, id, part,
              explanation: t.termCutMember(name(id), '—', part > 0),
              highlights: [MemberHighlight(id)]),
          ..._externalTerms(side, horizontal ? 'x' : 'y', reactionsKnown: true),
        ]);
      }

      String pointName(double px, double py) {
        final atJoint = p.nodeNear(px, py, 1e-6);
        if (atJoint != null) return node(atJoint.id);
        for (final (n, x, y) in points) {
          if ((x - px).abs() < 1e-9 && (y - py).abs() < 1e-9) return n;
        }
        final n = points.isEmpty ? 'O' : 'O${points.length + 1}';
        points.add((n, px, py));
        return n;
      }

      if (others.length == 2) {
        final a = lineOf(others[0]), b = lineOf(others[1]);
        final cross = a.ux * b.uy - a.uy * b.ux;
        if (cross.abs() > 1e-9) {
          final tt = ((b.qx - a.qx) * b.uy - (b.qy - a.qy) * b.ux) / cross;
          final px = a.qx + a.ux * tt, py = a.qy + a.uy * tt;
          final label = pointName(px, py);
          eq = momentAbout(px, py, label);
          why = t.sectionWhyMoment(label, name(id), [for (final o in others) name(o)]);
          if (p.nodeNear(px, py, 1e-6) == null) {
            pointNote = t.intersectionPoint(label, l(px), l(py),
                [for (final o in others) name(o)]);
          }
          extra = [PlanePointHighlight(px, py)];
        } else if (a.uy.abs() < 1e-9) {
          eq = forceEq(false);
          why = t.sectionWhyForce(false, name(id), [for (final o in others) name(o)]);
        } else if (a.ux.abs() < 1e-9) {
          eq = forceEq(true);
          why = t.sectionWhyForce(true, name(id), [for (final o in others) name(o)]);
        }
      } else if (others.length == 1) {
        final o = p.member(others.single)!;
        // A point on the other member's line that is not on this one's.
        for (final end in [o.a, o.b]) {
          final n = p.node(end)!;
          final arm = (me.qx - n.x) * me.uy - (me.qy - n.y) * me.ux;
          if (arm.abs() > 1e-9) {
            final label = node(end);
            eq = momentAbout(n.x, n.y, label);
            why = t.sectionWhyMoment(label, name(id), [name(others.single)]);
            extra = [PlanePointHighlight(n.x, n.y)];
            break;
          }
        }
      } else {
        eq = forceEq(me.ux.abs() >= me.uy.abs());
      }

      final hl = [MemberHighlight(id)];
      final v = s.force(id);
      final lines = <MathLine>[];
      if (eq == null) {
        lines.add(MathLine([
          MathToken(memberResult(id).text, role: TokenRole.result, highlights: hl),
        ], note: t.reactionsTogether));
      } else {
        final convention =
            eq.moment ? '↺' : (eq.header.contains('Fx') ? '→' : '↑');
        lines
          ..add(MathLine(_header(eq, convention).tokens, note: pointNote))
          ..add(_equationLine(eq, const {}));
        final (solve, value) = _solveOne(eq, id, const {}, name(id), hl);
        assert((value - v).abs() <= 1e-6 * (1 + v.abs()));
        final last = solve.removeLast();
        lines
          ..addAll(solve)
          ..add(MathLine([
            ...last.tokens,
            MathToken('(${v.abs() < 1e-9 ? t.zeroForce : (v > 0 ? 'T' : 'C')})',
                role: TokenRole.text),
          ], note: v < -1e-9 ? t.negativeMeansCompression(name(id)) : null));
      }
      steps.add(SolutionStep(
        kind: StepKind.trussSection,
        title: t.sectionStepTitle(name(id)),
        goal: eq?.header ?? '',
        lines: lines,
        explanation: why ?? t.reactionsTogether,
        highlights: [...hl, ...extra],
        results: [memberResult(id)],
      ));
    }

    steps.add(SolutionStep(
      kind: StepKind.trussMembers,
      title: t.summaryTitle,
      goal: '',
      lines: [
        for (final id in cut)
          MathLine([
            MathToken(memberResult(id).text,
                role: TokenRole.result, highlights: [MemberHighlight(id)]),
          ]),
      ],
      explanation: t.sectionSameAsJoints,
      results: [for (final id in cut) memberResult(id)],
    ));
    return TrussSection(cut: cut, side: side, steps: steps, points: points);
  }
}
