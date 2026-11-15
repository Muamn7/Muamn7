# مغناطيس منارة الحدباء – الموصل (Blender)

| الملف | الوصف |
|---|---|
| `hadba_magnet.blend` | المشهد الجاهز (Blender 5.3، يفتح على 4.2+). الخريطة والخط مضمّنان داخل الملف |
| **`hadba_magnet_print_mm.zip`** | **ملف الطباعة: STL واحد مغلق (watertight) بالمليمتر، 60 × 89.6 × 7.95 ملم** |
| `render_print_mesh.png` | معاينة لجسم الطباعة |
| `hadba_magnet.py` | سكربت يبني المشهد كاملاً من الصفر |
| `hadba_relief_height.png` | خريطة ارتفاع 16-bit للنحت البارز (1121×1505) |
| `render_front.png` / `render_angle.png` | معاينة Cycles |

## المقاسات
1 وحدة = 1 سم · اللوح 6.0 × 8.95 × 0.45 سم · أعلى بروز للنحت ≈ 3.6 ملم · بروز النص ≈ 1 ملم

## الكائنات
- **Plaque**: اللوح بقوس علوي وزوايا مدورة (Bevel modifier).
- **Relief_Minaret**: المنارة والقاعدة والأطلال. فيه Subdivision (Simple) ثم Displace.
  - لتغيير عمق النحت: غيّر **Strength** في `Displace_Relief`.
  - للحصول على Mesh حقيقي (للطباعة أو التصدير): Apply على الـ Subdivision ثم على الـ Displace.
- **Title_AlHadba_Minaret**: نص يتبع القوس `TitleArc` عبر Curve modifier، ويمكن تعديل الكتابة مباشرة (Tab).
- **Subtitle_Mosul** و **Footer_Iraq**: نصوص قابلة للتعديل.
- كاميرتان: `Camera` (أمامية) و `Camera_Angle` (مائلة).

## إعادة البناء من السكربت
```bash
blender --background --python hadba_magnet.py -- --save hadba_magnet.blend --render render_front.png
```
أو افتح السكربت في تبويب Scripting واضغط Run Script.

## الطباعة 3D
- استخدم `hadba_magnet_print_mm.stl` (داخل الـ zip) أو الكائن **Magnet_PRINT** في مجموعة `PRINT_3D` داخل الـ .blend.
- اللوح والنحت والنصوص مدموجة في جسم واحد مغلق: 0 حواف غير سليمة (non-manifold)، اتجاه الأوجه صحيح، قاعدة مسطّحة على z = 0.
- الوحدات بالمليمتر، فلا تحتاج تغيير المقياس في السلايسر.
- اطبعه مستلقياً والوجه للأعلى بدون دعامات. عمق نقوش الطابوق 0.1–0.2 ملم، فيظهر بشكل أوضح على طابعة رزن أو بفوهة 0.2 ملم.
- الكائنات القديمة (Plaque و Relief و Text) للعرض والتعديل فقط، فهي قطع منفصلة ولا تُطبع مباشرة.
- لإعادة توليد ملف الطباعة بعد أي تعديل:
```bash
blender --background --python hadba_magnet.py -- --save hadba_magnet.blend --stl hadba_magnet_print_mm.stl
```
