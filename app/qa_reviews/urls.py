from django.urls import path
from . import views

app_name = 'qa_reviews'

urlpatterns = [
    path('', views.qa_wheel_selection, name='wheel_selection'),
    path('get-eligible-users/', views.get_eligible_users, name='get_eligible_users'),
    path('spin-wheel/', views.spin_wheel, name='spin_wheel'),
    path('begin-review/<int:phase_id>/', views.begin_review, name='begin_review'),
    path('review/<uuid:review_id>/', views.review_detail, name='review_detail'),
    path('review/<uuid:review_id>/abort/', views.abort_review, name='abort_review'),
    path('history/', views.review_history, name='review_history'),
]