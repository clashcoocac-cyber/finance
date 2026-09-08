from datetime import datetime, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.db.models.functions import Lower
from django.views.generic import TemplateView

from finance.mixins import BossRequiredMixin, CashierRequiredMixin, OperatorRequiredMixin
from finance.models import Category, DailyReport, Transaction


class ReportListBase(LoginRequiredMixin, TemplateView):
    """Daily-report listing with the filter set shared by all three roles."""

    report_types = None
    operator_scoped = False
    default_days = 7

    def get_queryset(self):
        reports = DailyReport.objects.select_related('operator', 'operator__company')
        if self.report_types:
            reports = reports.filter(type__in=self.report_types)
        if self.operator_scoped:
            reports = reports.filter(operator=self.request.user)
        return reports

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request

        context['from'] = request.GET.get('from') or (
            datetime.today() - timedelta(days=self.default_days)
        ).strftime('%Y-%m-%d')
        context['to'] = request.GET.get('to') or datetime.today().strftime('%Y-%m-%d')
        context['q'] = request.GET.get('q') or ''
        context['type'] = request.GET.get('type') or ''
        context['categories'] = request.GET.getlist('category')

        reports = self.get_queryset()
        reports = reports.filter(
            date__gte=datetime.strptime(context['from'], '%Y-%m-%d').date(),
            date__lte=datetime.strptime(context['to'], '%Y-%m-%d').date(),
        )
        if context['type']:
            reports = reports.filter(type=context['type'])
        if context['q']:
            q = context['q'].casefold()
            reports = reports.annotate(
                op_username_l=Lower('operator__username'),
                company_name_l=Lower('operator__company__name'),
                category_l=Lower('category'),
            ).filter(
                Q(op_username_l__icontains=q)
                | Q(company_name_l__icontains=q)
                | Q(category_l__icontains=q)
            )
        if context['categories']:
            reports = reports.filter(category__in=context['categories'])

        reports = reports.order_by('-date')
        context['reports'] = reports
        context['pending_count'] = reports.filter(is_closed=False).count()
        context['confirmed_count'] = reports.filter(is_closed=True).count()
        context['category_options'] = Category.objects.filter(is_active=True)
        return context


class BossReportsView(BossRequiredMixin, ReportListBase):
    template_name = 'reports/boss_reports.html'


class CashierReportsView(CashierRequiredMixin, ReportListBase):
    template_name = 'reports/cashier_reports.html'
    report_types = ['income']


class OperatorReportsView(OperatorRequiredMixin, ReportListBase):
    template_name = 'reports/operator_reports.html'
    operator_scoped = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report_date = self.request.GET.get('report_date') or datetime.today().strftime('%Y-%m-%d')
        context['report_date'] = report_date
        context['is_expired'] = (
            datetime.today().date() - datetime.strptime(report_date, '%Y-%m-%d').date()
        ) > timedelta(days=3)
        # Transactions not yet rolled into a daily report — exactly what
        # "Kassani yopish" will sweep up for the selected date.
        context['unreported_count'] = Transaction.objects.filter(
            operator=self.request.user,
            report__isnull=True,
            date__date=datetime.strptime(report_date, '%Y-%m-%d').date(),
        ).count()
        return context
