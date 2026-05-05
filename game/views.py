import random
import string
from django.shortcuts import render, redirect, get_object_or_404
from .models import Room, Player
from django.db.models import Count
from django.db import models
def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def home(request):
    return render(request, "home.html")


def create_room(request):
    if request.method == "POST":
        name = request.POST.get("name")
        avatar = request.POST.get("avatar", "🐶")

        round_time = int(request.POST.get("round_time", 60))
        total_rounds = int(request.POST.get("total_rounds", 5))
        word_options_count = int(request.POST.get("word_options_count", 3))

        max_players = int(request.POST.get("max_players", 4))
        allow_random = request.POST.get("allow_random") == "on"

        if max_players < 4 or max_players % 2 != 0:
            return render(request, "home.html", {
                "error": "Players must be even and minimum 4."
            })

        room = Room.objects.create(
            room_code=generate_room_code(),
            round_time=round_time,
            total_rounds=total_rounds,
            word_options_count=word_options_count,
            max_players=max_players,
            allow_random=allow_random,
            phase="waiting"
        )

        player = Player.objects.create(
            room=room,
            name=name,
            avatar=avatar,
            is_host=True
        )

        request.session["player_id"] = player.id
        request.session["room_code"] = room.room_code

        return redirect("lobby", room_code=room.room_code)

    return redirect("home")

def join_room(request):
    if request.method == "POST":
        name = request.POST.get("name")
        avatar = request.POST.get("avatar", "🐶")
        room_code = request.POST.get("room_code").upper()

        room = get_object_or_404(Room, room_code=room_code)

        if room.players.count() >= room.max_players:
            return render(request, "home.html", {
                "error": "This room is already full."
            })

        player = Player.objects.create(
            room=room,
            name=name,
            avatar=avatar,
            is_host=False
        )

        request.session["player_id"] = player.id
        request.session["room_code"] = room.room_code

        return redirect("lobby", room_code=room.room_code)

    return redirect("home")
def lobby(request, room_code):
    room = get_object_or_404(Room, room_code=room_code)
    player_id = request.session.get("player_id")
    player = get_object_or_404(Player, id=player_id)

    return render(request, "lobby.html", {
        "room": room,
        "player": player,
    })


def game_page(request, room_code):
    room = get_object_or_404(Room, room_code=room_code)
    player_id = request.session.get("player_id")
    player = get_object_or_404(Player, id=player_id)

    return render(request, "game.html", {
        "room": room,
        "player": player,
    })
def join_random_room(request):
    if request.method == "POST":
        name = request.POST.get("name")
        avatar = request.POST.get("avatar", "🐶")

        room = Room.objects.annotate(
            current_players=Count("players")
        ).filter(
            allow_random=True,
            status="waiting",
            phase="waiting",
            current_players__lt=models.F("max_players")
        ).first()

        if not room:
            return render(request, "home.html", {
                "error": "No random room available right now."
            })

        player = Player.objects.create(
            room=room,
            name=name,
            avatar=avatar,
            is_host=False
        )

        request.session["player_id"] = player.id
        request.session["room_code"] = room.room_code

        return redirect("lobby", room_code=room.room_code)

    return redirect("home")