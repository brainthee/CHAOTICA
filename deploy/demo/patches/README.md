# Demo-data tuning override

`generate_demo_data.py` here is bind-mounted over the copy inside
`brainthee/chaotica:latest` by `../docker-compose.yml`.

**This is not a bug shim** — it is a copy of the image's own management command
with the demo-data distribution tuned so the demo looks realistic:

- Jobs are spread across the whole delivery lifecycle (long-past → spanning
  today → future pipeline) instead of all starting in the past, so phases land
  in every stage rather than everything on COMPLETED.
- Finished phases are mostly `DELIVERED` (report handed to the client), with a
  minority left at `COMPLETED`.
- Future/pipeline phases cover DRAFT, PENDING_SCHED, SCHEDULED_TENTATIVE/
  CONFIRMED, CLIENT_NOT_READY, READY_TO_BEGIN, PRE_CHECKS.
- Early-stage jobs get varied scoping statuses, and a slice become `LOST`.

It is based on the image's command (not repo `main`) so it stays import- and
schema-compatible with whatever the image ships.

## Retiring it

Fold these tweaks into the canonical
`app/chaotica_utils/management/commands/generate_demo_data.py`. Once a rebuilt
`brainthee/chaotica:latest` includes them:

1. Delete the `./patches/generate_demo_data.py:...` volume line in
   `../docker-compose.yml`.
2. Delete this `patches/` directory.
