"""
This is the base class on which to build a hierarchical category-like model
with customizable metadata and its own name space.
"""

from django import forms
from django.contrib import admin
from django.contrib.sites.models import Site
from django.db import models
from django.template.defaultfilters import slugify
from django.utils.encoding import force_unicode
from django.utils.translation import ugettext_lazy as _

from mptt.models import MPTTModel
from mptt.fields import TreeForeignKey
from mptt.managers import TreeManager

from categories.editor.tree_editor import TreeEditor
from categories.querysets import CategoryQuerySet
from categories.settings import ALLOW_SLUG_CHANGE, SLUG_TRANSLITERATOR


class CategoryManager(models.Manager):
    def get_query_set(self):
        return CategoryQuerySet(self.model)

    def active(self):
        """
        Only categories that are active
        """
        return self.get_query_set().active()

    def govexec(self):
        return self.get_query_set().govexec()


class CategoryBase(MPTTModel):
    """
    This base model includes the absolute bare bones fields and methods. One
    could simply subclass this model and do nothing else and it should work.
    """
    parent = TreeForeignKey('self',
        blank=True,
        null=True,
        related_name='children',
        verbose_name=_('parent'))
    name = models.CharField(max_length=100, verbose_name=_('name'))
    slug = models.SlugField(verbose_name=_('slug'))
    active = models.BooleanField(default=True, verbose_name=_('active'))
    unicode_name = models.CharField(
        blank=True,
        null=True,
        default=None,
        max_length=255)
    # TODO: I would like to make this required if we can eliminate edge cases
    site = models.ForeignKey(Site, blank=True, null=True)

    objects = CategoryManager()
    tree = TreeManager()

    def save(self, *args, **kwargs):
        """
        While you can activate an item without activating its descendants,
        It doesn't make sense that you can deactivate an item and have its
        decendants remain active.
        """
        if not self.slug:
            self.slug = slugify(SLUG_TRANSLITERATOR(self.name))[:50]

        super(CategoryBase, self).save(*args, **kwargs)

        if not self.active:
            for item in self.get_descendants():
                if item.active != self.active:
                    item.active = self.active
                    item.save()

    def __unicode__(self):
        if hasattr(self, 'unicode_name') and self.unicode_name:
            return self.unicode_name
        return self.generate_unicode_name()

    def generate_unicode_name(self):
        ancestors = self.get_ancestors()
        # remove top-level category from display
        ancestors_list = list(ancestors)
        # added hack to show "magazine" in the section title
        if len(ancestors_list) > 0 and not ancestors_list[0].slug == "magazine" and not ancestors_list[0].slug == "nextgov-categories":
            del ancestors_list[0]
        return ' > '.join([force_unicode(i.name) for i in ancestors] + [self.name, ])

    def all_categories(self, delimiter='::'):
        if hasattr(self, '__all_categories'):
            return self.__all_categories
        self.__all_categories = []
        for category in self.get_ancestors(include_self=True):
            tmp = []
            for existing in self.__all_categories:
                tmp.append(existing)
            tmp.append(category.name)
            self.__all_categories.append(delimiter.join(tmp))
        return self.__all_categories

    class Meta:
        abstract = True
        unique_together = (('parent', 'name'),('tree_id', 'slug'),)
        ordering = ('tree_id', 'lft')

    class MPTTMeta:
        order_insertion_by = 'name'


class CategoryBaseAdminForm(forms.ModelForm):
    def clean_slug(self):
        if self.instance is None or not ALLOW_SLUG_CHANGE:
            self.cleaned_data['slug'] = slugify(self.cleaned_data['name'])
        return self.cleaned_data['slug'][:50]

    def clean(self):

        super(CategoryBaseAdminForm, self).clean()

        if not self.is_valid():
            return self.cleaned_data

        opts = self._meta

        # Validate slug (no duplicate slugs within same tree_id)
        kwargs = {}
        this_tree_slugs = []
        if self.cleaned_data.get('parent', None) is None:
            # This is a top level category, so its tree_id cannot be checked
            pass
        else:
            # Retrieve all other slugs in the same tree (using the tree_id of the parent category)
            parent_tree_id = int(self.cleaned_data['parent'].tree_id)
            this_tree_slugs = [c['slug'] for c in opts.model.objects.filter(
                                    tree_id=parent_tree_id).values('id', 'slug'
                                    ) if c['id'] != self.instance.id]
        # Raise error if any other slugs in the same tree match the new category slug
        if self.cleaned_data['slug'] in this_tree_slugs:
            raise forms.ValidationError(_('The slug must be unique among '
                                          ' items in the same tree.'))

        # Validate Category Parent
        # Make sure the category doesn't set itself or any of its children as
        # its parent.
        decendant_ids = self.instance.get_descendants().values_list('id', flat=True)
        if self.cleaned_data.get('parent', None) is None or self.instance.id is None:
            return self.cleaned_data
        elif self.cleaned_data['parent'].id == self.instance.id:
            raise forms.ValidationError(_("You can't set the parent of the "
                                          "item to itself."))
        elif self.cleaned_data['parent'].id in decendant_ids:
            raise forms.ValidationError(_("You can't set the parent of the "
                                          "item to a descendant."))
        return self.cleaned_data


class CategoryBaseAdmin(TreeEditor, admin.ModelAdmin):
    form = CategoryBaseAdminForm
    list_display = ('name', 'active')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}

    actions = ['activate', 'deactivate']

    def get_actions(self, request):
        actions = super(CategoryBaseAdmin, self).get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def deactivate(self, request, queryset):
        """
        Set active to False for selected items
        """
        selected_cats = self.model.objects.filter(
            pk__in=[int(x) for x in request.POST.getlist('_selected_action')])

        for item in selected_cats:
            if item.active:
                item.active = False
                item.save()
                item.children.all().update(active=False)
    deactivate.short_description = _('Deactivate selected categories and their children')

    def activate(self, request, queryset):
        """
        Set active to True for selected items
        """
        selected_cats = self.model.objects.filter(
            pk__in=[int(x) for x in request.POST.getlist('_selected_action')])

        for item in selected_cats:
            item.active = True
            item.save()
            item.children.all().update(active=True)
    activate.short_description = _('Activate selected categories and their children')
