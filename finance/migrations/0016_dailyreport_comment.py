# Generated by Django 5.2.4 on 2025-07-27 03:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0015_transaction_comment'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailyreport',
            name='comment',
            field=models.TextField(blank=True, null=True),
        ),
    ]
