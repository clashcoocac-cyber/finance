from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import Company, User



class UserRegisterForm(UserCreationForm):
    company_name = forms.CharField(required=False)

    class Meta:
        model = User
        fields = ['username', 'role', 'company_name', 'password1', 'password2']

    def form_valid(self, form):
        print("form_valid chaqirildi!")   # Bu chiqadi
        user = form.save()                # Bu orqali form.save() ichidagi printlar ham chiqadi
        ...
        return super().form_valid(form)

    def save(self, commit = True):
        company_name = self.cleaned_data.pop('company_name', '')
        print('----', company_name)
        user = super().save(commit=False)
        print('----', company_name, user)
        
        if company_name:
            company, created = Company.objects.get_or_create(name=company_name)
            user.company = company
        else:
            user.company = None 
        if commit:
            user.save()
        return user


class UserUpdateForm(UserChangeForm):
    password = None  # Parolni o'zgartirish formda bo'lmaydi
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'company']
