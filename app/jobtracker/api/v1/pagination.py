from rest_framework.pagination import PageNumberPagination


class StandardResultsPagination(PageNumberPagination):
    """Standard page-number pagination for the /api/v1/ API.

    Deliberately separate from the global ``DatatablesPageNumberPagination`` so
    the versioned API returns a clean ``{count, next, previous, results}`` shape
    regardless of the request's ``Accept`` header.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
