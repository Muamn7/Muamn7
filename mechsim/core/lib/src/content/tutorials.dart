/// Tutorials: short lessons on the ideas the solver uses, each with a figure
/// drawn from a real problem by the same renderer as the editor.
library;

import '../explain/lang.dart';
import '../model/beam_problem.dart';
import 'examples.dart';

/// What a tutorial figure shows.
enum FigureKind { beam, freeBody, shear, moment }

class TutorialSection {
  const TutorialSection(this.heading, this.body, {this.figure, this.figureKind = FigureKind.beam});

  final String heading;
  final String body;
  final BeamProblem? figure;
  final FigureKind figureKind;
}

class Tutorial {
  const Tutorial(this.id, this.title, this.summary, this.sections);

  final String id;
  final String title;
  final String summary;
  final List<TutorialSection> sections;
}

abstract final class Tutorials {
  static List<Tutorial> all(Lang lang) => lang == Lang.ar ? _ar : _en;

  static BeamProblem get _central => ExampleLibrary.byId('central-load').problem;
  static BeamProblem get _cantilever => ExampleLibrary.byId('cantilever').problem;
  static BeamProblem get _overhang => ExampleLibrary.byId('overhang').problem;
  static BeamProblem get _two => ExampleLibrary.byId('two-loads').problem;

