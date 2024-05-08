# Generated by Django 5.0.2 on 2024-02-18 07:04

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('translator', '0012_geminitranslator_interval'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeepLWebTranslator',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Name')),
                ('valid', models.BooleanField(null=True, verbose_name='Valid')),
                ('max_characters', models.IntegerField(default=50000)),
                ('interval', models.IntegerField(default=5, verbose_name='Request Interval(s)')),
                ('proxy', models.URLField(blank=True, default=None, null=True, verbose_name='Proxy(optional)')),
            ],
            options={
                'verbose_name': 'DeepL Web',
                'verbose_name_plural': 'DeepL Web',
            },
        ),
    ]
