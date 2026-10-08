# portfolio

Portfolio website for Mohamed Ahmed Bahur - Technical Researcher

موقع ثابت (ملف `index.html` واحد + مجلد `images/`) بدون build step وبدون أي اعتماد على npm.

## الصور

كل الصور تُقرأ محلياً من مجلد `images/` — لا يوجد أي رابط Unsplash أو CDN للصور.
الأسماء مطلوبة بالحرف، والموقع يسقط على `images/placeholder-portrait.svg` تلقائياً إذا كان الملف ناقص
(بدل أيقونة "صورة مكسورة").

| الملف المطلوب            | المستخدم في                                          |
| ------------------------ | ---------------------------------------------------- |
| `images/profile-1.jpg`   | صورة البروفايل في الـ hero                           |
| `images/conference.jpg`  | خلفية قسم الـ hero                                    |
| `images/work-1.jpg`      | معرض الصور — تدقيق بيانات الحالات                      |
| `images/work-2.jpg`      | معرض الصور — تحليل المؤشرات                            |
| `images/work-3.jpg`      | معرض الصور — الأرشفة والتوثيق                          |
| `images/profile-2.jpg`   | معرض الصور — مشاركة في فعاليات سجل السرطان            |

المقاس الموصى به: ضلع أطول ≤ 1600px، JPEG بجودة 80–85، وأقل من 300KB لكل صورة
(صور أثقل من كده تُبطئ الموقع وما بتفرقش بصرياً).

## قبل ما ترفع أي صورة — تحقّف

```bash
python3 scripts/check-images.py
```

السكربت ده بيكتشف الأخطاء الأربعة اللي بتخلّي "رفع الملفات" يبدو فاشل:

1. ملف موجود بس **مش صورة حقيقية** (أول البايبتs `<!--` بدل `\xff\xd8\xff`) — حالة الـ placeholders القديمة.
2. **حجم غريب** (أقل من 5KB = ملف نصي متنكّر في صورة).
3. صورة **مش موجودة** أصلاً مع إنها مشار إليها في `index.html`.
4. صورة **غير مستخدمة**، أو حجم يتجاوز حد GitHub (100MB).

## طرق رفع الصور للمستودع

**من المتصفح (الأسهل):** افتح <https://github.com/Gentely/portfolio/upload/main/images/>
واسحب الملفات هناك، ثم Commit. تأكد إن الاسم مطابق للجدول فوق.

**من الطرفية:**

```bash
cp ~/Pictures/{profile-1,profile-2,conference,work-1,work-2,work-3}.jpg images/
python3 scripts/check-images.py
git add images/ && git commit -m "Add real portfolio photos" && git push
```

> ملاحظة: إرسال الصور كمرفقات في المحادثة/الدردشة بيريها كصورة بس ما بيكتبهاش على القرص
> داخل مساحة العمل. عشان توصل للمستودع لازم تكون `git add` أو رفع مباشر على GitHub.

## المعاينة محلياً

```bash
python3 -m http.server 8000
# ثم افتح http://localhost:8000
```

## النشر على GitHub Pages

الريبو ده **مش مفعّل** عليه Pages لحد الآن. لتفعيله:

```bash
gh api -X POST repos/Gentely/portfolio/pages -f source[branch]=main -f source[path]=/
```

أو من Settings → Pages → Branch: `main` / `/ (root)`.
