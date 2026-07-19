# Generated migration: Basic / Pro tiers only

from django.db import migrations, models


def forwards_plan_values(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    Profile.objects.filter(plan_tier="club_junior").update(plan_tier="basic")
    Profile.objects.filter(plan_tier__in=("individual_masters", "coach_team", "race_department")).update(
        plan_tier="pro"
    )
    Profile.objects.filter(admin_override_plan="club_junior").update(admin_override_plan="basic")
    Profile.objects.filter(
        admin_override_plan__in=("individual_masters", "coach_team", "race_department")
    ).update(admin_override_plan="pro")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_pricing_security"),
    ]

    operations = [
        migrations.RunPython(forwards_plan_values, noop_reverse),
        migrations.AlterField(
            model_name="profile",
            name="plan_tier",
            field=models.CharField(
                choices=[("basic", "Basic"), ("pro", "Pro")],
                default="basic",
                max_length=32,
            ),
        ),
    ]
