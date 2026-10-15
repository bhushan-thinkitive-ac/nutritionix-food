from django.urls import include, path

urlpatterns = [
    path('', include('poc.urls')),
]
