# mapas/roles.py
from django.contrib.auth.models import Group

MAP_ADMIN_GROUP = "map_admin"

def is_map_admin(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=MAP_ADMIN_GROUP).exists()

def get_or_create_map_admin_group():
    group, _ = Group.objects.get_or_create(name=MAP_ADMIN_GROUP)
    return group
