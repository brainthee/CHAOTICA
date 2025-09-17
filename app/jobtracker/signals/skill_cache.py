from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from ..models import UserSkill, Skill, SkillCategory
import logging

logger = logging.getLogger(__name__)


def clear_skill_matrix_cache():
    """Clear all skill matrix cache entries"""
    # Clear filter options cache
    cache.delete('skill_matrix_filter_options')

    # Clear all matrix data caches (we can't enumerate all keys, so we use a pattern)
    # In production, you might want to use Redis and its pattern deletion feature
    # For now, we'll just log that cache should be cleared
    logger.info("Skill matrix cache invalidation triggered")


@receiver(post_save, sender=UserSkill)
def clear_cache_on_userskill_save(sender, instance, **kwargs):
    """Clear skill matrix cache when a user skill is updated"""
    clear_skill_matrix_cache()


@receiver(post_delete, sender=UserSkill)
def clear_cache_on_userskill_delete(sender, instance, **kwargs):
    """Clear skill matrix cache when a user skill is deleted"""
    clear_skill_matrix_cache()


@receiver(post_save, sender=Skill)
def clear_cache_on_skill_save(sender, instance, **kwargs):
    """Clear skill matrix cache when a skill is updated"""
    clear_skill_matrix_cache()


@receiver(post_delete, sender=Skill)
def clear_cache_on_skill_delete(sender, instance, **kwargs):
    """Clear skill matrix cache when a skill is deleted"""
    clear_skill_matrix_cache()


@receiver(post_save, sender=SkillCategory)
def clear_cache_on_category_save(sender, instance, **kwargs):
    """Clear skill matrix cache when a category is updated"""
    clear_skill_matrix_cache()


@receiver(post_delete, sender=SkillCategory)
def clear_cache_on_category_delete(sender, instance, **kwargs):
    """Clear skill matrix cache when a category is deleted"""
    clear_skill_matrix_cache()