from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLES = [
        ('boss', 'Бошлиқ'),
        ('cashier', 'Главный кассир'),
        ('operator', 'Оператор')
    ]
    role = models.CharField(max_length=20, choices=ROLES)
    company = models.ForeignKey('Company', on_delete=models.CASCADE, null=True)
    created = models.DateField(auto_now_add=True)


class Company(models.Model):
    name = models.CharField(max_length=255)


PERSONS = [
    ('kenjayev_jasur', 'Kenjayev Jasur'),
    ('abdullayev_vohid', 'Abdullayev Vohid'),
    ('murodov_zubaydullo', 'Murodov Zubaydullo'),
    ('yarashev_kamol', 'Yarashev Kamol'),
    ('umarov_maxsud', 'Umarov Maxsud'),
    ('axmedov_ulugbek', "Axmedov Ulug'bek"),
    ('amonova_rushana', 'Amonova Rushana'),
    ('hamidova_umida', 'Hamidova Umida'),
    ('other', 'Boshqa')
]

CLICKS = [
    ('click1', 'SFB'),
    ('click2', 'OPT')
]

class Transaction(models.Model):
    TYPES = [
        ('income', 'Kirim'),
        ('expense', 'Chiqim')
    ]
    PAYMENT_TYPES = [
        ('click', 'Click'),
        ('cash', 'Naqd'),
        ('terminal', 'Terminal'),
        ('bank', 'Bank'),
    ]
    
    date = models.DateTimeField(null=True, blank=True)
    type = models.CharField(max_length=10, choices=TYPES)
    click = models.CharField(max_length=255, choices=CLICKS, null=True, blank=True)
    amount_usd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    amount_uzs = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    amount_rub = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    amount_eur = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPES)
    description = models.TextField()
    operator = models.ForeignKey(User, on_delete=models.CASCADE)
    counterparty = models.CharField(max_length=255, choices=PERSONS)
    report = models.ForeignKey('DailyReport', on_delete=models.CASCADE, null=True, blank=True)
    comment = models.TextField(null=True, blank=True)



class DailyReport(models.Model):
    TYPES = [
        ('income', 'Kirim'),
        ('expense', 'Chiqim'),
        ('xarajat', 'Xarajat'),
    ]
    type = models.CharField(max_length=10, choices=TYPES)
    date = models.DateField()
    operator = models.ForeignKey(User, on_delete=models.CASCADE)
    operator_shift = models.IntegerField(null=True, blank=True)
    category = models.CharField(max_length=100)
    desc = models.TextField(null=True, blank=True)
    
    total_uzs = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    total_usd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    total_rub = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    total_eur = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    uzs_detail = models.JSONField(null=True, blank=True)
    usd_detail = models.JSONField(null=True, blank=True)
    rub_detail = models.JSONField(null=True, blank=True)
    eur_detail = models.JSONField(null=True, blank=True)
    
    is_closed = models.BooleanField(default=False)
    comment = models.TextField(null=True, blank=True)


from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum


def _recalc_report(report_id):
    if not report_id:
        return
    try:
        report = DailyReport.objects.get(pk=report_id)
    except DailyReport.DoesNotExist:
        return

    qs = Transaction.objects.filter(report=report)
    report.total_uzs = qs.aggregate(_sum=Sum('amount_uzs'))['_sum'] or 0
    report.total_usd = qs.aggregate(_sum=Sum('amount_usd'))['_sum'] or 0
    report.total_rub = qs.aggregate(_sum=Sum('amount_rub'))['_sum'] or 0
    report.total_eur = qs.aggregate(_sum=Sum('amount_eur'))['_sum'] or 0

    # Simple details: totals grouped by counterparty for each currency
    if qs.exists():
        uzs = list(qs.values('counterparty').annotate(total=Sum('amount_uzs')))
        usd = list(qs.values('counterparty').annotate(total=Sum('amount_usd')))
        rub = list(qs.values('counterparty').annotate(total=Sum('amount_rub')))
        eur = list(qs.values('counterparty').annotate(total=Sum('amount_eur')))
        report.uzs_detail = uzs
        report.usd_detail = usd
        report.rub_detail = rub
        report.eur_detail = eur
    else:
        report.uzs_detail = None
        report.usd_detail = None
        report.rub_detail = None
        report.eur_detail = None

    report.save()


@receiver(pre_save, sender=Transaction)
def _transaction_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            prev = Transaction.objects.get(pk=instance.pk)
            instance._previous_report_id = prev.report_id
        except Transaction.DoesNotExist:
            instance._previous_report_id = None
    else:
        instance._previous_report_id = None


@receiver(post_save, sender=Transaction)
def _transaction_post_save(sender, instance, **kwargs):
    old_id = getattr(instance, '_previous_report_id', None)
    new_id = instance.report_id
    if old_id and old_id != new_id:
        _recalc_report(old_id)
    if new_id:
        _recalc_report(new_id)


@receiver(post_delete, sender=Transaction)
def _transaction_post_delete(sender, instance, **kwargs):
    if instance.report_id:
        _recalc_report(instance.report_id)

class StatTypes(models.TextChoices):
    INCOME = 'income', 'Kirim'
    EXPENSE = 'expense', 'Chiqim'
    BALANCE = 'diff', 'Qoldiq'

class Stat(models.Model):
    type = models.CharField(max_length=10, choices=StatTypes.choices)

    total_uzs = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_usd = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_rub = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_eur = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    default_uzs = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    default_usd = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    default_rub = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    default_eur = models.DecimalField(max_digits=15, decimal_places=2, default=0)
