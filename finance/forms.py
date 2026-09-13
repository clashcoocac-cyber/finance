from datetime import datetime
from django import forms
from django.contrib.auth.forms import UserChangeForm
from django.shortcuts import redirect
from .models import Company, User, Transaction, DailyReport, CLICKS, Category, Counterparty


# Uzbek labels shared by every money form; errors are shown as "label: message".
AMOUNT_LABELS = {
    'amount_uzs': "So'm", 'amount_usd': 'Dollar', 'amount_rub': 'Rubl', 'amount_eur': 'Yevro',
    'payment_type': "To'lov turi", 'click': 'Click karta',
    'comment': 'Izoh', 'description': 'Tavsif',
}


class UserRegisterForm(forms.ModelForm):    
    password = forms.CharField(widget=forms.PasswordInput)
    company_name = forms.CharField(required=False)

    class Meta:
        model = User
        fields = ['username', 'role', 'company_name', 'password']
        labels = {'username': 'Login', 'role': 'Rol', 'company_name': 'Kompaniya', 'password': 'Parol'}

    def save(self, commit = True):
        company_name = self.cleaned_data.pop('company_name', '')
        password = self.cleaned_data.pop('password')

        user = super().save(commit=False)
        user.set_password(password)
        
        if company_name:
            company, _ = Company.objects.get_or_create(name=company_name)
            user.company = company
        else:
            user.company = None 

        if commit:
            user.save()
        return user


class UserUpdateForm(UserChangeForm):
    user_id = forms.IntegerField()
    new_password = forms.CharField(widget=forms.PasswordInput, required=False)
    company_name = forms.CharField(required=False)

    class Meta:
        model = User
        fields = ['user_id', 'username', 'new_password', 'company_name']

    def save(self, commit = True, **kwargs):
        user = super().save(commit=False)

        print(self.cleaned_data)

        new_password = self.cleaned_data.get('new_password')
        if new_password:
            user.set_password(new_password)

        company_name = self.cleaned_data.get('company_name')

        company, _ = Company.objects.get_or_create(name=company_name)
        user.company = company

        if commit:
            user.save()

        return user


