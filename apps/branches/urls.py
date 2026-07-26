from django.urls import path

from .views import branch_list

app_name = 'branches'

urlpatterns = [
    path('', branch_list, name='branch_list'),
]
