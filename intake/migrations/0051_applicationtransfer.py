# -*- coding: utf-8 -*-
# Generated by Django 1.10.1 on 2017-03-14 01:21
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('intake', '0050_application_created_updated_transferred'),
    ]

    operations = [
        migrations.CreateModel(
            name='ApplicationTransfer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated', models.DateTimeField(auto_now=True, null=True)),
                ('reason', models.TextField(blank=True)),
                ('new_application', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='incoming_transfers', to='intake.Application')),
                ('status_update', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='transfer', to='intake.StatusUpdate')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]