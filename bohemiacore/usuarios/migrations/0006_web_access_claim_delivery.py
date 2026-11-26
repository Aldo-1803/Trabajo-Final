from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('usuarios', '0005_walkin_rate_bucket')]

    operations = [
        migrations.CreateModel(
            name='WebAccessClaimDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_user_id', models.BigIntegerField(null=True)),
                ('contact_digest', models.CharField(max_length=64)),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
