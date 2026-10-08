"""Compatibility for existing account provisioning paths."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import StoreMembership, UserProfile


@receiver(post_save, sender=UserProfile)
def provision_initial_membership(sender, instance, created, raw=False, **kwargs):
    if raw or not instance.store_id or instance.role not in ("staff", "manager"):
        return
    if created:
        StoreMembership.objects.get_or_create(
            user_id=instance.user_id, store_id=instance.store_id,
            defaults={"role": instance.role},
        )
