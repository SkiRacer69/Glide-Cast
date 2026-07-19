from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_basic_pro_plans"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ScreenshotCaptureSignal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page_path", models.CharField(blank=True, default="", max_length=512)),
                ("signal_type", models.CharField(blank=True, default="", max_length=64)),
                ("detail", models.CharField(blank=True, default="", max_length=256)),
                ("user_agent", models.CharField(blank=True, default="", max_length=512)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="screenshotcapturesignal",
            index=models.Index(fields=["user", "created_at"], name="accounts_sc_user_id_7e8b2d_idx"),
        ),
    ]
