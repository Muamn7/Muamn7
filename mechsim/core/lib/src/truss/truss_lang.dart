/// The words of the truss explanations, in Arabic and English.
library;

import '../explain/lang.dart';
import 'truss_solver.dart';

abstract class TrussTexts {
  const TrussTexts();

  static TrussTexts of(Lang lang) =>
      lang == Lang.ar ? const _Ar() : const _En();

  /// Wraps Latin and mathematics inside Arabic so it keeps its order.
  String m(String s) => s;

  // problem and determinacy
  String get givenTitle;
  String get givenGoal;
  String givenExplanation(int joints, int members, int loads);
  String get determinacyTitle;
  String get determinacyGoal;
  String determinacyExplanation(int m, int r, int j);
  String get determinacyDetail;
  String unsolvableTitle(TrussReason reason);
  String stabilityMessage(TrussStability s);
  String stabilityAdvice(TrussReason reason);

  // reactions
  String get reactionsTitle;
  String reactionsGoal(List<String> symbols);
  String get reactionsExplanation;
  String whyMoment(String point, String target, List<String> through);
  String whyForce(bool horizontal, String target);
  String get reactionsTogether;
  String termReaction(String symbol, String arrow, bool positive);
  String termKnownReaction(String symbol, String value);
  String termLoad(String name, String value, String arrow, bool positive);
  String termLoadMoment(String name, String value, String arm, String about,
      bool counterClockwise, bool positive);
  String termReactionMoment(String symbol, String arm, String about,
      bool counterClockwise, bool positive);

  // joints
  String jointTitle(String joint);
  String jointGoal(List<String> unknowns);
  String jointExplanation(String joint, List<String> unknowns,
      List<String> known);
  String get jointDetail;
  String termMember(String name, String joint, String other, String part,
      bool positive);
  String termKnownMember(String name, String value);
  String get solveTogether;
  String get tension;
  String get compression;
  String get zeroForce;
  String get assumeTension;
  String negativeMeansCompression(String name);
  String get remainingTitle;
  String get remainingExplanation;
  String get checkTitle;
  String checkExplanation(String joint);
  String get summaryTitle;
  String get summaryGoal;
  String summaryExplanation(int tension, int compression, int zero);

  // sections
  String sectionTitle(List<String> cut);
  String get sectionGoal;
  String sectionExplanation(List<String> cut, List<String> side);
  String get sectionDetail;
  String sectionInvalid(int count, bool separates);
  String sectionStepTitle(String target);
  String sectionWhyMoment(String point, String target, List<String> through);
  String sectionWhyForce(bool horizontal, String target, List<String> others);
  String intersectionPoint(String name, String x, String y, List<String> of);
  String termCutMember(String name, String arm, bool positive);
  String get sectionSameAsJoints;
  String get leftPart;
  String get rightPart;
}

String _sign(bool positive, Lang lang) => lang == Lang.ar
    ? (positive ? 'موجبة' : 'سالبة')
    : (positive ? 'positive' : 'negative');

class _Ar extends TrussTexts {
  const _Ar();

  @override
  String m(String s) => '\u2066$s\u2069';

