from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_rename_accounts_sc_user_id_7e8b2d_idx_accounts_sc_user_id_3fdbcf_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="sport_access",
            field=models.CharField(default="alpine", max_length=16),
        ),
        migrations.AlterField(
            model_name="profile",
            name="plan_tier",
            field=models.CharField(
                choices=[("basic", "Basic"), ("pro", "Pro"), ("all", "All Access")],
                default="basic",
                max_length=32,
            ),
        ),
    ]
