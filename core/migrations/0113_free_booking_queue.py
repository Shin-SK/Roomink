from django.db import migrations, models


def mark_existing_queues(apps, schema_editor):
    # Existing staff-created 「フリー」 rows are intake lanes, not extra staff.
    apps.get_model('core', 'Cast').objects.filter(
        name='フリー', user__isnull=True,
    ).update(is_booking_queue=True)


def protect_pending_on_reverse(apps, schema_editor):
    if apps.get_model('core', 'Order').objects.filter(is_free_pending=True, status='REQUESTED').exists():
        raise RuntimeError('担当未定のフリー受付が残っています。受付を処理してから移行を戻してください。')


class Migration(migrations.Migration):
    dependencies = [('core', '0112_checkout_store_registration')]
    operations = [
        migrations.AddField(model_name='cast', name='is_booking_queue', field=models.BooleanField(default=False, db_default=False, help_text='担当未定のフリー受付用。実在の担当者ではありません。')),
        migrations.AddField(model_name='order', name='is_free_pending', field=models.BooleanField(default=False, db_default=False, help_text='フリー受付・担当選択待ち')),
        migrations.AddIndex(model_name='order', index=models.Index(fields=['store','is_free_pending','status','start'], name='order_free_queue_idx')),
        migrations.AddConstraint(model_name='order', constraint=models.CheckConstraint(condition=models.Q(is_free_pending=False) | models.Q(status__in=['REQUESTED','CANCELLED'], room__isnull=True, nomination_fee_price=0), name='free_queue_pending_state')),
        migrations.RunPython(mark_existing_queues, protect_pending_on_reverse),
    ]
