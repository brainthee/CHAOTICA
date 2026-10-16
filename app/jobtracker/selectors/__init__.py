"""Read-side query logic shared by template views and /api/v1/.

A selector takes the viewer (and usually the request's PolicyContext) and
returns querysets or plain data; views only render.
"""