  static final List<Tutorial> _ar = [
    Tutorial('supports', 'المساند وردود الأفعال', 'Pin وRoller وFixed: ماذا يمنع كل واحد؟', [
      TutorialSection('القاعدة الذهبية',
          'كل حركة يمنعها المسند تقابلها قوة رد فعل في اتجاهها. المسند الذي يمنع الدوران يؤثر بعزم.'),
      TutorialSection('Pin — مسند مفصلي',
          'يمنع الحركة الأفقية والرأسية، ويسمح بالدوران. له رد فعلين: H (أفقي) وR (رأسي).',
          figure: _central),
      TutorialSection('Roller — مسند متدحرج',
          'يتدحرج على سطحه، فيمنع الحركة العمودية على السطح فقط. له رد فعل واحد R. لا يقاوم أي قوة أفقية، لذلك كمرة على مسندين Roller غير مستقرة.'),
      TutorialSection('Fixed — مسند مثبّت',
          'الكمرة مدفونة فيه فلا تتحرك ولا تدور. له ثلاثة ردود أفعال: H وR وعزم M. يكفي وحده لاتزان الكمرة (Cantilever).',
          figure: _cantilever, figureKind: FigureKind.freeBody),
      TutorialSection('متى تُحل المسألة بالاتزان؟',
          'لدينا ثلاث معادلات اتزان في المستوى. Pin + Roller = 3 مجاهيل ✓. Fixed وحده = 3 ✓. Pin + Pin = 4 ✗ (غير محددة استاتيكيًا). Roller + Roller = 2 ✗ (غير مستقرة).'),
    ]),
    Tutorial('fbd', 'مخطط الجسم الحر (FBD)', 'أول خطوة في أي مسألة', [
      TutorialSection('ما هو؟',
          'رسم للكمرة وحدها، بعد إزالة المساند، مع كل القوى المؤثرة عليها: الأحمال وردود الأفعال.',
          figure: _central, figureKind: FigureKind.freeBody),
      TutorialSection('كيف نرسمه؟',
          '1) ارسم الكمرة خطًا. 2) ارسم الأحمال كما هي. 3) أزل كل مسند وضع مكانه ردود أفعاله. 4) اكتب الأبعاد. 5) افترض اتجاهًا لكل رد فعل (عادة → و↑ و↺).'),
      TutorialSection('ماذا لو أخطأت الاتجاه؟',
          'لا مشكلة: إذا خرجت النتيجة سالبة فالاتجاه الحقيقي عكس ما افترضت. القيمة صحيحة ولا تعيد الحل.'),
    ]),
    Tutorial('equilibrium', 'معادلات الاتزان', 'ΣFx = 0 و ΣFy = 0 و ΣM = 0', [
      TutorialSection('لماذا ثلاث معادلات؟',
          'الجسم في المستوى يمكن أن يتحرك أفقيًا ورأسيًا ويدور. الاتزان يعني أن لا شيء من هذه الحركات يحدث: مجموع القوى في x صفر، وفي y صفر، ومجموع العزوم صفر.'),
      TutorialSection('العزم = القوة × الذراع',
          'الذراع هو البعد العمودي من النقطة إلى خط عمل القوة. القوة التي تمر بالنقطة ذراعها صفر، فعزمها صفر.'),
      TutorialSection('حول أي نقطة نأخذ العزوم؟',
          'أي نقطة تصلح، لكن الذكي يختار نقطة تمر بها قوى مجهولة فتختفي من المعادلة. في كمرة Pin عند A وRoller عند B: العزوم حول A تحذف HA وRA فيبقى RB وحده.',
          figure: _central, figureKind: FigureKind.freeBody),
      TutorialSection('تحقق دائمًا',
          'بعد الحل خذ العزوم حول نقطة لم تستخدمها. إذا أعطت صفرًا فالحل صحيح.'),
    ]),
    Tutorial('signs', 'اصطلاح الإشارات', 'لماذا هذه القوة موجبة؟', [
      TutorialSection('في معادلات الاتزان',
          'نختار اتجاهًا موجبًا ونلتزم به: عادة → موجب، ↑ موجب، ↺ موجب. يمكنك تغيير ذلك من الإعدادات؛ تتغير إشارات الحدود لكن ردود الأفعال لا تتغير.'),
      TutorialSection('في قوة القص V',
          'V موجبة إذا كانت القوى على يسار المقطع تدفعه للأعلى. لذلك: V = مجموع القوى الرأسية على يسار المقطع (↑ موجب).'),
      TutorialSection('في عزم الانحناء M',
          'M موجب إذا حنى الكمرة على شكل ابتسامة ⌣ (Sagging): الألياف السفلى في شد والعليا في ضغط. السالب (Hogging) يحنيها ⌢.',
          figure: _overhang, figureKind: FigureKind.moment),
    ]),
    Tutorial('sfd', 'من الأحمال إلى SFD', 'كيف يُرسم مخطط القص؟', [
      TutorialSection('القفزات',
          'تحرك من اليسار إلى اليمين. عند كل قوة مركّزة يقفز المخطط بمقدارها: للأعلى إذا كانت للأعلى وللأسفل إذا كانت للأسفل.',
          figure: _two, figureKind: FigureKind.shear),
      TutorialSection('بين الأحمال',
          'إذا لم يوجد حمل موزّع فقوة القص ثابتة: خط أفقي، لأن dV/dx = −w = 0.'),
      TutorialSection('لماذا يعود للصفر؟',
          'مجموع كل القفزات = مجموع كل القوى الرأسية = 0 (ΣFy = 0). إذا لم يعد للصفر فهناك خطأ.'),
      TutorialSection('لماذا تصبح V سالبة؟',
          'عندما تصبح القوى للأسفل على يسار المقطع أكبر من القوى للأعلى.'),
    ]),
    Tutorial('bmd', 'من SFD إلى BMD', 'وأين يقع أقصى عزم؟', [
      TutorialSection('الميل',
          'ميل مخطط العزم = قوة القص: dM/dx = V. V موجبة ⇐ M يزداد. V سالبة ⇐ M يقل. V ثابتة ⇐ M خط مستقيم.',
          figure: _two, figureKind: FigureKind.moment),
      TutorialSection('المساحة',
          'التغير في العزم بين نقطتين = مساحة SFD بينهما. ابدأ من M = 0 عند الطرف الحر أو المسند البسيط وأضف المساحات.'),
      TutorialSection('أقصى عزم',
          'العزم يتوقف عن الزيادة حيث تتوقف V عن أن تكون موجبة. لذلك Mmax حيث تغيّر V إشارتها (أو عند المساند والأطراف).'),
      TutorialSection('الكابولي',
          'في الكمرة الكابولية أكبر عزم عند المسند الثابت دائمًا، وهو سالب (Hogging).',
          figure: _cantilever, figureKind: FigureKind.moment),
    ]),
  ];

