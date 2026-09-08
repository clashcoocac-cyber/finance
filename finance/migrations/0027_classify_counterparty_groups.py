from django.db import migrations

# Cashier income-category values (from the old static IncomeCHoices list and its
# replacement) must not be mixed into the operator's person-name counterparty pool.
INCOME_CATEGORY_NAMES = ['Almashdi', 'Vozvrat rasx den', 'almashdi', 'vozvrat']


def classify(apps, schema_editor):
    Counterparty = apps.get_model('finance', 'Counterparty')
    Counterparty.objects.filter(name__in=INCOME_CATEGORY_NAMES).update(group='income')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0026_counterparty_group'),
    ]

    operations = [
        migrations.RunPython(classify, noop_reverse),
    ]
