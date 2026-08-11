"""Doom-style action replay: record orders and re-apply them with the same RNG seed."""

import json
import os
from datetime import datetime

from .engine import GameState


def replays_root():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "replays")


def create_match_folder(prefix="match"):
    root = replays_root()
    os.makedirs(root, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(root, f"{stamp}_{prefix}")
    os.makedirs(folder, exist_ok=True)
    return folder


def save_replay(folder, game_state):
    path = os.path.join(folder, "replay.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(game_state.get_replay_metadata(), f, indent=2)
    return path


def save_feedback(folder, entries):
    """Write compiled feedback entries (mid-game + end-game) to feedback.json."""
    path = os.path.join(folder, "feedback.json")
    payload = {
        "entries": entries,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def list_replays():
    root = replays_root()
    if not os.path.isdir(root):
        return []
    entries = []
    for name in sorted(os.listdir(root), reverse=True):
        folder = os.path.join(root, name)
        replay_path = os.path.join(folder, "replay.json")
        if os.path.isdir(folder) and os.path.isfile(replay_path):
            entries.append({"name": name, "folder": folder, "replay_path": replay_path})
    return entries


def load_replay(replay_path):
    with open(replay_path, "r", encoding="utf-8") as f:
        return json.load(f)


class ReplayPlayer:
    """Replays a recorded action stream through a fresh GameState."""

    def __init__(self, replay_data, full_map_view=True):
        self.replay_data = replay_data
        self.full_map_view = full_map_view
        self.actions = list(replay_data.get("actions", []))
        self.index = 0
        self.playing = False
        self.auto_timer = 0
        self.auto_interval = 45

        self.state = self._make_state()
        self._apply_view_mode()

    def _make_state(self):
        mode = self.replay_data.get("mode", "Fog")
        return GameState(
            mode=mode,
            map_name=self.replay_data.get("map_name", "moba"),
            ai_type=self.replay_data.get("ai_type", "Aggressive"),
            rng_seed=self.replay_data.get("rng_seed"),
            record_replay=False,
        )

    def _apply_view_mode(self):
        if self.full_map_view:
            self.state.mode = "God"
        else:
            self.state.mode = self.replay_data.get("mode", "Fog")
        self.state.update_visibility()

    def set_full_map_view(self, enabled):
        self.full_map_view = enabled
        self._apply_view_mode()

    def done(self):
        return self.index >= len(self.actions) or self.state.game_over

    def step(self):
        """Apply the next recorded action."""
        if self.index >= len(self.actions) or self.state.game_over:
            return False

        action = self.actions[self.index]
        side = action["side"]
        self.state.turn = side
        self.state.apply_replay_action(action)
        self.state.process_execute_orders(side)
        self.state.process_end_of_turn(side)
        self.state._check_win_condition()
        self.index += 1

        # After an AI action, advance turn count like live end_turn
        if side == 1 and not self.state.game_over:
            self.state.turn_count += 1
            self.state.turn = 0
            self.state.has_acted = [False, False]

        self._apply_view_mode()
        return True

    def step_back(self):
        """Rebuild state from seed up to the previous action index."""
        if self.index <= 0:
            return False
        target = self.index - 1
        self.state = self._make_state()
        self.index = 0
        while self.index < target:
            if not self.step():
                break
        self.playing = False
        self.auto_timer = 0
        self._apply_view_mode()
        return True

    def tick(self):
        if not self.playing or self.done():
            return
        self.auto_timer += 1
        if self.auto_timer >= self.auto_interval:
            self.auto_timer = 0
            self.step()
