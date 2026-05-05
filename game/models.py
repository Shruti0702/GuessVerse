from django.db import models

class Room(models.Model):
    room_code = models.CharField(max_length=10, unique=True)
    status = models.CharField(max_length=20, default="waiting")

    round_time = models.IntegerField(default=60)
    total_rounds = models.IntegerField(default=5)
    current_round = models.IntegerField(default=1)
    word_options_count = models.IntegerField(default=3)
    team_a_score = models.IntegerField(default=0)
    team_b_score = models.IntegerField(default=0)
    round_started_at = models.IntegerField(null=True, blank=True)
    current_selecting_team = models.CharField(max_length=1, default="A")
    current_guessing_team = models.CharField(max_length=1, default="B")

    selected_word = models.CharField(max_length=200, blank=True, null=True)
    selected_category = models.CharField(max_length=50, blank=True, null=True)
    hint_giver_id = models.IntegerField(blank=True, null=True)

    phase = models.CharField(max_length=30, default="waiting")

    max_players = models.IntegerField(default=4)
    allow_random = models.BooleanField(default=False)

class Player(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="players")
    name = models.CharField(max_length=100)
    team = models.CharField(max_length=1, null=True)
    avatar = models.CharField(max_length=10, default="🐶")
    is_host = models.BooleanField(default=False)


class Word(models.Model):
    CATEGORY_CHOICES = (
        ("movie", "Movie"),
        ("place", "Place"),
        ("person", "Person"),
        ("food", "Food"),
        ("fruit", "Fruit"),
        ("vegetable", "Vegetable"),
        ("animal", "Animal"),
    )

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)