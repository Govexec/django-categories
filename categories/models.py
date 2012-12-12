from django.core.urlresolvers import reverse
from django.db import models
from django.utils.encoding import force_unicode
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.core.files.storage import get_storage_class
from django.template.defaultfilters import slugify
from django.utils.translation import ugettext as _

from mptt.models import MPTTModel

from settings import (RELATION_MODELS, RELATIONS, THUMBNAIL_UPLOAD_PATH, 
                        THUMBNAIL_STORAGE)

from django.db import transaction

STORAGE = get_storage_class(THUMBNAIL_STORAGE)


@transaction.commit_manually
def flush_transaction():
    transaction.commit()


class CategoryManager(models.Manager):
    """
    A manager that adds an "active()" method for all active categories
    """
    def active(self):
        """
        Only categories that are active
        """
        return self.get_query_set().filter(active=True)

class Category(MPTTModel):
    parent = models.ForeignKey('self', 
        blank=True, 
        null=True, 
        related_name="children", 
        help_text="Leave this blank for an Category Tree", 
        verbose_name='Parent')
    name = models.CharField(max_length=100)
    is_blog = models.BooleanField(db_index=True)
    thumbnail = models.FileField(
        upload_to=THUMBNAIL_UPLOAD_PATH, 
        null=True, blank=True,
        storage=STORAGE(),)
    thumbnail_width = models.IntegerField(blank=True, null=True)
    thumbnail_height = models.IntegerField(blank=True, null=True)
    order = models.IntegerField(db_index=True, blank=True, null=True)
    slug = models.SlugField(db_index=True)
    alternate_title = models.CharField(
        blank=True,
        default="",
        max_length=100,
        help_text="An alternative title to use on pages with this category.")
    alternate_url = models.URLField(
        blank=True,
        verify_exists=False,
        help_text="An alternative URL to use instead of the one derived from the category hierarchy.")
    description = models.TextField(blank=True, null=True)
    meta_keywords = models.CharField(
        blank=True,
        default="",
        max_length=255,
        help_text="Comma-separated keywords for search engines.")
    meta_extra = models.TextField(
        blank=True,
        default="",
        help_text="(Advanced) Any additional HTML to be placed verbatim in the &lt;head&gt;")
    active = models.BooleanField(default=True)

    show_converser_ad = models.BooleanField("Show a converser ad?", default=False,
        help_text="Select to enable a converser ad for the category page.  A 600x300 converser ad unit must be " \
                  "active in Dart.")

    unicode_name = models.CharField(
        blank=True,
        default=None,
        max_length=255)

    objects = CategoryManager()

    @property
    def display_converser(self):
        """
        This method flushes the database cache to get the current value of the "show_converser_ad" field
        """
        if not hasattr(self, '_uncached_show_converser_ad'):
            flush_transaction()
            uncached_show_converser_ad_list = Category.objects.values('show_converser_ad').filter(id=self.id)
            if len(uncached_show_converser_ad_list) > 0:
                if uncached_show_converser_ad_list[0]['show_converser_ad']:
                    self._uncached_show_converser_ad = True
                else:
                    self._uncached_show_converser_ad = False
        return self._uncached_show_converser_ad

    @property
    def short_title(self):
        return self.name
    
    def get_absolute_url(self):
        """Return a path"""
        if self.alternate_url:
            return self.alternate_url
        prefix = reverse('categories_tree_list')
        ancestors = list(self.get_ancestors()) + [self,]

        # remove top-level category from display
        if len(ancestors) > 0:
            del ancestors[0]

        return prefix + '/'.join([force_unicode(i.slug) for i in ancestors]) + '/'
    
    if RELATION_MODELS:
        def get_related_content_type(self, content_type):
            """
            Get all related items of the specified content type
            """
            return self.categoryrelation_set.filter(
                content_type__name=content_type)
        
        def get_relation_type(self, relation_type):
            """
            Get all relations of the specified relation type
            """
            return self.categoryrelation_set.filter(relation_type=relation_type)
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:50]
        if self.thumbnail:
            from django.core.files.images import get_image_dimensions
            import django
            if django.VERSION[1] < 2:
                width, height = get_image_dimensions(self.thumbnail.file)
            else:
                width, height = get_image_dimensions(self.thumbnail.file, close=True)
        else:
            width, height = None, None
        
        self.thumbnail_width = width
        self.thumbnail_height = height
        
        super(Category, self).save(*args, **kwargs)
        
        for item in self.get_descendants():
            if item.active != self.active:
                item.active = self.active
                item.save()
    
    class Meta:
        verbose_name_plural = 'categories'
        unique_together = ('parent', 'name')
        ordering = ('tree_id', 'lft')
    
    class MPTTMeta:
        verbose_name_plural = 'categories'
        unique_together = ('parent', 'name')
        ordering = ('tree_id', 'lft')
        order_insertion_by = 'name'
    
    def __unicode__(self):

        if self.unicode_name:
            return self.unicode_name

        return self.generate_unicode_name()

    def generate_unicode_name(self):

        ancestors = self.get_ancestors()

        # remove top-level category from display
        ancestors_list = list(ancestors)

        # added hack to show "magazine" in the section title
        if len(ancestors_list) > 0 and not ancestors_list[0].slug == "magazine" and not ancestors_list[0].slug == "nextgov-categories":
            del ancestors_list[0]

        return ' > '.join([force_unicode(i.name) for i in ancestors_list]+[self.name,])


if RELATION_MODELS:
    category_relation_limits = reduce(lambda x,y: x|y, RELATIONS)
    class CategoryRelationManager(models.Manager):
        def get_content_type(self, content_type):
            qs = self.get_query_set()
            return qs.filter(content_type__name=content_type)
        
        def get_relation_type(self, relation_type):
            qs = self.get_query_set()
            return qs.filter(relation_type=relation_type)
    
    class CategoryRelation(models.Model):
        """Related story item"""
        story = models.ForeignKey(Category)
        content_type = models.ForeignKey(
            ContentType, limit_choices_to=category_relation_limits)
        object_id = models.PositiveIntegerField()
        content_object = generic.GenericForeignKey('content_type', 'object_id')
        relation_type = models.CharField(_("Relation Type"), 
            max_length="200", 
            blank=True, 
            null=True,
            help_text=_("A generic text field to tag a relation, like 'leadphoto'."))
        
        objects = CategoryRelationManager()
        
        def __unicode__(self):
            return u"CategoryRelation"
