from django.db import migrations

INCOME_COUNTERPARTIES_SEED = []


def backfill(apps, schema_editor):
    Counterparty = apps.get_model('finance', 'Counterparty')
    for name in INCOME_COUNTERPARTIES_SEED:
        Counterparty.objects.get_or_create(name__iexact=name, defaults={'name': name})
    # group is set on these rows by migration 0027, once the `group` field exists.


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0024_backfill_category_counterparty'),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
