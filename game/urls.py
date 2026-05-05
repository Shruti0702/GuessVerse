from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("create-room/", views.create_room, name="create_room"),
    path("join-room/", views.join_room, name="join_room"),
    path("lobby/<str:room_code>/", views.lobby, name="lobby"),
    path("game/<str:room_code>/", views.game_page, name="game_page"),
    path("join-random/", views.join_random_room, name="join_random_room"),
]