  static final List<Tutorial> _en = [
    Tutorial('supports', 'Supports and reactions', 'Pin, roller, fixed: what does each one stop?', [
      TutorialSection('The golden rule',
          'Every movement a support prevents comes with a reaction force in that direction. A support that prevents rotation applies a moment.'),
      TutorialSection('Pin',
          'Stops horizontal and vertical movement, allows rotation. Two reactions: H (horizontal) and R (vertical).',
          figure: _central),
      TutorialSection('Roller',
          'Rolls along its surface, so it only stops movement perpendicular to it. One reaction R. It resists no horizontal force, which is why a beam on two rollers is unstable.'),
      TutorialSection('Fixed',
          'The beam is built in: it can neither move nor rotate. Three reactions: H, R and a moment M. It holds a beam on its own (a cantilever).',
          figure: _cantilever, figureKind: FigureKind.freeBody),
      TutorialSection('When does equilibrium solve it?',
          'There are three equilibrium equations in 2D. Pin + roller = 3 unknowns ✓. Fixed alone = 3 ✓. Pin + pin = 4 ✗ (indeterminate). Roller + roller = 2 ✗ (unstable).'),
    ]),
    Tutorial('fbd', 'Free body diagram', 'The first step of every problem', [
      TutorialSection('What is it?',
          'A drawing of the beam on its own, with the supports removed and every force on it shown: loads and reactions.',
          figure: _central, figureKind: FigureKind.freeBody),
      TutorialSection('How to draw it',
          '1) Draw the beam as a line. 2) Draw the loads as given. 3) Replace each support by its reactions. 4) Add the dimensions. 5) Assume a direction for each reaction (usually →, ↑, ↺).'),
      TutorialSection('What if I guess the direction wrong?',
          'Nothing breaks: a negative result means the real direction is the opposite one. The value is right and nothing needs redoing.'),
    ]),
    Tutorial('equilibrium', 'Equilibrium equations', 'ΣFx = 0, ΣFy = 0, ΣM = 0', [
      TutorialSection('Why three?',
          'A body in a plane can slide sideways, move up or down, and rotate. Equilibrium means none of that happens: forces in x add to zero, forces in y add to zero, and moments add to zero.'),
      TutorialSection('Moment = force × arm',
          'The arm is the perpendicular distance from the point to the line of action of the force. A force through the point has zero arm and zero moment.'),
      TutorialSection('Which point to take moments about?',
          'Any point works, but a good choice is one that unknown forces pass through, so they drop out. With a pin at A and a roller at B, moments about A remove HA and RA and leave RB alone.',
          figure: _central, figureKind: FigureKind.freeBody),
      TutorialSection('Always check',
          'After solving, take moments about a point you did not use. If it comes out zero, the answer is right.'),
    ]),
    Tutorial('signs', 'Sign conventions', 'Why is this force positive?', [
      TutorialSection('In the equilibrium equations',
          'Pick a positive direction and stick to it: usually → positive, ↑ positive, ↺ positive. You can change it in Settings; the signs of the terms change but the reactions do not.'),
      TutorialSection('For shear V',
          'V is positive when the forces left of the cut push it up. So V = the sum of the vertical forces left of the cut (↑ positive).'),
      TutorialSection('For bending moment M',
          'M is positive when it bends the beam into a smile ⌣ (sagging): bottom fibres in tension, top in compression. Negative (hogging) bends it ⌢.',
          figure: _overhang, figureKind: FigureKind.moment),
    ]),
    Tutorial('sfd', 'From loads to the SFD', 'How the shear diagram is drawn', [
      TutorialSection('Jumps',
          'Walk from left to right. At every point force the diagram jumps by that force: up for an upward force, down for a downward one.',
          figure: _two, figureKind: FigureKind.shear),
      TutorialSection('Between loads',
          'With no distributed load the shear is constant: a level line, because dV/dx = −w = 0.'),
      TutorialSection('Why does it end at zero?',
          'All the jumps add up to all the vertical forces, which is zero (ΣFy = 0). If it does not close, something is wrong.'),
      TutorialSection('Why does V turn negative?',
          'When the downward forces left of the cut outweigh the upward ones.'),
    ]),
    Tutorial('bmd', 'From the SFD to the BMD', 'And where the maximum moment is', [
      TutorialSection('Slope',
          'The slope of the BMD is the shear: dM/dx = V. Positive V ⇒ M rises. Negative V ⇒ M falls. Constant V ⇒ M is a straight line.',
          figure: _two, figureKind: FigureKind.moment),
      TutorialSection('Area',
          'The change in moment between two points is the area of the SFD between them. Start from M = 0 at a free end or simple support and add the areas.'),
      TutorialSection('Maximum moment',
          'The moment stops rising where V stops being positive. So Mmax is where V changes sign (or at a support or an end).'),
      TutorialSection('Cantilevers',
          'In a cantilever the largest moment is always at the fixed support, and it is hogging.',
          figure: _cantilever, figureKind: FigureKind.moment),
    ]),
  ];
}
