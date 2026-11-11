"""Generate skill-rating suggestions when a qualification is awarded.

When a :class:`QualificationRecord` reaches AWARDED (and is verified, where the
qualification requires verification), we raise one
:class:`SkillRatingSuggestion` per skill the qualification evidences. Suggestions
are non-destructive: they never change a user's :class:`UserSkill` directly — the
user accepts or dismisses each one. We only ever propose a rating *higher* than
what the user already holds, and we never raise the same suggestion twice for the
same record + skill (so dismissing one is final for that award).
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from ..enums import QualificationStatus
from ..models.qualification import QualificationRecord
from ..models.skill import UserSkill, SkillRatingSuggestion

logger = logging.getLogger(__name__)


def _award_is_effective(record):
    """True when an award should drive skill suggestions.

    Awarded, and — if the qualification needs manager verification — verified.
    """
    if record.status != QualificationStatus.AWARDED:
        return False
    if record.qualification.verification_required and not record.verified_on:
        return False
    return True


@receiver(post_save, sender=QualificationRecord)
def suggest_skills_on_award(sender, instance, created, **kwargs):
    if not _award_is_effective(instance):
        return

    links = instance.qualification.skill_links.select_related("skill").all()
    if not links:
        return

    for link in links:
        # One suggestion per (record, skill), ever — honour an earlier dismissal.
        already = SkillRatingSuggestion.objects.filter(
            user=instance.user,
            skill=link.skill,
            source_qualification_record=instance,
        ).exists()
        if already:
            continue

        # Only propose a lift above the user's current self-assessment.
        current = (
            UserSkill.objects.filter(user=instance.user, skill=link.skill)
            .values_list("rating", flat=True)
            .first()
        )
        if current is not None and current >= link.suggested_rating:
            continue

        SkillRatingSuggestion.objects.create(
            user=instance.user,
            skill=link.skill,
            suggested_rating=link.suggested_rating,
            source=SkillRatingSuggestion.SOURCE_QUALIFICATION,
            source_qualification_record=instance,
            message="Suggested from awarded qualification: %s"
            % (instance.qualification,),
        )
    logger.info(
        "Generated skill suggestions for %s from qualification %s",
        instance.user,
        instance.qualification,
    )
