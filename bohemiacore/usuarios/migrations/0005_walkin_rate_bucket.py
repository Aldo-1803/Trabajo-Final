from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('usuarios', '0004_enforce_nonblank_email')]

    operations = [
        migrations.CreateModel(
            name='WalkInRateBucket',
            fields=[
                ('key', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('hits', models.PositiveIntegerField()),
                ('expires_at', models.DateTimeField(db_index=True)),
            ],
        ),
    ]
