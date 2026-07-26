from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.db.models import ProtectedError
from .models import Branch


@receiver(pre_delete, sender=Branch)
def guard_branch_dependent_staff_on_delete(sender, instance, **kwargs):
    from users.models import User
    dependent_qs = User.objects.filter(
        branch=instance,
        role__in=[User.Role.STAFF, User.Role.BRANCH_MANAGER],
    )
    if dependent_qs.exists():
        raise ProtectedError(
            f"Cannot delete branch '{instance.name}': staff members are still "
            f"assigned to it. Reassign or deactivate them first.",
            dependent_qs,
        )