from django.urls import path

from . import views

app_name = "chats"
urlpatterns = [
    path("", views.index, name="index"),
    path("chat/<int:pk>/", views.detail, name="detail"),
    path("chat/<int:pk>/sposta/", views.move_one, name="move_one"),
    path("sposta/", views.move, name="move"),
    path("file/<int:pk>/", views.attachment, name="attachment"),
    path("categorie/", views.categories, name="categories"),
]
