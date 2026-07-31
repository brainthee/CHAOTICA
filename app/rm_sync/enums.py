class RMSyncDirection:
    """Per-user sync direction for a RMSyncRecord.

    Deliberately excludes a two-way / BOTH option: syncing both directions for the same
    user would create feedback loops (CHAOTICA writes to RM, then reads its own write back
    in). ``sync_authoritative`` is orthogonal to this and controls whether the *destination*
    side is pruned to match the source.
    """

    OFF = 0
    PUSH = 1  # CHAOTICA -> RM (CHAOTICA is the source of truth)
    PULL = 2  # RM -> CHAOTICA (RM is the source of truth)

    CHOICES = (
        (OFF, "Off"),
        (PUSH, "Push (CHAOTICA → RM)"),
        (PULL, "Pull (RM → CHAOTICA)"),
    )
