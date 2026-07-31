"""Pre-import RM clients into CHAOTICA so mirrored projects can be linked to them."""

import logging
from dataclasses import dataclass

from jobtracker.models import Client

from .client import RMClient

logger = logging.getLogger("rm_sync")


@dataclass
class ClientImportResult:
    created: int = 0
    linked: int = 0  # existing client stamped with external_id
    skipped_no_name: int = 0
    errors: int = 0


def sync_rm_clients(client=None, dry_run=False):
    """Create/link CHAOTICA Clients from RM's ``/clients`` collection.

    RM clients expose ``id`` and ``value`` (the name). We key on ``external_id`` (the RM id)
    and fall back to matching an existing Client by name.
    """
    client = client or RMClient()
    result = ClientImportResult()

    for rm_client in client.paginate("/api/v1/clients", {"per_page": 500}):
        try:
            name = (rm_client.get("value") or "").strip()
            if not name:
                result.skipped_no_name += 1
                continue
            external_id = str(rm_client["id"])
            existing = Client.objects.filter(external_id=external_id).first()
            if existing:
                continue
            by_name = Client.objects.filter(name__iexact=name).first()
            if by_name:
                if not by_name.external_id and not dry_run:
                    by_name.external_id = external_id
                    by_name.save(update_fields=["external_id"])
                result.linked += 1
                continue
            result.created += 1
            if not dry_run:
                Client.objects.create(name=name, external_id=external_id)
        except Exception:
            result.errors += 1
            logger.exception(
                "Client import error for RM client %s", rm_client.get("id")
            )

    return result


def get_or_create_client(name, external_id=None):
    """Resolve a CHAOTICA Client by name (used when mirroring projects)."""
    name = (name or "").strip()
    if not name:
        return None
    existing = Client.objects.filter(name__iexact=name).first()
    if existing:
        if external_id and not existing.external_id:
            existing.external_id = str(external_id)
            existing.save(update_fields=["external_id"])
        return existing
    return Client.objects.create(
        name=name, external_id=str(external_id) if external_id else ""
    )
