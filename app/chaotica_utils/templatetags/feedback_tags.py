from django import template

register = template.Library()


@register.simple_tag
def get_combined_average_qa_rating_12mo(user):
    return user.get_combined_average_qa_rating_12mo()