  @override
  String get givenTitle => 'المسألة';
  @override
  String get givenGoal => 'المعطيات';
  @override
  String givenExplanation(int joints, int members, int loads) =>
      'جملون مستوٍ من ${m('$joints')} وصلات و${m('$members')} عضوًا، عليه ${m('$loads')} حمل على الوصلات. '
      'كل عضو مثبّت بمسمار في طرفيه، فلا ينقل إلا قوة على امتداده: شد أو ضغط.';
  @override
  String get determinacyTitle => 'هل الجملون مستقر ومحدد؟';
  @override
  String get determinacyGoal => 'نعدّ الأعضاء وردود الأفعال والوصلات';
  @override
  String determinacyExplanation(int m_, int r, int j) =>
      'لكل وصلة معادلتان (ΣFx = 0 وΣFy = 0)، فعدد المعادلات ${m('2j = ${2 * j}')}. '
      'والمجاهيل هي قوى الأعضاء وردود الأفعال: ${m('m + r = $m_ + $r = ${m_ + r}')}. '
      'العددان متساويان، والأعضاء مرتبة بمثلثات، فالجملون مستقر ومحدد استاتيكيًا.';
  @override
  String get determinacyDetail =>
      'القاعدة: m + r = 2j جملون محدد، وm + r < 2j جملون غير مستقر يمكن أن ينهار، وm + r > 2j جملون غير محدد يحتاج معادلات التشوه.';
  @override
  String unsolvableTitle(TrussReason reason) => switch (reason) {
        TrussReason.indeterminate => 'الجملون غير محدد استاتيكيًا',
        TrussReason.empty || TrussReason.zeroLength => 'المسألة غير مكتملة',
        _ => 'الجملون غير مستقر',
      };
  @override
  String stabilityMessage(TrussStability s) => switch (s.reason) {
        TrussReason.empty =>
          'ارسم الوصلات (Joint) ثم الأعضاء (Member) بينها، أو اختر قالبًا جاهزًا.',
        TrussReason.zeroLength => 'يوجد عضو طوله صفر: طرفاه في النقطة نفسها.',
        TrussReason.freeJoint =>
          'توجد وصلة لا يتصل بها أي عضو، فلا شيء يمسكها.',
        TrussReason.noSupports =>
          'لا توجد مساند، فالجملون كله سيتحرك. ضع Pin على وصلة وRoller على أخرى.',
        TrussReason.mechanism =>
          'المجاهيل ${m('m + r = ${s.members + s.reactions}')} لا تكفي لـ ${m('2j = ${2 * s.joints}')} معادلة، '
              'أو الأعضاء ليست مثلثات: الجملون يمكن أن يتشوه أو يتحرك (آلية).',
        TrussReason.indeterminate =>
          'المجاهيل ${m('m + r = ${s.members + s.reactions}')} أكثر من ${m('2j = ${2 * s.joints}')} معادلة بـ ${m('${s.degree}')}: '
              'الجملون غير محدد استاتيكيًا، وحله يحتاج معادلات التشوه.',
        TrussReason.ok => '',
      };
  @override
  String stabilityAdvice(TrussReason reason) => switch (reason) {
        TrussReason.mechanism =>
          'الحل: قسّم الجملون إلى مثلثات (أضف عضوًا قطريًا في كل مستطيل)، وتأكد من Pin وRoller.',
        TrussReason.indeterminate => 'الحل: احذف عضوًا زائدًا أو استبدل Pin بـ Roller.',
        TrussReason.noSupports => 'الترتيب المعتاد: Pin في طرف وRoller في الطرف الآخر.',
        _ => '',
      };

  @override
  String get reactionsTitle => 'ردود الأفعال — اتزان الجملون كله';
  @override
  String reactionsGoal(List<String> symbols) => 'إيجاد ${m(symbols.join('، '))}';
  @override
  String get reactionsExplanation =>
      'نبدأ بالجملون كله كجسم واحد: القوى الداخلية في الأعضاء تلغي بعضها، فلا يبقى إلا الأحمال وردود الأفعال. '
      'ثلاث معادلات اتزان تكفي لإيجاد ثلاثة ردود أفعال.';
  @override
  String whyMoment(String point, String target, List<String> through) =>
      'نأخذ العزوم حول ${m(point)} لأن ${m(through.join(' و'))} تمر به فعزمها صفر، فيبقى ${m(target)} وحده في المعادلة.';
  @override
  String whyForce(bool horizontal, String target) => horizontal
      ? 'مجموع القوى الأفقية صفر، والمجهول الأفقي الوحيد هو ${m(target)}.'
      : 'مجموع القوى الرأسية صفر، والمجهول الرأسي الباقي هو ${m(target)}.';
  @override
  String get reactionsTogether =>
      'هذه المساند لا تعطي ثلاثة ردود أفعال يمكن إيجادها من الجملون كله، فوجدناها مع قوى الأعضاء من معادلات كل الوصلات معًا.';
  @override
  String termReaction(String symbol, String arrow, bool positive) =>
      '${m(symbol)} رد الفعل، افترضناه $arrow، لذلك إشارته ${_sign(positive, Lang.ar)} في هذه المعادلة.';
  @override
  String termKnownReaction(String symbol, String value) =>
      '${m('$symbol = $value')} وجدناه في خطوة سابقة، فنعوّض بقيمته.';
  @override
  String termLoad(String name, String value, String arrow, bool positive) =>
      '${m(name)} حمل قيمته ${m(value)} واتجاهه $arrow، لذلك إشارته ${_sign(positive, Lang.ar)}.';
  @override
  String termLoadMoment(String name, String value, String arm, String about,
          bool counterClockwise, bool positive) =>
      '${m(name)} = ${m(value)} وذراعه ${m(arm)} حول ${m(about)}، فيدير الجملون '
      '${counterClockwise ? 'عكس عقارب الساعة ↺' : 'مع عقارب الساعة ↻'}: إشارته ${_sign(positive, Lang.ar)}.';
  @override
  String termReactionMoment(String symbol, String arm, String about,
          bool counterClockwise, bool positive) =>
      '${m(symbol)} رد فعل ذراعه ${m(arm)} حول ${m(about)}، يدير الجملون '
      '${counterClockwise ? 'عكس عقارب الساعة ↺' : 'مع عقارب الساعة ↻'}: إشارته ${_sign(positive, Lang.ar)}.';

