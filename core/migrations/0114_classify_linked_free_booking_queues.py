from django.db import migrations


def classify_linked_queues(apps, schema_editor):
    # Legacy intake lanes can have a cast login. Account presence is not a
    # reliable indication of whether this is a real therapist.
    Cast = apps.get_model('core', 'Cast')
    ids = [pk for pk, name in Cast.objects.values_list('pk', 'name')
           if name.strip() == 'フリー']
    Cast.objects.filter(pk__in=ids).update(is_booking_queue=True)


class Migration(migrations.Migration):
    dependencies = [('core', '0113_free_booking_queue')]
    operations = [migrations.RunPython(classify_linked_queues, migrations.RunPython.noop)]
