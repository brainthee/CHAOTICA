from django.core.exceptions import ImproperlyConfigured


class PrefetchRelatedMixin(object):
    prefetch_related = None

    def get_queryset(self):
        if self.prefetch_related is None:
            raise ImproperlyConfigured(
                "%(cls)s is missing the prefetch_related"
                "property. This must be a tuple or list."
                % {"cls": self.__class__.__name__}
            )

        if not isinstance(self.prefetch_related, (tuple, list)):
            raise ImproperlyConfigured(
                "%(cls)s's select_related property "
                "must be a tuple or list." % {"cls": self.__class__.__name__}
            )

        queryset = super(PrefetchRelatedMixin, self).get_queryset()
        return queryset.prefetch_related(*self.prefetch_related)