  @override
  String jointTitle(String joint) => 'الوصلة ${m(joint)}';
  @override
  String jointGoal(List<String> unknowns) => 'إيجاد ${m(unknowns.join(' و'))}';
  @override
  String jointExplanation(String joint, List<String> unknowns,
          List<String> known) =>
      'نختار الوصلة ${m(joint)} لأن فيها ${unknowns.length == 1 ? 'مجهولًا واحدًا' : 'مجهولين فقط'} '
      '(${m(unknowns.join('، '))})${known.isEmpty ? '' : '، والباقي معروف (${m(known.join('، '))})'}. '
      'الوصلة مسمار في حالة اتزان، فلها معادلتان: ΣFx = 0 وΣFy = 0.';
  @override
  String get jointDetail =>
      'كل عضو يؤثر على الوصلة بقوة على امتداده. نفترضها شدًا: تسحب الوصلة نحو الطرف الآخر للعضو. '
      'نحلل كل قوة إلى مركّبتين: الأفقية = F × cos θ والرأسية = F × sin θ، حيث θ زاوية العضو مع الأفقي.';
  @override
  String termMember(String name, String joint, String other, String part,
          bool positive) =>
      '${m(name)} قوة العضو. افترضناها شدًا فتسحب الوصلة ${m(joint)} نحو ${m(other)}؛ مركّبتها هنا ${m(part)}، وإشارتها ${_sign(positive, Lang.ar)}.';
  @override
  String termKnownMember(String name, String value) =>
      '${m('$name = $value')} وجدناها من وصلة سابقة، فنعوّض بقيمتها (بإشارتها).';
  @override
  String get solveTogether => 'المجهولان في المعادلتين معًا، فنحلهما معًا';
  @override
  String get tension => 'شد (T)';
  @override
  String get compression => 'ضغط (C)';
  @override
  String get zeroForce => 'عضو صفري';
  @override
  String get assumeTension =>
      'نفترض كل قوى الأعضاء شدًا (تسحب الوصلة). إذا خرجت سالبة فالعضو في حالة ضغط.';
  @override
  String negativeMeansCompression(String name) =>
      'الإشارة السالبة تعني أن ${m(name)} يدفع الوصلة بدل أن يسحبها: العضو في حالة ضغط (C).';
  @override
  String get remainingTitle => 'الأعضاء الباقية';
  @override
  String get remainingExplanation =>
      'لم تبقَ وصلة فيها مجهولان فقط، فوجدنا الباقي من معادلات كل الوصلات معًا.';
  @override
  String get checkTitle => 'تحقق';
  @override
  String checkExplanation(String joint) =>
      'كل قوى الوصلة ${m(joint)} صارت معروفة ولم نستعملها، فإذا تحققت معادلتاها كان الحل صحيحًا.';
  @override
  String get summaryTitle => 'قوى الأعضاء';
  @override
  String get summaryGoal => 'كل عضو: قيمته، شد أم ضغط';
  @override
  String summaryExplanation(int tension, int compression, int zero) =>
      'في الجملون ${m('$tension')} أعضاء في حالة شد و${m('$compression')} في حالة ضغط'
      '${zero == 0 ? '' : ' و${m('$zero')} أعضاء صفرية (قوتها صفر تحت هذه الأحمال، لكنها تمنع الجملون من التشوه)'}.';

