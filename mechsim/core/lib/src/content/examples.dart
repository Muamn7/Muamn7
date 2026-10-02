/// The "Mechanics" library: classic beam problems a student meets in the
/// first weeks, each one ready to open, edit and analyse.
library;

import '../explain/lang.dart';
import '../model/beam_problem.dart';

class ExampleProblem {
  const ExampleProblem({
    required this.id,
    required this.titleAr,
    required this.titleEn,
    required this.ideaAr,
    required this.ideaEn,
    required this.problem,
  });

  final String id;
  final String titleAr;
  final String titleEn;

  /// What the example teaches.
  final String ideaAr;
  final String ideaEn;
  final BeamProblem problem;

  String title(Lang lang) => lang == Lang.ar ? titleAr : titleEn;
  String idea(Lang lang) => lang == Lang.ar ? ideaAr : ideaEn;
}

const _kN = 1000.0;

abstract final class ExampleLibrary {
  static const List<ExampleProblem> all = [
    ExampleProblem(
      id: 'central-load',
      titleAr: 'كمرة بسيطة وحمل في المنتصف',
      titleEn: 'Simply supported, central load',
      ideaAr: 'أبسط حالة: المسندان يتقاسمان الحمل بالتساوي، وأقصى عزم تحت الحمل.',
      ideaEn: 'The simplest case: the supports share the load equally and Mmax is under the load.',
      problem: BeamProblem(length: 6, supports: [
        Support(id: 's1', type: SupportType.pin, x: 0),
        Support(id: 's2', type: SupportType.roller, x: 6),
      ], loads: [
        PointLoad(id: 'p1', x: 3, magnitude: 20 * _kN),
      ]),
    ),
    ExampleProblem(
      id: 'off-centre-load',
      titleAr: 'حمل غير متماثل',
      titleEn: 'Off-centre load',
      ideaAr: 'المسند الأقرب إلى الحمل يحمل الجزء الأكبر منه: RA = Pb/L و RB = Pa/L.',
      ideaEn: 'The support nearer the load carries more of it: RA = Pb/L, RB = Pa/L.',
      problem: BeamProblem(length: 8, supports: [
        Support(id: 's1', type: SupportType.pin, x: 0),
        Support(id: 's2', type: SupportType.roller, x: 8),
      ], loads: [
        PointLoad(id: 'p1', x: 2, magnitude: 30 * _kN),
      ]),
    ),
    ExampleProblem(
      id: 'two-loads',
      titleAr: 'حملان مركّزان',
      titleEn: 'Two point loads',
      ideaAr: 'كل حمل يصنع قفزة في SFD، وMmax حيث تغيّر V إشارتها.',
      ideaEn: 'Each load makes a jump in the SFD; Mmax is where V changes sign.',
      problem: BeamProblem(length: 10, supports: [
        Support(id: 's1', type: SupportType.pin, x: 0),
        Support(id: 's2', type: SupportType.roller, x: 10),
      ], loads: [
        PointLoad(id: 'p1', x: 3, magnitude: 20 * _kN),
        PointLoad(id: 'p2', x: 7, magnitude: 30 * _kN),
      ]),
    ),
    ExampleProblem(
      id: 'udl',
      titleAr: 'حمل موزّع منتظم (UDL)',
      titleEn: 'Uniformly distributed load (UDL)',
      ideaAr: 'المحصّلة = w × L في المنتصف. SFD خط مائل وBMD قطع مكافئ، وأقصى عزم wL²/8 حيث V = 0.',
      ideaEn: 'Resultant = w × L at mid-span. The SFD is a sloping line and the BMD a parabola; Mmax = wL²/8 where V = 0.',
      problem: BeamProblem(length: 6, supports: [
        Support(id: 's1', type: SupportType.pin, x: 0),
        Support(id: 's2', type: SupportType.roller, x: 6),
      ], loads: [
        DistributedLoad(id: 'w1', x: 0, x2: 6, w1: 5 * _kN, w2: 5 * _kN),
      ]),
    ),
    ExampleProblem(
      id: 'uvl',
      titleAr: 'حمل مثلثي (UVL)',
      titleEn: 'Triangular load (UVL)',
      ideaAr: 'المحصّلة = ½ × w × L على ثلث الطول من الطرف الأكبر. SFD منحنى وBMD من الدرجة الثالثة.',
      ideaEn: 'Resultant = ½ × w × L, a third of the length from the larger end. The SFD is a curve and the BMD a cubic.',
      problem: BeamProblem(length: 6, supports: [
        Support(id: 's1', type: SupportType.pin, x: 0),
        Support(id: 's2', type: SupportType.roller, x: 6),
      ], loads: [
        DistributedLoad(id: 'w1', x: 0, x2: 6, w1: 0, w2: 6 * _kN),
      ]),
    ),
    ExampleProblem(
      id: 'udl-cantilever',
      titleAr: 'كابولي عليه حمل موزّع',
      titleEn: 'Cantilever with a UDL',
      ideaAr: 'عزم المسند الثابت = wL²/2، والعزم سالب على طول الكمرة.',
      ideaEn: 'The fixed-end moment is wL²/2, and the moment is hogging all along.',
      problem: BeamProblem(length: 4, supports: [
        Support(id: 's1', type: SupportType.fixed, x: 0),
      ], loads: [
        DistributedLoad(id: 'w1', x: 0, x2: 4, w1: 3 * _kN, w2: 3 * _kN),
      ]),
    ),
    ExampleProblem(
      id: 'couple',
      titleAr: 'عزم مركّز (Moment)',
      titleEn: 'Concentrated moment',
      ideaAr: 'العزم المركّز لا يغيّر SFD لكنه يجعل BMD يقفز بمقداره.',
      ideaEn: 'A couple leaves the SFD alone but makes the BMD jump by its value.',
      problem: BeamProblem(length: 6, supports: [
        Support(id: 's1', type: SupportType.pin, x: 0),
        Support(id: 's2', type: SupportType.roller, x: 6),
      ], loads: [
        PointMoment(id: 'c1', x: 2, magnitude: 12 * _kN),
      ]),
    ),
    ExampleProblem(
      id: 'overhang',
      titleAr: 'كمرة ببروز (Overhang)',
      titleEn: 'Beam with an overhang',
      ideaAr: 'حمل على الطرف البارز يجعل أحد ردود الأفعال سالبًا، ويظهر عزم سالب (Hogging) فوق المسند.',
      ideaEn: 'A load on the overhang makes one reaction negative and a hogging moment appears over the support.',
      problem: BeamProblem(length: 6, supports: [
        Support(id: 's1', type: SupportType.pin, x: 0),
        Support(id: 's2', type: SupportType.roller, x: 4),
      ], loads: [
        PointLoad(id: 'p1', x: 2, magnitude: 10 * _kN),
        PointLoad(id: 'p2', x: 6, magnitude: 12 * _kN),
      ]),
    ),
    ExampleProblem(
      id: 'cantilever',
      titleAr: 'كمرة كابولية (Cantilever)',
      titleEn: 'Cantilever',
      ideaAr: 'مسند Fixed واحد يعطي ثلاثة ردود أفعال، وأكبر عزم عند المسند وهو سالب.',
      ideaEn: 'One fixed support gives three reactions; the largest moment is at the support, and it is hogging.',
      problem: BeamProblem(length: 4, supports: [
        Support(id: 's1', type: SupportType.fixed, x: 0),
      ], loads: [
        PointLoad(id: 'p1', x: 4, magnitude: 10 * _kN),
      ]),
    ),
    ExampleProblem(
      id: 'cantilever-right',
      titleAr: 'كابولي مثبّت من اليمين',
      titleEn: 'Cantilever fixed on the right',
      ideaAr: 'نفس الفكرة لكن المسند على اليمين: لاحظ أن SFD يبدأ من الصفر عند الطرف الحر.',
      ideaEn: 'Same idea with the support on the right: the SFD starts at zero at the free end.',
      problem: BeamProblem(length: 5, supports: [
        Support(id: 's1', type: SupportType.fixed, x: 5),
      ], loads: [
        PointLoad(id: 'p1', x: 0, magnitude: 8 * _kN),
        PointLoad(id: 'p2', x: 2, magnitude: 12 * _kN),
      ]),
    ),
    ExampleProblem(
      id: 'inclined-load',
      titleAr: 'حمل مائل',
      titleEn: 'Inclined load',
      ideaAr: 'نحلل الحمل إلى مركبتين: الأفقية يقاومها الـ Pin وتسبب قوة محورية، والرأسية تسبب القص والعزم.',
      ideaEn: 'Resolve the load: the pin resists the horizontal part, which causes axial force; the vertical part causes shear and moment.',
      problem: BeamProblem(length: 5, supports: [
        Support(id: 's1', type: SupportType.pin, x: 0),
        Support(id: 's2', type: SupportType.roller, x: 5),
      ], loads: [
        PointLoad(id: 'p1', x: 2, magnitude: 20 * _kN, angleDeg: -60),
      ]),
    ),
    ExampleProblem(
      id: 'upward-load',
      titleAr: 'حمل للأعلى',
      titleEn: 'An upward load',
      ideaAr: 'حمل للأعلى يقفز بالـ SFD للأعلى. انتبه للإشارات في ΣFy.',
      ideaEn: 'An upward load makes the SFD jump up. Watch the signs in ΣFy.',
      problem: BeamProblem(length: 8, supports: [
        Support(id: 's1', type: SupportType.pin, x: 0),
        Support(id: 's2', type: SupportType.roller, x: 6),
      ], loads: [
        PointLoad(id: 'p1', x: 3, magnitude: 30 * _kN),
        PointLoad(id: 'p2', x: 8, magnitude: 10 * _kN, angleDeg: 90),
      ]),
    ),
  ];

  static ExampleProblem byId(String id) => all.firstWhere((e) => e.id == id);
}
