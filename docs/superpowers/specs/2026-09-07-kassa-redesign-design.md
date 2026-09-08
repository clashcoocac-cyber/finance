# Kassa/Moliya tizimi — 100% redizayn + funksional tuzatishlar

**Sana:** 2026-09-07
**Loyiha:** Django (`finance` app) + Tailwind CDN + Alpine.js (yangi)
**Muallif:** Claude Code (Komron bilan birga brainstorming orqali kelishilgan)

## 1. Maqsad

Mavjud kassa/moliya boshqaruv tizimini (boss/kassir/operator rollari) vizual va funksional jihatdan to'liq yangilash:

1. Zamonaviy, aniq, ishonchli UI — barcha sahifalarda bir xil dizayn tizimi.
2. 7 ta funksional talab (pastda §4) bajarilishi.
3. Yo'l-yo'lakay topilgan eski xatolar (typo, JSON'da pul kesilishi, filter yo'qolishi) tuzatiladi — Komron ruxsat berdi.

## 2. Ko'lam

Ichida: `finance/models.py`, `finance/forms.py`, `finance/views/*.py`, `finance/mixins.py`, `finance/admin.py`, barcha `templates/**/*.html`, `templates/base.html`.

Tashqarida: autentifikatsiya mexanizmi (Django auth saqlanadi), `Stat.default_*` offset mexanizmining o'zi (faqat qo'llanish doirasi torayadi — pastga qarang), `Company` modeli, `manage.py`/`config/`.

## 3. Ma'lumotlar bazasi o'zgarishlari

### 3.1 Yangi modellar (`finance/models.py`)

```python
class Category(models.Model):
    GROUPS = [('expense', 'Chiqim'), ('xarajat', 'Xarajat')]
    name = models.CharField(max_length=100, unique=True)
    group = models.CharField(max_length=10, choices=GROUPS)
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

class Counterparty(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
```

