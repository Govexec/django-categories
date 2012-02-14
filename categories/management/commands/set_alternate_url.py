from django.core.management.base import BaseCommand, CommandError
from categories.models import Category

class Command(BaseCommand):
    """
    Alter one or more models' tables with the registered attributes
    """
    
    def handle(self, *args, **options):

        from django.db.models import Q
        root_category = Category.objects.get(slug='categories')
        # uncomment to exclude the root
        root_category.lft += 1
        root_category.rght -= 1
        # limit to "categories"
        categories = Category.objects.filter(lft__lte=root_category.rght,
                                            lft__gte=root_category.lft,
                                            tree_id=root_category.tree_id)

        for category in categories:
            if not category.alternate_url:
                print "%s=[%s]" % (category.name, category.get_absolute_url(),)
                category.alternate_url = category.get_absolute_url()
                category.save()