  @override
  String sectionTitle(List<String> cut) => 'المقطع عبر ${m(cut.join('، '))}';
  @override
  String get sectionGoal => 'نقطع الجملون ونأخذ جزءًا واحدًا';
  @override
  String sectionExplanation(List<String> cut, List<String> side) =>
      'نقطع الأعضاء ${m(cut.join('، '))} فينفصل الجملون إلى جزأين، ونأخذ الجزء الذي فيه الوصلات ${m(side.join('، '))}. '
      'قوى الأعضاء المقطوعة تصبح قوى خارجية على هذا الجزء، والجزء في حالة اتزان: ثلاث معادلات لثلاثة مجاهيل على الأكثر.';
  @override
  String get sectionDetail =>
      'الحيلة: نأخذ العزوم حول نقطة تقاطع خطي عضوين مقطوعين، فيختفي عزماهما ويبقى الثالث وحده. '
      'هكذا نجد قوة أي عضو مباشرة دون المرور بكل الوصلات.';
  @override
  String sectionInvalid(int count, bool separates) => count == 0
      ? 'اضغط على الأعضاء التي تريد قطعها (حتى 3) لترسم المقطع.'
      : count > 3
          ? 'المقطع يقطع ${m('$count')} أعضاء: لا يمكن إيجاد أكثر من 3 مجاهيل من ثلاث معادلات.'
          : !separates
              ? 'هذه الأعضاء لا تفصل الجملون إلى جزأين. اختر أعضاء يمر بها خط واحد يقسم الجملون.'
              : 'لا يمكن الحل بهذا المقطع.';
  @override
  String sectionStepTitle(String target) => 'إيجاد ${m(target)}';
  @override
  String sectionWhyMoment(String point, String target, List<String> through) =>
      'نأخذ العزوم حول ${m(point)} لأن خطوط عمل ${m(through.join(' و'))} تمر بها فعزمها صفر، فيبقى ${m(target)} وحده.';
  @override
  String sectionWhyForce(bool horizontal, String target, List<String> others) =>
      '${m(others.join(' و'))} ${horizontal ? 'رأسية' : 'أفقية'} فلا تظهر في ${horizontal ? 'ΣFx' : 'ΣFy'}، فيبقى ${m(target)} وحده.';
  @override
  String intersectionPoint(String name, String x, String y, List<String> of) =>
      '${m(name)} نقطة تقاطع امتدادَي ${m(of.join(' و'))}، عند ${m('($x, $y)')}.';
  @override
  String termCutMember(String name, String arm, bool positive) =>
      '${m(name)} قوة العضو المقطوع، نفترضها شدًا (تسحب الجزء نحو الجزء الآخر)، وذراعها العمودي ${m(arm)}: إشارتها ${_sign(positive, Lang.ar)}.';
  @override
  String get sectionSameAsJoints =>
      'نفس النتائج التي وجدناها بطريقة الوصلات ✓ — لكن بمعادلة واحدة لكل عضو.';
  @override
  String get leftPart => 'الجزء الأيسر';
  @override
  String get rightPart => 'الجزء الأيمن';
}

class _En extends TrussTexts {
  const _En();

