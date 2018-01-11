from django.db.models import Q
from django.db.models.query import QuerySet


class CategoryQuerySet(QuerySet):
    def active(self):
        return self.filter(active=True)

    def govexec(self):
        ge_root_category = self.model.objects.get(slug='categories')

        return self.filter(
            (
                Q(lft__lte=ge_root_category.rght) &
                Q(lft__gte=ge_root_category.lft) &
                Q(tree_id=ge_root_category.tree_id)
            ) |
            Q(slug='govexec-sponsored')
        )
