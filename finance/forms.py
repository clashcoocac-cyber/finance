from datetime import datetime
from django import forms
from django.contrib.auth.forms import UserChangeForm
from django.shortcuts import redirect
from .models import Company, User, Transaction, DailyReport, CLICKS



class UserRegisterForm(forms.ModelForm):    
    password = forms.CharField(widget=forms.PasswordInput)
    company_name = forms.CharField(required=False)

    class Meta:
        model = User
        fields = ['username', 'role', 'company_name', 'password']

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
    other_counterparty = forms.CharField(required=False, max_length=255, label="Boshqa shaxs nomi")

    class Meta:
        model = Transaction
        fields = ['amount_usd' ,'amount_uzs', 'amount_rub', 'amount_eur', 'payment_type', 'click', 'comment', 'counterparty']
        
    def save(self, commit = ..., operator=None, date=None):
        transaction = super().save(commit=False)
        if self.cleaned_data['counterparty'] == 'other':
            transaction.counterparty = self.cleaned_data['other_counterparty']
        else:
            transaction.counterparty = self.cleaned_data['counterparty']
        transaction.operator = operator
        transaction.type = 'income'

        # If a report date is provided (operator selecting which report/day this
        # transaction belongs to), keep the current time but set the date part to
        # the provided report date. This handles shift-cross-midnight cases.
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
    
CATEGORIES = {
    'chikako': 'Chikako zavod',
    'jasur': 'Jasur un',
    'ravshan': 'Ravshan $',
    'almashdi': 'Almashdi',
    'msbb_xarajat': 'MSSB xarajat',
    'opt_xarajat': 'OPT xarajat',
    'sfb_xarajat': 'SFB xarajat',
    'rasxod_den': 'Rasxod den'
}

IncomeCHoices = [
    ('almashdi', 'Almashdi'),
    ('vozvrat', 'Vozvrat rasx den'),
    ('other', 'Boshqa'),
]

class IncomeForm(forms.ModelForm):
    countryparty = forms.ChoiceField(choices=IncomeCHoices)
    other_counterparty = forms.CharField(required=False, max_length=255, label="Boshqa shaxs nomi")
    click = forms.ChoiceField(choices=CLICKS, required=False)

    class Meta:
        model = Transaction
        fields = ['amount_usd' ,'amount_uzs', 'amount_rub', 'amount_eur', 'payment_type', 'click', 'comment', 'countryparty', 'other_counterparty']
        
    def save(self, commit = True, operator=None, date=None):
        # build transaction instance (don't save yet)
        transaction = super().save(commit=False)
        if self.cleaned_data['countryparty'] == 'other':
            transaction.counterparty = self.cleaned_data['other_counterparty'].lower()
        else:
            transaction.counterparty = self.cleaned_data['countryparty'].lower()
        transaction.operator = operator

        # parse date if provided, otherwise use today
        if date:
            try:
                parsed_date = datetime.strptime(date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                parsed_date = datetime.now().date()
        else:
            parsed_date = datetime.now().date()

        # create the report first (store date as date object)
        report = DailyReport.objects.create(
            operator=operator,
            type='income',
            is_closed=True,
            date=parsed_date
        )

        report.total_uzs = self.cleaned_data.get('amount_uzs', 0)
        report.total_usd = self.cleaned_data.get('amount_usd', 0)
        report.total_rub = self.cleaned_data.get('amount_rub', 0)
        report.total_uer = self.cleaned_data.get('amount_eur', 0)

        # use click value as detail key when payment_type is 'click'
        payment_type = self.cleaned_data.get('payment_type')
        detail_key = self.cleaned_data.get('click') if payment_type == 'click' else payment_type
        report.uzs_detail = {detail_key: int(self.cleaned_data.get('amount_uzs') or 0)}
        report.usd_detail = {detail_key: int(self.cleaned_data.get('amount_usd') or 0)}
        report.rub_detail = {detail_key: int(self.cleaned_data.get('amount_rub') or 0)}
        report.eur_detail = {detail_key: int(self.cleaned_data.get('amount_eur') or 0)}
        report.category = transaction.counterparty
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
    category = forms.CharField(max_length=100)
    amount_usd = forms.DecimalField(max_digits=15, decimal_places=2, required=False)
    amount_uzs = forms.DecimalField(max_digits=15, decimal_places=2, required=False)
    amount_rub = forms.DecimalField(max_digits=15, decimal_places=2, required=False)
    amount_eur = forms.DecimalField(max_digits=15, decimal_places=2, required=False)
    payment_type = forms.ChoiceField(choices=Transaction.PAYMENT_TYPES)
    click = forms.ChoiceField(choices=CLICKS, required=False)
    description = forms.CharField(widget=forms.Textarea, required=False)
    exp_type = forms.CharField()

    class Meta:
        fields = ['exp_type', 'category', 'amount_usd', 'amount_uzs', 'amount_rub', 'amount_eur', 'payment_type', 'description']
        
    def save(self, commit=True, operator=None, date=None):
        exp_type = self.cleaned_data.get('exp_type', None)
        if self.cleaned_data['category'] in CATEGORIES:
            category = CATEGORIES.get(self.cleaned_data['category'], 'Boshqa xarajatlar').lower()
            desc = self.cleaned_data.get('description', '')
        else:
            category = self.cleaned_data['description']
            desc=None
        
        # parse date if provided, otherwise use today
        if date:
            try:
                parsed_date = datetime.strptime(date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                parsed_date = datetime.now().date()
        else:
            parsed_date = datetime.now().date()
        
        report = DailyReport.objects.create(
            operator=operator,
            type=exp_type,
            is_closed=False,
            category=category,
            desc=desc,
            date=parsed_date
        )
        report.total_uzs = self.cleaned_data.get('amount_uzs', 0)
        report.total_usd = self.cleaned_data.get('amount_usd', 0)
        report.total_rub = self.cleaned_data.get('amount_rub', 0)
        report.total_uer = self.cleaned_data.get('amount_eur', 0)
        # decide detail key: specific click key when payment_type is 'click'
        payment_type = self.cleaned_data.get('payment_type')
        detail_key = self.cleaned_data.get('click') if payment_type == 'click' else payment_type

        report.uzs_detail = {detail_key: int(self.cleaned_data.get('amount_uzs') or 0)}
        report.usd_detail = {detail_key: int(self.cleaned_data.get('amount_usd') or 0)}
        report.rub_detail = {detail_key: int(self.cleaned_data.get('amount_rub') or 0)}
        report.eur_detail = {detail_key: int(self.cleaned_data.get('amount_eur') or 0)}
        report.save()

        transaction = Transaction.objects.create(
            type='expense',
            amount_usd=self.cleaned_data.get('amount_usd'),
            amount_uzs=self.cleaned_data.get('amount_uzs'),
            amount_rub=self.cleaned_data.get('amount_rub'),
            amount_eur=self.cleaned_data.get('amount_eur'),
            payment_type=self.cleaned_data['payment_type'],
            click=self.cleaned_data.get('click') if self.cleaned_data.get('payment_type') == 'click' else None,
            description=self.cleaned_data['description'],
            operator=operator,
            report=report,
            counterparty=category,
            date=datetime.combine(parsed_date, datetime.now().time())
        )
        transaction.save()
        return transaction
