from django.db import migrations, models


def fill_snapshots(apps, schema_editor):
    Order = apps.get_model("core", "Order")
    OrderOption = apps.get_model("core", "OrderOption")
    for order in Order.objects.select_related("course").iterator():
        order.course_name = order.course.name
        order.course_price = order.course.price
        opt_total = 0
        for oo in OrderOption.objects.filter(order=order).select_related("option"):
            opt_total += oo.option.price
        order.options_price = opt_total
        order.total_price = order.course_price + opt_total
        order.save(update_fields=["course_name", "course_price", "options_price", "total_price"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_seed_store"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="course_name",
            field=models.CharField(default="", max_length=50),
        ),
        migrations.AddField(
            model_name="order",
            name="course_price",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="order",
            name="options_price",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="order",
            name="total_price",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(fill_snapshots, migrations.RunPython.noop),
    ]
