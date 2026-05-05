import json
import random
import asyncio
import time

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from .models import Room, Word


ACTIVE_TIMERS = {}


def get_word_hint(word_name):
    words = word_name.split()
    return {
        "hidden_name": " ".join("_" * len(word) for word in words),
        "word_count": len(words),
        "word_lengths": [len(word) for word in words],
    }


class GameConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.room_code = self.scope["url_route"]["kwargs"]["room_code"]
        self.room_group_name = f"game_{self.room_code}"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        await self.broadcast_state("send_state")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get("action")

        if action == "start_game":
            result = await self.start_game()

            if not result["success"]:
                await self.send(text_data=json.dumps({
                    "type": "start_error",
                    "message": result["message"]
                }))
                return

            await self.broadcast_state("game_started")

        elif action == "get_words":
            words = await self.get_random_words()
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "word_options", "words": words}
            )

        elif action == "select_word":
            word_name = data.get("word")
            round_started_at = int(time.time())

            await self.save_selected_word(word_name, round_started_at)

            hint_giver_id = await self.choose_random_hint_giver()
            hint = get_word_hint(word_name)

            await self.broadcast_state(
                "word_selected",
                extra={
                    "hint": hint,
                    "hint_giver_id": hint_giver_id,
                }
            )

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "word_revealed",
                    "hint_giver_id": hint_giver_id,
                    "word": word_name,
                }
            )

            room = await self.get_room_data()

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "timer_start",
                    "start_time": round_started_at,
                    "duration": room["round_time"],
                }
            )

            await self.start_timer(room["round_time"])

        elif action == "send_hint":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "hint_message",
                    "player_name": data.get("player_name"),
                    "message": data.get("message"),
                }
            )

        elif action == "submit_guess":
            guess = data.get("guess", "").strip()
            player_name = data.get("player_name")

            if not guess:
                return

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "guess_message",
                    "player_name": player_name,
                    "guess": guess,
                }
            )
            async def guess_message(self, event):
                await self.send(text_data=json.dumps(event))

            is_correct = await self.check_guess(guess)

            if is_correct:
                await self.cancel_timer()
                await self.add_point_to_guessing_team()
                await self.go_next_round()

            await self.broadcast_state(
                "guess_result",
                extra={
                    "player_name": player_name,
                    "guess": guess,
                    "correct": is_correct,
                }
            )

        elif action == "draw_start":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "draw_start_event",
                    "x": data.get("x"),
                    "y": data.get("y"),
                    "color": data.get("color", "#000000"),
                    "size": data.get("size", 4),
                }
            )

        elif action == "draw_move":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "draw_move_event",
                    "x": data.get("x"),
                    "y": data.get("y"),
                    "color": data.get("color", "#000000"),
                    "size": data.get("size", 4),
                }
            )

        elif action == "clear_canvas":
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "clear_canvas_event"}
            )

        elif action == "fill_canvas":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "fill_canvas_event",
                    "color": data.get("color", "#ffffff"),
                }
            )

    async def broadcast_state(self, event_type, extra=None):
        players = await self.get_players()
        room = await self.get_room_data()

        payload = {
            "type": event_type,
            "players": players,
            "room": room,
        }

        if extra:
            payload.update(extra)

        await self.channel_layer.group_send(self.room_group_name, payload)

    async def start_timer(self, seconds):
        await self.cancel_timer()
        task = asyncio.create_task(self.round_timer(seconds))
        ACTIVE_TIMERS[self.room_code] = task

    async def cancel_timer(self):
        task = ACTIVE_TIMERS.get(self.room_code)

        if task and not task.done():
            task.cancel()

        ACTIVE_TIMERS.pop(self.room_code, None)

    async def round_timer(self, seconds):
        try:
            await asyncio.sleep(seconds)

            await self.add_point_to_selecting_team()
            await self.go_next_round()

            await self.broadcast_state("time_up_result")

        except asyncio.CancelledError:
            pass

    async def send_state(self, event):
        await self.send(text_data=json.dumps(event))

    async def game_started(self, event):
        await self.send(text_data=json.dumps(event))

    async def word_options(self, event):
        await self.send(text_data=json.dumps(event))

    async def word_selected(self, event):
        await self.send(text_data=json.dumps(event))

    async def word_revealed(self, event):
        my_player_id = self.scope["session"].get("player_id")

        if str(my_player_id) == str(event["hint_giver_id"]):
            await self.send(text_data=json.dumps({
                "type": "word_revealed",
                "word": event["word"],
            }))

    async def timer_start(self, event):
        await self.send(text_data=json.dumps(event))

    async def hint_message(self, event):
        await self.send(text_data=json.dumps(event))

    async def guess_message(self, event):
        await self.send(text_data=json.dumps(event))

    async def guess_result(self, event):
        await self.send(text_data=json.dumps(event))

    async def time_up_result(self, event):
        await self.send(text_data=json.dumps(event))

    async def draw_start_event(self, event):
        await self.send(text_data=json.dumps(event))

    async def draw_move_event(self, event):
        await self.send(text_data=json.dumps(event))

    async def clear_canvas_event(self, event):
        await self.send(text_data=json.dumps(event))

    async def fill_canvas_event(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def get_players(self):
        room = Room.objects.get(room_code=self.room_code)

        return [
            {
                "id": player.id,
                "name": player.name,
                "avatar": player.avatar,
                "team": player.team,
                "is_host": player.is_host,
            }
            for player in room.players.all()
        ]

    @database_sync_to_async
    def get_room_data(self):
        room = Room.objects.get(room_code=self.room_code)

        return {
            "room_code": room.room_code,
            "status": room.status,
            "phase": room.phase,
            "round_time": room.round_time,
            "total_rounds": room.total_rounds,
            "current_round": room.current_round,
            "team_a_score": room.team_a_score,
            "team_b_score": room.team_b_score,
            "current_selecting_team": room.current_selecting_team,
            "current_guessing_team": room.current_guessing_team,
            "hint_giver_id": room.hint_giver_id,
            "word_options_count": room.word_options_count,
            "selected_word": room.selected_word,
            "round_started_at": room.round_started_at,
            "max_players": room.max_players,
            "allow_random": room.allow_random,
            "current_players": room.players.count(),
        }

    @database_sync_to_async
    def start_game(self):
        room = Room.objects.get(room_code=self.room_code)
        players = list(room.players.all())

        if len(players) < room.max_players:
            return {
                "success": False,
                "message": f"Need {room.max_players} players to start. Currently {len(players)} joined."
            }

        if len(players) % 2 != 0:
            return {
                "success": False,
                "message": "Players must be even to form teams."
            }

        random.shuffle(players)
        half = len(players) // 2

        for index, player in enumerate(players):
            player.team = "A" if index < half else "B"
            player.save()

        room.status = "started"
        room.phase = "word_selection"
        room.current_round = 1
        room.current_selecting_team = "A"
        room.current_guessing_team = "B"
        room.team_a_score = 0
        room.team_b_score = 0
        room.selected_word = None
        room.selected_category = None
        room.hint_giver_id = None
        room.round_started_at = None
        room.save()

        return {
            "success": True,
            "message": "Game started."
        }

    @database_sync_to_async
    def get_random_words(self):
        room = Room.objects.get(room_code=self.room_code)
        words = list(Word.objects.all())

        count = room.word_options_count

        if len(words) <= count:
            selected = words
        else:
            selected = random.sample(words, count)

        return [{"name": word.name} for word in selected]

    @database_sync_to_async
    def save_selected_word(self, word_name, round_started_at):
        room = Room.objects.get(room_code=self.room_code)
        selected = Word.objects.filter(name=word_name).first()

        room.selected_word = word_name
        room.selected_category = selected.category if selected else ""
        room.phase = "guessing"
        room.hint_giver_id = None
        room.round_started_at = round_started_at
        room.save()

    @database_sync_to_async
    def choose_random_hint_giver(self):
        room = Room.objects.get(room_code=self.room_code)
        guessing_players = list(room.players.filter(team=room.current_guessing_team))

        if not guessing_players:
            return None

        hint_giver = random.choice(guessing_players)
        room.hint_giver_id = hint_giver.id
        room.save()

        return hint_giver.id

    @database_sync_to_async
    def check_guess(self, guess):
        room = Room.objects.get(room_code=self.room_code)

        if not room.selected_word:
            return False

        return guess.strip().lower() == room.selected_word.strip().lower()

    @database_sync_to_async
    def add_point_to_guessing_team(self):
        room = Room.objects.get(room_code=self.room_code)

        if room.current_guessing_team == "A":
            room.team_a_score += 1
        else:
            room.team_b_score += 1

        room.save()

    @database_sync_to_async
    def add_point_to_selecting_team(self):
        room = Room.objects.get(room_code=self.room_code)

        if room.current_selecting_team == "A":
            room.team_a_score += 1
        else:
            room.team_b_score += 1

        room.save()

    @database_sync_to_async
    def go_next_round(self):
        room = Room.objects.get(room_code=self.room_code)

        if room.current_round >= room.total_rounds:
            room.status = "finished"
            room.phase = "game_over"
            room.selected_word = None
            room.selected_category = None
            room.hint_giver_id = None
            room.round_started_at = None
            room.save()
            return

        room.current_round += 1

        if room.current_selecting_team == "A":
            room.current_selecting_team = "B"
            room.current_guessing_team = "A"
        else:
            room.current_selecting_team = "A"
            room.current_guessing_team = "B"

        room.phase = "word_selection"
        room.selected_word = None
        room.selected_category = None
        room.hint_giver_id = None
        room.round_started_at = None
        room.save()