  @override
  String get givenTitle => 'The problem';
  @override
  String get givenGoal => 'What is given';
  @override
  String givenExplanation(int joints, int members, int loads) =>
      'A plane truss of $joints joints and $members members carrying $loads loads at its joints. '
      'Each member is pinned at both ends, so it carries only a force along its own line: tension or compression.';
  @override
  String get determinacyTitle => 'Is the truss stable and determinate?';
  @override
  String get determinacyGoal => 'Count members, reactions and joints';
  @override
  String determinacyExplanation(int m, int r, int j) =>
      'Each joint gives two equations (ΣFx = 0 and ΣFy = 0): 2j = ${2 * j}. '
      'The unknowns are the member forces and the reactions: m + r = $m + $r = ${m + r}. '
      'They match and the members form triangles, so the truss is stable and statically determinate.';
  @override
  String get determinacyDetail =>
      'The rule: m + r = 2j determinate; m + r < 2j unstable, it can collapse; m + r > 2j indeterminate, it needs deformations.';
  @override
  String unsolvableTitle(TrussReason reason) => switch (reason) {
        TrussReason.indeterminate => 'The truss is statically indeterminate',
        TrussReason.empty || TrussReason.zeroLength => 'The problem is incomplete',
        _ => 'The truss is unstable',
      };
  @override
  String stabilityMessage(TrussStability s) => switch (s.reason) {
        TrussReason.empty =>
          'Place joints, then members between them, or start from a template.',
        TrussReason.zeroLength => 'A member has zero length: both ends at one point.',
        TrussReason.freeJoint => 'A joint has no member, so nothing holds it.',
        TrussReason.noSupports =>
          'There are no supports, so the whole truss would move. Put a pin at one joint and a roller at another.',
        TrussReason.mechanism =>
          'm + r = ${s.members + s.reactions} unknowns are not enough for 2j = ${2 * s.joints} equations, '
              'or the members do not form triangles: the truss can deform or move (a mechanism).',
        TrussReason.indeterminate =>
          'm + r = ${s.members + s.reactions} unknowns are more than 2j = ${2 * s.joints} equations by ${s.degree}: '
              'the truss is statically indeterminate and needs deformations to solve.',
        TrussReason.ok => '',
      };
  @override
  String stabilityAdvice(TrussReason reason) => switch (reason) {
        TrussReason.mechanism =>
          'Fix: divide the truss into triangles (a diagonal in every rectangle), with a pin and a roller.',
        TrussReason.indeterminate => 'Fix: remove a redundant member or turn a pin into a roller.',
        TrussReason.noSupports => 'The usual set-up: a pin at one end and a roller at the other.',
        _ => '',
      };

  @override
  String get reactionsTitle => 'Reactions — the whole truss';
  @override
  String reactionsGoal(List<String> symbols) => 'Find ${symbols.join(', ')}';
  @override
  String get reactionsExplanation =>
      'Start with the whole truss as one body: the member forces inside it cancel in pairs, leaving only the loads and the reactions. '
      'Three equilibrium equations give three reactions.';
  @override
  String whyMoment(String point, String target, List<String> through) =>
      'Take moments about $point: ${through.join(' and ')} pass through it, so their moment is zero and $target is left alone.';
  @override
  String whyForce(bool horizontal, String target) => horizontal
      ? 'The horizontal forces add up to zero, and $target is the only horizontal unknown.'
      : 'The vertical forces add up to zero, and $target is the vertical unknown left.';
  @override
  String get reactionsTogether =>
      'These supports do not give three reactions the whole truss can find, so they were found with the member forces from all the joint equations together.';
  @override
  String termReaction(String symbol, String arrow, bool positive) =>
      '$symbol is the reaction, assumed $arrow, so it is ${_sign(positive, Lang.en)} in this equation.';
  @override
  String termKnownReaction(String symbol, String value) =>
      '$symbol = $value was found in an earlier step, so its value is substituted.';
  @override
  String termLoad(String name, String value, String arrow, bool positive) =>
      '$name is a load of $value acting $arrow, so it is ${_sign(positive, Lang.en)}.';
  @override
  String termLoadMoment(String name, String value, String arm, String about,
          bool counterClockwise, bool positive) =>
      '$name = $value with arm $arm about $about turns the truss '
      '${counterClockwise ? 'counter-clockwise ↺' : 'clockwise ↻'}: ${_sign(positive, Lang.en)}.';
  @override
  String termReactionMoment(String symbol, String arm, String about,
          bool counterClockwise, bool positive) =>
      '$symbol, a reaction with arm $arm about $about, turns the truss '
      '${counterClockwise ? 'counter-clockwise ↺' : 'clockwise ↻'}: ${_sign(positive, Lang.en)}.';

