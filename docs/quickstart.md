# Quickstart

You can quickly and easily run CHAOTICA by using Docker:

```bash
docker run -e DEBUG=1 brainthee/chaotica
```

When finished, you should be able view it at `http://localhost:8000`. When you first visit the site, it will ask you to register a new account. This first account will automatically be given full administrative permissions.

!!! Warning
    Beware - this will run with SQLite as the database and without persistent volumes. You will lose data if that container is destroyed!

To load some dummp data


Installation

To use CHAOTICA in a dev environment, you can simply pull with docker!

```console
docker run brainthee/chaotica
```