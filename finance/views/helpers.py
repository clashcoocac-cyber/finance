from datetime import datetime

from django.db.models import Sum
from finance.models import Transaction, Stat, StatTypes

CURRENCIES = ('uzs', 'usd', 'rub', 'eur')


def date_param(value, default):
    """`value` if it is a valid YYYY-MM-DD string, else `default`.
    Query-string dates come from users; a bad one must fall back, not 500."""
    try:
        datetime.strptime((value or '').strip(), '%Y-%m-%d')
    except ValueError:
        return default
    return value.strip()


def preserve_filters(request, base_url):
    """Redirect back to base_url keeping the query string the page was
    showing when its form was submitted. POST handlers read `current_qs`
    (a hidden field carrying `request.GET.urlencode` from the filtered
    page) instead of `request.META['QUERY_STRING']`, because that reflects
    the POST target's own (empty) querystring, not the page the user saw.
    """
    qs = request.POST.get('current_qs', '')
    return f"{base_url}?{qs}" if qs else base_url


def _aggregate(qs):
    result = qs.aggregate(
        total_usd=Sum('amount_usd'), total_uzs=Sum('amount_uzs'),
        total_rub=Sum('amount_rub'), total_eur=Sum('amount_eur'),
    )
    return {k: v or 0 for k, v in result.items()}


def _totals_for(is_closed, date_from=None, date_to=None):
    income_qs = Transaction.objects.filter(type='income', report__is_closed=is_closed, payment_type='cash')
    expense_qs = Transaction.objects.filter(type='expense', report__is_closed=is_closed, payment_type='cash')

    if date_from and date_to:
        income_qs = income_qs.filter(date__date__range=(date_from, date_to))
        expense_qs = expense_qs.filter(date__date__range=(date_from, date_to))

    income = _aggregate(income_qs)
    expense = _aggregate(expense_qs)
    diff = {f'total_{cur}': income[f'total_{cur}'] - expense[f'total_{cur}'] for cur in CURRENCIES}
    return {'income': income, 'expense': expense, 'diff': diff}


def raw_confirmed_totals(date_from=None, date_to=None):
    return _totals_for(is_closed=True, date_from=date_from, date_to=date_to)


def raw_pending_totals(date_from=None, date_to=None):
    return _totals_for(is_closed=False, date_from=date_from, date_to=date_to)


def compute_money_stats(date_from=None, date_to=None):
    """Confirmed totals get the manual `Stat.default_*` correction applied
    (existing boss "edit daily stats" feature); pending totals are always
    live with no correction — there's nothing to manually fix on money that
    hasn't been confirmed yet."""
    raw = raw_confirmed_totals(date_from=date_from, date_to=date_to)
    pending = raw_pending_totals(date_from=date_from, date_to=date_to)

    inc_stat, _ = Stat.objects.get_or_create(type=StatTypes.INCOME)
    for cur in CURRENCIES:
        setattr(inc_stat, f'total_{cur}', raw['income'][f'total_{cur}'] - getattr(inc_stat, f'default_{cur}'))
    inc_stat.save()

    exp_stat, _ = Stat.objects.get_or_create(type=StatTypes.EXPENSE)
    for cur in CURRENCIES:
        setattr(exp_stat, f'total_{cur}', raw['expense'][f'total_{cur}'] - getattr(exp_stat, f'default_{cur}'))
    exp_stat.save()

    diff_stat, _ = Stat.objects.get_or_create(type=StatTypes.BALANCE)
    for cur in CURRENCIES:
        setattr(diff_stat, f'total_{cur}', int(raw['diff'][f'total_{cur}']) - getattr(diff_stat, f'default_{cur}'))
    diff_stat.save()

    combined = {}
    for key, stat in (('income', inc_stat), ('expense', exp_stat), ('diff', diff_stat)):
        combined[key] = {
            f'total_{cur}': getattr(stat, f'total_{cur}') + pending[key][f'total_{cur}']
            for cur in CURRENCIES
        }

    return {
        'confirmed': {'income': inc_stat, 'expense': exp_stat, 'diff': diff_stat},
        'pending': pending,
        # Confirmed + pending combined, so the headline figure reflects every
        # recorded amount regardless of confirmation state — the pending
        # summary line under each stat card shows the part still awaiting
        # confirmation, but the main number already includes it.
        'combined': combined,
    }