  @override
  String jointTitle(String joint) => 'Joint $joint';
  @override
  String jointGoal(List<String> unknowns) => 'Find ${unknowns.join(' and ')}';
  @override
  String jointExplanation(String joint, List<String> unknowns,
          List<String> known) =>
      'Joint $joint has ${unknowns.length == 1 ? 'one unknown' : 'only two unknowns'} '
      '(${unknowns.join(', ')})${known.isEmpty ? '' : ', the rest is known (${known.join(', ')})'}. '
      'The joint is a pin in equilibrium, which gives two equations: ΣFx = 0 and ΣFy = 0.';
  @override
  String get jointDetail =>
      'Each member pushes or pulls on the joint along its own line. Assume tension: it pulls the joint towards the member\'s other end. '
      'Resolve each force: horizontal part F × cos θ, vertical part F × sin θ, θ being the member\'s angle with the horizontal.';
  @override
  String termMember(String name, String joint, String other, String part,
          bool positive) =>
      '$name is the member force. Assumed tension, it pulls joint $joint towards $other; its part here is $part, ${_sign(positive, Lang.en)}.';
  @override
  String termKnownMember(String name, String value) =>
      '$name = $value was found at an earlier joint, so its value (with its sign) is substituted.';
  @override
  String get solveTogether => 'Both unknowns appear in both equations: solve them together';
  @override
  String get tension => 'tension (T)';
  @override
  String get compression => 'compression (C)';
  @override
  String get zeroForce => 'zero-force member';
  @override
  String get assumeTension =>
      'Every member force is assumed to be tension (pulling on the joint). A negative result means compression.';
  @override
  String negativeMeansCompression(String name) =>
      'The minus sign means $name pushes on the joint instead of pulling: the member is in compression (C).';
  @override
  String get remainingTitle => 'The remaining members';
  @override
  String get remainingExplanation =>
      'No joint is left with only two unknowns, so the rest were found from all the joint equations together.';
  @override
  String get checkTitle => 'Check';
  @override
  String checkExplanation(String joint) =>
      'Every force at joint $joint is now known and this joint was not used: if its equations hold, the answer is right.';
  @override
  String get summaryTitle => 'Member forces';
  @override
  String get summaryGoal => 'Each member: its force, tension or compression';
  @override
  String summaryExplanation(int tension, int compression, int zero) =>
      'The truss has $tension members in tension and $compression in compression'
      '${zero == 0 ? '' : ', and $zero zero-force members (no force under these loads, but they keep the truss from deforming)'}.';

  @override
  String sectionTitle(List<String> cut) => 'A section through ${cut.join(', ')}';
  @override
  String get sectionGoal => 'Cut the truss and keep one part';
  @override
  String sectionExplanation(List<String> cut, List<String> side) =>
      'Cut members ${cut.join(', ')}: the truss falls into two parts, and we keep the one with joints ${side.join(', ')}. '
      'The cut members\' forces become external forces on this part, which is in equilibrium: three equations for at most three unknowns.';
  @override
  String get sectionDetail =>
      'The trick: take moments about the point where the lines of two cut members meet; their moments vanish and the third is left alone. '
      'That finds any member\'s force directly, without going joint by joint.';
  @override
  String sectionInvalid(int count, bool separates) => count == 0
      ? 'Tap the members you want to cut (up to 3) to make the section.'
      : count > 3
          ? 'The section cuts $count members: three equations cannot find more than 3 unknowns.'
          : !separates
              ? 'These members do not split the truss in two. Choose members a single line crossing the truss would cut.'
              : 'This section cannot be solved.';
  @override
  String sectionStepTitle(String target) => 'Find $target';
  @override
  String sectionWhyMoment(String point, String target, List<String> through) =>
      'Take moments about $point: the lines of ${through.join(' and ')} pass through it, so their moments are zero and $target is left alone.';
  @override
  String sectionWhyForce(bool horizontal, String target, List<String> others) =>
      '${others.join(' and ')} ${horizontal ? 'are vertical' : 'are horizontal'}, so they do not appear in ${horizontal ? 'ΣFx' : 'ΣFy'}: $target is left alone.';
  @override
  String intersectionPoint(String name, String x, String y, List<String> of) =>
      '$name is where the lines of ${of.join(' and ')} meet, at ($x, $y).';
  @override
  String termCutMember(String name, String arm, bool positive) =>
      '$name is the cut member\'s force, assumed tension (pulling this part towards the other), with perpendicular arm $arm: ${_sign(positive, Lang.en)}.';
  @override
  String get sectionSameAsJoints =>
      'The same results as the method of joints ✓ — with one equation per member.';
  @override
  String get leftPart => 'the left part';
  @override
  String get rightPart => 'the right part';
}