- Ikkalasi ham oddiy nom-ro'yxat: hozirgi hardcoded `CATEGORIES` dict (`forms.py`) va `PERSONS` choices (`models.py`) o'rnini bosadi.
- `Transaction.counterparty` va `DailyReport.category` maydonlari **CharField bo'lib qoladi** (mavjud ma'lumotlar buzilmasligi uchun) — lekin forma darajasida select DB'dan dinamik to'ldiriladi.
- Migratsiya: mavjud `PERSONS` ro'yxatidagi barcha qiymatlar + mavjud `Transaction.counterparty`/`DailyReport.category`dagi noyob qiymatlar data-migration bilan `Counterparty`/`Category` jadvaliga ko'chiriladi (tarixiy filtr/select ishlashda uzilish bo'lmasligi uchun).
- Admin panelga (`finance/admin.py`) ikkalasi ham ro'yxatga olinadi — boss xohlasa `is_active=False` qilib yashira oladi.

### 3.2 "Boshqa" → avtomatik saqlash oqimi

Forma validatsiyasida: foydalanuvchi "Boshqa" tanlab erkin matn kiritsa →
`Category.objects.get_or_create(name=value.strip())` / `Counterparty.objects.get_or_create(name=value.strip())` chaqiriladi, keyin shu qiymat tranzaksiyaga yoziladi. Keyingi so'rovda bu qiymat select ro'yxatida avtomatik chiqadi (qo'shimcha "eslab qolish" logikasi kerak emas — DB manba bo'ladi).

### 3.3 Tuzatiladigan eski xatolar

| Joy | Muammo | Tuzatish |
|---|---|---|
| `forms.py: IncomeForm` | `countryparty` maydon nomi typo | `counterparty`ga o'zgartiriladi (forma + shablon + view) |
| `views/accounts.py: TransactionDeleteView.subtract_detail` | try/except ichida ikkala branch bir xil, ma'nosiz | try/except olib tashlanadi |
| `forms.py` (`ExpenseForm.save`, `IncomeForm.save`) | `report.*_detail` JSON yozilganda `int(...)` bilan pul kesiladi (tiyin yo'qoladi) | `float(...)`ga o'tkaziladi |
| `views/transaction.py: ConfirmExpenseView/ConfirmIncomeView`, `CloseCashRegister` | redirect joriy filterlarni saqlamaydi (§4.6 bug root cause) | umumiy `preserve_filters()` helper orqali redirect |

## 4. Funksional talablar (7 ta)

### 4.1 Kassir: chiqim kategoriyasi eslab qolinadi
`ExpenseForm.category` — hozirgi `CharField` → `ChoiceField` (DB'dagi `Category.objects.filter(is_active=True)` + `('__new__', '+ Yangi qo'shish')`). UX aniq talab: foydalanuvchi avval mavjud kategoriyalar select'ini ko'radi (u "Boshqa" deb yozmaydi); select tagida/yonida "+" tugma bor — bosilsa select yashirinib text input ko'rinadi (Alpine `x-show`, ikkalasi bir vaqtda emas), matn kiritib saqlaydi. Saqlashda §3.2 oqimi ishlaydi (`get_or_create`), yangi kategoriya select ro'yxatiga navbatdagi so'rovda avtomatik qo'shiladi. `'__new__'` maxsus qiymat forma validatsiyasida "matn maydoni to'ldirilishi shart" qoidasini triggerlaydi.

**Muhim tafsilot (kod tekshiruvida topildi):** hozirgi `expenses_page.html`da kategoriya ro'yxati ikkita mustaqil to'plamga bo'lingan — "Chiqim" (`exp_type='expense'`: chikako/jasur/ravshan/almashdi/rasxod_den) va "Xarajat" (`exp_type='xarajat'`: mssb/opt/sfb xarajat), JS orqali `exp_type` tanlanganda select qayta to'ldiriladi. Shuning uchun `Category.group` maydoni qo'shiladi (`expense`/`xarajat`), yangi select ham shu ikki guruhni Alpine bilan filtrlaydi (server `category` ChoiceField barcha faol kategoriyalarni group bilan birga beradi, shablon `exp_type`ga qarab ko'rsatadi/yashiradi — eski `changeCategories()` JS funksiyasi shu bilan almashadi).

### 4.2 Operator: "kimdan oldi" xuddi shunday
`TransactionFrom.counterparty` / `IncomeForm.counterparty` (typo tuzatilgandan keyin) xuddi 4.1 kabi — `Counterparty` DB ro'yxatidan select + "+" tugma → text input almashinuvi.

### 4.3 Kassa yopilmasa ham stats ko'rinishi (boss + kassir)
`BossDashboardView` va `ChiefCashierDashboardView.get_context_data`: statistika hisoblash ikkiga bo'linadi —
- `stats.confirmed` — hozirgi logika (`report__is_closed=True`), `Stat.default_*` offset shu yerga tegishli bo'lib qoladi.
- `stats.pending` — yangi, xuddi shu aggregatsiya lekin `report__is_closed=False`, offset **qo'llanilmaydi** (tuzatish faqat tasdiqlangan summaga tegishli tushuncha).

Ikkalasi ham kirim / chiqim / foyda(diff) uchun alohida hisoblanadi va shablonda ikki xil stat-card guruhida (rang/badge bilan farqlanib) ko'rsatiladi.

### 4.4 Checkbox bilan tasdiqlash (hammasida)
- `ConfirmExpenseView` (bitta pk) va `ConfirmIncomeView` (bitta pk) o'rniga: bitta `BulkConfirmReportsView(LoginRequiredMixin, View)` — POST bilan `report_ids` (checkbox `name="report_ids"` qiymatlar ro'yxati) qabul qiladi. Ruxsat: `request.user.role` `boss` yoki `cashier` bo'lishi kerak (ikkalasi ham shu view'ni chaqiradi, alohida subclass shart emas); queryset shu rolga tegishli report turlariga cheklanadi — bu mavjud biznes bo'linishga mos: boss faqat `type in ('expense', 'xarajat')` report'larni tasdiqlaydi (hozirgi `ConfirmExpenseView` xatti-harakati), cashier faqat `type='income'` (hozirgi `ConfirmIncomeView`). Boshqa rol yoki mos kelmagan report turi 403/e'tiborsiz qoldiriladi.
- Shablonda: har qator checkbox, jadval tepasida "Hammasini belgilash" checkbox + tanlangan sonini ko'rsatuvchi bulk-action bar (Alpine `x-data`), pastda "Tasdiqlash" tugmasi (faqat kamida 1ta belgilanganda faol).

### 4.5 Kuchli filter — bir nechta kategoriya
`BossDashboardView`, `ChiefCashierDashboardView`, `TransactionList`: `request.GET.getlist('category')` bilan ko'p qiymatli filtr, `reports.filter(category__in=selected)`. Shablonda checkbox-chip dropdown (Alpine), tanlangan chiplar filter-bar'da ko'rinadi, "×" bilan olib tashlanadi.

### 4.6 Filterlar saqlanishi (reset bo'lmasin)
Root cause: POST confirm/close view'lari `success_url`ga joriy query-string'siz redirect qiladi. Yechim: umumiy helper

```python
def preserve_filters(request, base_url):
    qs = request.POST.get('current_qs') or request.META.get('QUERY_STRING', '')
    return f"{base_url}?{qs}" if qs else base_url
```

Har bir filtrlanadigan sahifadagi form/bulk-action ichida `<input type="hidden" name="current_qs" value="{{ request.GET.urlencode }}">` bo'ladi. Barcha tegishli POST view'lar (`BulkConfirmReportsView`, `CloseCashRegister`, `ExpensesPageView.post`, `IncomesPageView.post`) shu helper orqali redirect qiladi.

### 4.7 Tasdiqlanmagan pullar admin+kassada ko'rinishi
§4.3 bilan bir xil yechim — pending stat-card guruhi + jadvalda `is_closed=False` qatorlar "Kutilmoqda" badge (amber) bilan, `is_closed=True` esa "Tasdiqlangan" badge (yashil) bilan alohida ko'rinadi. Hech qanday qator "yashirilmaydi".

## 5. Dizayn tizimi

ui-ux-pro-max: Minimalism/Swiss uslub + Banking-trust palitra (zich dashboard, ishonchli, professional; internal tool bo'lgani uchun marketing emas, aniqlik ustuvor).

### 5.1 Tokenlar (`templates/base.html` `<style>` ichida CSS custom properties)

Light (default):
```
--color-bg: #F8FAFC
--color-surface: #FFFFFF
--color-surface-muted: #F1F5F9
--color-border: #E2E8F0
--color-text: #0F172A
--color-text-muted: #64748B
--color-brand: #1E3A8A          /* tugmalar, linklar, focus ring */
--color-brand-foreground: #FFFFFF
--color-positive: #16A34A       /* kirim, tasdiqlangan */
--color-positive-bg: #F0FDF4
--color-negative: #DC2626       /* chiqim */
--color-negative-bg: #FEF2F2
--color-pending: #D97706        /* kutilmoqda */
--color-pending-bg: #FFFBEB
```

Dark (`@media (prefers-color-scheme: dark)`, bonus — asosiy talab emas, past xarajat bo'lgani uchun qo'shiladi):
```
--color-bg: #0F172A
--color-surface: #1B2336
--color-surface-muted: #1A1E2F
--color-border: #334155
--color-text: #F8FAFC
--color-text-muted: #94A3B8
/* brand/positive/negative/pending — bir xil qoladi, kontrast dark bg'da yetarli */
```

### 5.2 Tipografiya
- UI matn: Inter (Google Fonts, `wght@400;500;600;700`), base 16px, line-height 1.5.
- Pul summalari: `font-variant-numeric: tabular-nums;` + monospace (`ui-monospace, 'Fira Code', monospace`) — ustunlar tekis, o'qish oson.

### 5.3 Qayta ishlatiladigan komponentlar (`templates/partials/`)
- `_stat_card.html` — sarlavha, summa (valyuta bo'yicha), status badge (confirmed/pending), trend ixtiyoriy.
- `_status_badge.html` — `confirmed` (yashil) / `pending` (amber) / `expense` (qizil) / `income` (yashil).
- `_filter_bar.html` — sana range + qidiruv + multi-select category chip dropdown, `current_qs` hidden input avtomatik qo'shiladi.
- `_bulk_action_bar.html` — "hammasini belgilash" checkbox, tanlangan son, "Tasdiqlash" tugma, Alpine `x-data="bulkSelect()"`.
- Bulk tasdiqlash uchun alohida modal-dialog **kiritilmaydi** (v1) — checkbox belgilash + "Tasdiqlash" tugmasi allaqachon ataylab qilingan ikki bosqichli harakat, qo'shimcha modal ortiqcha (YAGNI). Kerak bo'lsa keyinroq qo'shiladi.

Alpine.js CDN: `https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js` (`defer`), `base.html`ga qo'shiladi.

## 6. Sahifalar bo'yicha o'zgarish ro'yxati

| Sahifa | Asosiy o'zgarish |
|---|---|
| `base.html` | Token'lar, Inter, Alpine CDN, rolga qarab nav, umumiy layout shell |
| `accounts/login.html` | Vizual tozalash, xatolik holati aniqroq |
| `dashboard/boss.html` | Stat-card grid (confirmed+pending), multi-category filter, checkbox bulk-confirm jadval |
| `cashier_home.html` | Xuddi shunday, kassir doirasida (faqat income report'lar) |
| `dashboard/operator.html` | "Kimdan oldi" select DB'dan + Boshqa, checkbox yo'q (operator o'ziga tasdiqlamaydi) |
| `expenses_page.html` | Category select DB'dan + Boshqa, jadval qayta dizayn |
| `incomes_page.html` | Xuddi shu pattern (counterparty) |
| `transaction_page.html` | Kuchli filter, jadval qayta dizayn |
| `edit_tran.html` | Vizual tozalash, funksiya o'zgarmaydi |
| `accounts/user_list.html` | Vizual tozalash, funksiya o'zgarmaydi |

## 7. Test rejasi

`finance/tests.py` (Django `TestCase`), targeted:
- `Category`/`Counterparty` `get_or_create` oqimi (yangi "Boshqa" qiymat keyingi so'rovda select'da chiqishi).
- `BulkConfirmReportsView` — bir nechta pk bilan, ruxsatsiz rol bilan (403/redirect).
- `preserve_filters` — redirect URL'da `current_qs` saqlanganini tekshirish.
- Pending vs confirmed stat ajratilishi (bitta yopiq + bitta ochiq report bilan aggregatsiya to'g'riligi).
- Data-migration: eski `PERSONS`/`CATEGORIES` qiymatlari DB'ga to'g'ri ko'chganini tekshirish.

Ishga tushirish: `python manage.py test finance`.

## 9. Dizayn amendment (2026-09-08) — App shell (sidebar navigatsiya)

Komron 5 ta referens screenshot yubordi (zamonaviy admin dashboard: chap tomonda tungi (dark) sidebar, yuqorida breadcrumb+bildirishnoma+avatar topbar). Ko'rsatma: aynan nusxa emas, kerakli qismlarini olib, barcha sahifalarga (allaqachon qurilganlariga ham) qo'llash.

**Qabul qilingan o'zgarishlar:**
- Har bir sahifaning o'z ichida yozilgan `<nav>` (top bar, faqat 3-4 link) butunlay bekor qilinadi. O'rniga umumiy **app shell**: chap tomonda doimiy sidebar (`--color-bg` emas, alohida to'q token — sidebar o'zining fon rangini ishlatadi, boshqa tokenlar bilan aralashmaydi) + yuqorida breadcrumb topbar (sahifa nomi + foydalanuvchi avatar/rol + logout).
- Sidebar nav elementlari rolga qarab: boss → Bosh sahifa (`boss_dashboard`), Tranzaksiyalar (`transaction_list`), Foydalanuvchilar (`users`); cashier → Bosh sahifa (`cashier_dashboard`), Kirimlar (`incomes_list`), Chiqimlar (`expenses_list`); operator → Bosh sahifa (`operator_dashboard`). Har biri SVG icon + label, joriy sahifa active-holat bilan ajratiladi (fon rangi/border).
- `_stat_card.html` yangilanadi: sarlavha yonida rangli doira ichida icon (icon-badge), pastda hozirgi kabi summalar + status badge — badge o'rni endi kartaning yuqori-o'ng burchagida (referensdagi kabi).
- `_bulk_action_bar.html` qayta ishlanadi: hozirgi "yuqorida inline bar" o'rniga **pastda yopishqoq (sticky) footer bar** — "N ta tanlandi" + tanlanganlar umumiy summasi (taxminiy) + "Bekor qilish"/"Saqlash" tugmalari, referensdagi 4-screenshot uslubida.
- Login sahifasi **o'zgarmaydi** — u hali autentifikatsiyadan oldingi ekran, sidebar tegishli emas (referens screenshotlarda ham login yo'q).
- Haqiqiy sahifalash (pagination, "Jami N ta natija / 10/sahifa") referensda ko'rinadi, lekin bu backend queryset'ga `Paginator` qo'shishni talab qiladi — **hozircha qo'shilmaydi** (ishlamaydigan dekorativ pagination yasash noto'g'ri bo'lardi); alohida keyingi task sifatida taklif qilinadi, hozirgi plan doirasidan tashqarida.

**Qo'shimcha forma andozasi (2026-09-08, 6-screenshot):** har bir forma kartasi: yuqorida rangli doira ichida icon + Title + subtitle (masalan "Kirim Qo'shish" / "Kirim ma'lumotlarini to'ldiring va tizimga kiriting"), har bir input/select ichida chapda kichik icon (valyuta belgisi, karta icon va h.k.), pastda to'liq enli, icon+matnli tugma (masalan yashil "→ Qo'shish"). **Bu naqsh barcha formalarga tegishli** — login, kirim/chiqim qo'shish, foydalanuvchi yaratish va h.k., faqat yangi quriladigan sahifalarga emas, balki **allaqachon tayyor bo'lgan login va expenses_page'ga ham** keyingi retrofit orqali qo'llanadi.

**Ijro tartibi:** yangi "App shell" task (partial + `base.html`/yangi `base_app.html` qatlami) → allaqachon qurilgan sahifalarni (boss/cashier/operator/expenses) shu shell'ga ko'chirish (bitta batch task, bir xil turdagi o'zgarish) → qolgan sahifalar (incomes/transactions/edit_tran/user_list) to'g'ridan-to'g'ri yangi shell asosida qurilib davom etadi.

## 8. Xavf / cheklovlar

- Data-migration eski `Transaction.counterparty`/`DailyReport.category` erkin matn qiymatlarida yozuv xatolari (turli register/probel) bo'lsa, duplicate-ga o'xshash lekin boshqa `Counterparty`/`Category` yozuvlari paydo bo'lishi mumkin — migration `strip().lower()` normalizatsiya bilan yoziladi, lekin 100% tozalik kafolatlanmaydi (mavjud "iflos" ma'lumot muammosi, yangi emas).
- Alpine.js — yangi dependency (CDN, build kerak emas), Komron tomonidan ma'qullangan.
- To'liq redizayn ~2300 qator shablonni qamrab oladi — implementation plan bosqichlarga bo'linadi (backend/model → dizayn tizimi/base → sahifa-sahifa), har bosqichdan keyin tekshiriladi.
