from rest_framework.permissions import BasePermission

from .models import User


def is_rider(user):
    return bool(user and user.is_authenticated and hasattr(user, 'rider_profile'))


def has_role(user, *roles):
    return bool(user and user.is_authenticated and user.is_active and user.role in roles)


class IsCustomerRole(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, User.Role.CUSTOMER)


class IsRider(BasePermission):
    """Rider is a capability granted by a validated RiderProfile, not a role string."""

    def has_permission(self, request, view):
        return bool(request.user.is_active and is_rider(request.user))


class IsStaffOrAbove(BasePermission):
    """Operational branch staff, excluding accounts dedicated to rider duties."""

    def has_permission(self, request, view):
        return has_role(
            request.user,
            User.Role.STAFF,
            User.Role.INVENTORY_MANAGER,
            User.Role.BRANCH_MANAGER,
            User.Role.SUPER_ADMIN,
        ) and not is_rider(request.user)


class IsBranchManagerOrAbove(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN)


class IsInventoryController(BasePermission):
    """Branch inventory managers, branch managers and super admins."""

    def has_permission(self, request, view):
        return has_role(
            request.user,
            User.Role.INVENTORY_MANAGER,
            User.Role.BRANCH_MANAGER,
            User.Role.SUPER_ADMIN,
        )


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, User.Role.SUPER_ADMIN)


def can_access_branch(user, branch_id):
    """Super admins are global; all other privileged users are branch-bound."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.role == User.Role.SUPER_ADMIN:
        return True
    return user.branch_id is not None and user.branch_id == branch_id


def is_pos_operator(user):
    return has_role(
        user, User.Role.STAFF, User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN,
    ) and not is_rider(user)
