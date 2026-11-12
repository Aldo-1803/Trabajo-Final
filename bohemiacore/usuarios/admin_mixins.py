class BusinessPermissionAdminMixin:
    """Require Django model permissions and effective business authority."""

    actions = None
    business_view_permissions = ()
    business_add_permissions = None
    business_change_permissions = None
    business_delete_permissions = None

    def _business_permissions_for(self, operation):
        permissions = getattr(
            self,
            f'business_{operation}_permissions',
            None,
        )
        if permissions is None:
            permissions = self.business_view_permissions
        return tuple(permissions)

    def has_business_permission(self, request, operation='view'):
        permissions = self._business_permissions_for(operation)
        return bool(permissions) and any(
            request.user.has_perm(permission)
            for permission in permissions
        )

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def has_view_permission(self, request, obj=None):
        return bool(
            self.has_business_permission(request, 'view')
            and super().has_view_permission(request, obj)
        )

    def has_add_permission(self, request):
        return bool(
            self.has_business_permission(request, 'add')
            and super().has_add_permission(request)
        )

    def has_change_permission(self, request, obj=None):
        return bool(
            self.has_business_permission(request, 'change')
            and super().has_change_permission(request, obj)
        )

    def has_delete_permission(self, request, obj=None):
        return bool(
            self.has_business_permission(request, 'delete')
            and super().has_delete_permission(request, obj)
        )


class BusinessReadOnlyAdminMixin(BusinessPermissionAdminMixin):
    """Expose legitimate technical reads but close generic domain writes."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class TechnicalSuperuserReadOnlyAdminMixin:
    """Restrict technical-only records to active Django superusers."""

    actions = None

    @staticmethod
    def _is_technical_superuser(request):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and getattr(user, 'is_staff', False)
            and getattr(user, 'is_superuser', False)
        )

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def has_view_permission(self, request, obj=None):
        return bool(
            self._is_technical_superuser(request)
            and super().has_view_permission(request, obj)
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