class TransactionFrom(forms.ModelForm):
    counterparty = forms.ChoiceField(choices=[])
    other_counterparty = forms.CharField(required=False, max_length=255, label="Boshqa shaxs nomi")

    class Meta:
        model = Transaction
        fields = ['amount_usd', 'amount_uzs', 'amount_rub', 'amount_eur', 'payment_type', 'click', 'comment', 'counterparty']
        labels = {**AMOUNT_LABELS, 'counterparty': 'Kimdan olindi'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['counterparty'].choices = (
            [('', '-- Tanlang --')] +
            [(c.name, c.name) for c in Counterparty.objects.filter(is_active=True, group='person')] +
            [('__new__', "+ Yangi qo'shish")]
        )

    def clean(self):
        cleaned_data = super().clean()
        counterparty = cleaned_data.get('counterparty')
        other = (cleaned_data.get('other_counterparty') or '').strip()
        if counterparty == '__new__':
            if not other:
                self.add_error('other_counterparty', "Yangi shaxs nomini kiriting.")
            else:
                cleaned_data['counterparty'] = other
        return cleaned_data

    def save(self, commit=True, operator=None, date=None):
        transaction = super().save(commit=False)
        counterparty = self.cleaned_data['counterparty']
        Counterparty.objects.get_or_create(
            name__iexact=counterparty, group='person', defaults={'name': counterparty}
        )
        transaction.counterparty = counterparty
        transaction.operator = operator
        transaction.type = 'income'

        if date:
            try:
                parsed_date = datetime.strptime(date, '%Y-%m-%d').date()
                now_time = datetime.now().time()
                transaction.date = datetime.combine(parsed_date, now_time)
            except Exception:
                transaction.date = datetime.now()
        else:
            transaction.date = datetime.now()

        if commit:
            transaction.save()

        return transaction

class IncomeForm(forms.ModelForm):
    counterparty = forms.ChoiceField(choices=[], label="Manba (Kirim manbai)")
    other_counterparty = forms.CharField(required=False, max_length=255, label="Yangi manba nomi")
    purpose = forms.ChoiceField(choices=[], label="Maqsad (Kirim turi)", required=False)
    click = forms.ChoiceField(choices=CLICKS, required=False)

    class Meta:
        model = Transaction
        fields = ['amount_usd' ,'amount_uzs', 'amount_rub', 'amount_eur', 'payment_type', 'click', 'comment', 'counterparty', 'other_counterparty']
        labels = AMOUNT_LABELS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['counterparty'].choices = (
            [('', '-- Tanlang --')] +
            [(c.name, c.name) for c in Counterparty.objects.filter(is_active=True, group='income')] +
            [('__new__', "+ Yangi qo'shish")]
        )
        # Maqsad is a fixed DB-level choice like the expense form's
        # Chiqim/Xarajat pair — not a user-extensible list.
        self.fields['purpose'].choices = (
            [('', '-- Tanlang --')] +
            [('foyda', 'Foyda'), ('tushum', 'Tushum')]
        )

    def clean(self):
        cleaned_data = super().clean()
        counterparty = cleaned_data.get('counterparty')
        other = (cleaned_data.get('other_counterparty') or '').strip()
        if counterparty == '__new__':
            if not other:
                self.add_error('other_counterparty', "Yangi manba nomini kiriting.")
            else:
                cleaned_data['counterparty'] = other
        return cleaned_data

    def save(self, commit = True, operator=None, date=None):
        # build transaction instance (don't save yet)
        transaction = super().save(commit=False)
        counterparty = self.cleaned_data['counterparty']
        Counterparty.objects.get_or_create(
            name__iexact=counterparty, group='income', defaults={'name': counterparty}
        )
        transaction.counterparty = counterparty
        transaction.operator = operator

        # handle purpose/category — fixed choice, stored on the report
        purpose = self.cleaned_data.get('purpose') or ''
        # parse date if provided, otherwise use today
        if date:
            try:
                parsed_date = datetime.strptime(date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                parsed_date = datetime.now().date()
        else:
            parsed_date = datetime.now().date()

        # create the report first (store date as date object);
        # category = counterparty, purpose goes into desc ("Maqsad: X")
        report = DailyReport.objects.create(
            operator=operator,
            type='income',
            is_closed=True,
            date=parsed_date,
            category=transaction.counterparty,
            desc=f"Maqsad: {purpose}" if purpose else None,
        )

        report.total_uzs = self.cleaned_data.get('amount_uzs') or 0
        report.total_usd = self.cleaned_data.get('amount_usd') or 0
        report.total_rub = self.cleaned_data.get('amount_rub') or 0
        report.total_eur = self.cleaned_data.get('amount_eur') or 0

        # use click value as detail key when payment_type is 'click'
        payment_type = self.cleaned_data.get('payment_type')
        detail_key = self.cleaned_data.get('click') if payment_type == 'click' else payment_type
        report.uzs_detail = {detail_key: float(self.cleaned_data.get('amount_uzs') or 0)}
        report.usd_detail = {detail_key: float(self.cleaned_data.get('amount_usd') or 0)}
        report.rub_detail = {detail_key: float(self.cleaned_data.get('amount_rub') or 0)}
        report.eur_detail = {detail_key: float(self.cleaned_data.get('amount_eur') or 0)}
        report.save()

        # finish transaction fields and save (ensure non-null date for stats/admin)
        transaction.report = report
        transaction.type = 'income'
        transaction.click = self.cleaned_data.get('click') if payment_type == 'click' else None
        # combine parsed date with current time
        transaction.date = datetime.combine(parsed_date, datetime.now().time())
        if commit:
            transaction.save()

        return transaction

class ExpenseForm(forms.Form):
    category = forms.ChoiceField(choices=[], label='Kategoriya')
    new_category = forms.CharField(required=False, max_length=100, label="Yangi kategoriya nomi")
    amount_usd = forms.DecimalField(max_digits=15, decimal_places=2, required=False, label=AMOUNT_LABELS['amount_usd'])
    amount_uzs = forms.DecimalField(max_digits=15, decimal_places=2, required=False, label=AMOUNT_LABELS['amount_uzs'])
    amount_rub = forms.DecimalField(max_digits=15, decimal_places=2, required=False, label=AMOUNT_LABELS['amount_rub'])
    amount_eur = forms.DecimalField(max_digits=15, decimal_places=2, required=False, label=AMOUNT_LABELS['amount_eur'])
    payment_type = forms.ChoiceField(choices=Transaction.PAYMENT_TYPES, label=AMOUNT_LABELS['payment_type'])
    click = forms.ChoiceField(choices=CLICKS, required=False, label=AMOUNT_LABELS['click'])
    description = forms.CharField(widget=forms.Textarea, required=False, label=AMOUNT_LABELS['description'])
    exp_type = forms.CharField(label='Maqsad')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_categories = Category.objects.filter(is_active=True)
        self.category_options = [{'name': c.name, 'group': c.group} for c in active_categories]
        self.fields['category'].choices = (
            [('', '-- Tanlang --')] +
            [(c.name, c.name) for c in active_categories] +
            [('__new__', "+ Yangi qo'shish")]
        )

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        new_category = (cleaned_data.get('new_category') or '').strip()
        if category == '__new__':
            if not new_category:
                self.add_error('new_category', "Yangi kategoriya nomini kiriting.")
            else:
                cleaned_data['category'] = new_category.lower()
        return cleaned_data

    def save(self, commit=True, operator=None, date=None):
        exp_type = self.cleaned_data.get('exp_type')
        category = self.cleaned_data['category']
        Category.objects.get_or_create(
            name__iexact=category,
            defaults={'name': category, 'group': exp_type if exp_type in dict(Category.GROUPS) else 'expense'},
        )
        desc = self.cleaned_data.get('description') or None
        # expense "maqsad" — the Chiqim/Xarajat kind, stored as a fixed
        # "Maqsad:" prefix in desc like the income form does
        kind = 'Xarajat' if exp_type == 'xarajat' else 'Chiqim'
        desc = f"Maqsad: {kind.lower()}" + (f" — {desc}" if desc else '')

        if date:
            try:
                parsed_date = datetime.strptime(date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                parsed_date = datetime.now().date()
        else:
            parsed_date = datetime.now().date()

        report = DailyReport.objects.create(
            operator=operator, type=exp_type, is_closed=False,
            category=category, desc=desc, date=parsed_date,
        )
        report.total_uzs = self.cleaned_data.get('amount_uzs') or 0
        report.total_usd = self.cleaned_data.get('amount_usd') or 0
        report.total_rub = self.cleaned_data.get('amount_rub') or 0
        report.total_eur = self.cleaned_data.get('amount_eur') or 0

        payment_type = self.cleaned_data.get('payment_type')
        detail_key = self.cleaned_data.get('click') if payment_type == 'click' else payment_type
        report.uzs_detail = {detail_key: float(self.cleaned_data.get('amount_uzs') or 0)}
        report.usd_detail = {detail_key: float(self.cleaned_data.get('amount_usd') or 0)}
        report.rub_detail = {detail_key: float(self.cleaned_data.get('amount_rub') or 0)}
        report.eur_detail = {detail_key: float(self.cleaned_data.get('amount_eur') or 0)}
        report.save()

        transaction = Transaction.objects.create(
            type='expense',
            amount_usd=self.cleaned_data.get('amount_usd'),
            amount_uzs=self.cleaned_data.get('amount_uzs'),
            amount_rub=self.cleaned_data.get('amount_rub'),
            amount_eur=self.cleaned_data.get('amount_eur'),
            payment_type=payment_type,
            click=self.cleaned_data.get('click') if payment_type == 'click' else None,
            description=self.cleaned_data['description'],
            operator=operator,
            report=report,
            counterparty=category,
            date=datetime.combine(parsed_date, datetime.now().time()),
        )
        return transaction
