# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-09-20 22:05
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('intake', '0027_applicant_applicationevent'),
    ]

    operations = [
        migrations.AddField(
            model_name='formsubmission',
            name='applicant',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='form_submissions', to='intake.Applicant'),
        ),
    ]
