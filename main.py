import os
import sys
import warnings
import math

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
warnings.filterwarnings("ignore", message="Your system is avx2 capable")

import pygame
from game.engine import GameState, UNIT_TYPE_LETTER
from game.graph import get_available_maps
from game.replay import (
    ReplayPlayer,
    create_match_folder,
    list_replays,
    load_replay,
    save_feedback,
    save_replay,
)
from game.ui_components import Button, TextInput
from game.audio_recorder import AudioRecorder

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
SCREEN_WIDTH = WINDOW_WIDTH
SCREEN_HEIGHT = WINDOW_HEIGHT

GRID_SIZE = 3
CELL_SIZE = 70
BOTTOM_PANEL_HEIGHT = 150
REPLAY_PANEL_WIDTH = 220
MIDGAME_PROMPT_INTERVAL = 5
MAP_WIDTH = SCREEN_WIDTH
MAP_HEIGHT = SCREEN_HEIGHT - BOTTOM_PANEL_HEIGHT

GRID_OFFSET_X = 60
GRID_OFFSET_Y = 40
NODE_RADIUS = 28

from enum import Enum


class UIState(Enum):
    MAIN_MENU = 1
    SETTINGS = 2
    PLAYING = 3
    FEEDBACK = 4
    REPLAY_MENU = 5
    REPLAYING = 6


WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
DARK_GRAY = (100, 100, 100)
RED = (255, 100, 100)
BLUE = (100, 100, 255)
GREEN = (100, 255, 100)
YELLOW = (255, 255, 100)
FOG = (50, 50, 50)
SILHOUETTE = (80, 80, 80)


class ContextMenu:
    def __init__(self, font):
        self.visible = False
        self.pos = (0, 0)
        self.options = []
        self.font = font
        self.target_node = None
        self.padding = 10
        self.option_height = 30
        self.text_input = None

    def show(self, pos, options, target_node):
        self.visible = True
        self.pos = pos
        self.options = options
        self.target_node = target_node
        self.text_input = None
        for opt in options:
            if opt.get("is_splitter"):
                self.text_input = TextInput(0, 0, 60, 24, self.font)
                self.text_input.set_text(str(opt.get("amount", 1)))
                break

    def hide(self):
        self.visible = False
        self.options = []
        self.target_node = None
        self.text_input = None

    def get_rect(self):
        if not self.options:
            return pygame.Rect(0, 0, 0, 0)

        def get_label_width(opt):
            label = opt["label"]
            if opt.get("is_splitter"):
                prefix_w = self.font.size(label)[0]
                suffix_w = self.font.size(" (Scroll to adjust)")[0]
                return prefix_w + 60 + suffix_w + 20
            return self.font.size(label)[0]

        width = max(get_label_width(opt) for opt in self.options) + self.padding * 2
        height = len(self.options) * self.option_height
        return pygame.Rect(self.pos[0], self.pos[1], width, height)

    def draw(self, screen):
        if not self.visible or not self.options:
            return

        rect = self.get_rect()
        if self.pos[0] + rect.width > SCREEN_WIDTH:
            rect.x = SCREEN_WIDTH - rect.width
        if self.pos[1] + rect.height > SCREEN_HEIGHT:
            rect.y = SCREEN_HEIGHT - rect.height

        pygame.draw.rect(screen, WHITE, rect)
        pygame.draw.rect(screen, BLACK, rect, 2)

        curr_y = rect.y
        for opt in self.options:
            opt_rect = pygame.Rect(rect.x, curr_y, rect.width, self.option_height)
            if not (self.text_input and self.text_input.rect.collidepoint(pygame.mouse.get_pos())):
                if opt_rect.collidepoint(pygame.mouse.get_pos()):
                    pygame.draw.rect(screen, GRAY, opt_rect)

            if opt.get("is_splitter"):
                prefix_surf = self.font.render(opt["label"], True, BLACK)
                screen.blit(prefix_surf, (rect.x + self.padding, curr_y + 5))
                prefix_w = prefix_surf.get_width()
                if self.text_input:
                    self.text_input.rect.x = rect.x + self.padding + prefix_w + 5
                    self.text_input.rect.y = curr_y + 3
                    self.text_input.draw(screen)
                    input_w = self.text_input.rect.width
                else:
                    input_w = 0
                suffix_surf = self.font.render(" (Scroll to adjust)", True, BLACK)
                screen.blit(
                    suffix_surf,
                    (rect.x + self.padding + prefix_w + input_w + 10, curr_y + 5),
                )
            else:
                text_surf = self.font.render(opt["label"], True, BLACK)
                screen.blit(text_surf, (rect.x + self.padding, curr_y + 5))
            curr_y += self.option_height

    def handle_click(self, pos, hide_automatically=True):
        if not self.visible:
            return None

        if self.text_input and self.text_input.rect.collidepoint(pos):
            self.text_input.active = True
            return None

        rect = self.get_rect()
        if self.pos[0] + rect.width > SCREEN_WIDTH:
            rect.x = SCREEN_WIDTH - rect.width
        if self.pos[1] + rect.height > SCREEN_HEIGHT:
            rect.y = SCREEN_HEIGHT - rect.height

        if not rect.collidepoint(pos):
            self.hide()
            return None

        curr_y = rect.y
        for opt in self.options:
            opt_rect = pygame.Rect(rect.x, curr_y, rect.width, self.option_height)
            if opt_rect.collidepoint(pos):
                if hide_automatically:
                    self.hide()
                return opt
            curr_y += self.option_height

        self.hide()
        return None


class Game:
    def __init__(self):
        pygame.init()

        global SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT, GRID_OFFSET_X, GRID_OFFSET_Y
        SCREEN_WIDTH = WINDOW_WIDTH
        SCREEN_HEIGHT = WINDOW_HEIGHT
        MAP_WIDTH = SCREEN_WIDTH
        MAP_HEIGHT = SCREEN_HEIGHT - BOTTOM_PANEL_HEIGHT
        GRID_OFFSET_X = 80
        GRID_OFFSET_Y = 60

        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Don't Shoot the Messenger - Strategy Game")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 18)
        self.small_font = pygame.font.SysFont("Arial", 14)
        self.title_font = pygame.font.SysFont("Arial", 48, bold=True)
        self.ui_font = pygame.font.SysFont("Arial", 24, bold=True)

        self.ui_state = UIState.MAIN_MENU
        self.selected_mode = "Fog"
        self.state = None
        self.mode_options = ["God", "Fog", "Realistic"]
        self.context_menu = ContextMenu(self.font)

        self.audio_recorder = AudioRecorder()
        self.voice_recording_enabled = False

        self.ai_types = ["AI 0", "AI 1", "AI 2", "AI 3", "AI 4", "AI 5", "AI 6"]
        self.selected_ai_index = 0

        self.ai_thinking = False
        self.ai_think_timer = 0

        self.camera_x = 0
        self.camera_y = 0
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.camera_start_x = 0
        self.camera_start_y = 0

        self.floating_messages = []
        self.notifications = []

        self.match_folder = None
        self.feedback_rating = 3
        self.feedback_input = None
        self.feedback_entries = []
        self.feedback_is_final = False
        self.pending_game_over = False
        self.pending_midgame_prompt = False

        self.replay_list = []
        self.replay_scroll = 0
        self.replay_player = None
        self.replay_buttons = []

        self.maps_dir = os.path.join(os.path.dirname(__file__), "maps")
        self.available_maps = get_available_maps(self.maps_dir)
        self.selected_map_index = 0
        if "moba" in self.available_maps:
            self.selected_map_index = self.available_maps.index("moba")

        button_w, button_h = 220, 50
        self.menu_buttons = [
            Button(SCREEN_WIDTH // 2 - 110, 280, button_w, button_h, "Start Game", self.ui_font),
            Button(SCREEN_WIDTH // 2 - 110, 350, button_w, button_h, "Replays", self.ui_font),
            Button(SCREEN_WIDTH // 2 - 110, 420, button_w, button_h, "Settings", self.ui_font),
            Button(SCREEN_WIDTH // 2 - 110, 490, button_w, button_h, "Quit", self.ui_font),
        ]
        self._rebuild_settings_buttons()

    def _rebuild_settings_buttons(self):
        button_w, button_h = 220, 50
        ai_type = self.ai_types[self.selected_ai_index]
        if ai_type == "AI 0":
            map_name = "moba (Locked)"
        else:
            map_name = self.available_maps[self.selected_map_index] if self.available_maps else "none"
        rec_status = "On" if self.voice_recording_enabled else "Off"
        self.settings_buttons = [
            Button(SCREEN_WIDTH // 2 - 110, 200, button_w, button_h, f"Mode: {self.selected_mode}", self.font),
            Button(SCREEN_WIDTH // 2 - 110, 260, button_w, button_h, f"AI: {ai_type}", self.font),
            Button(SCREEN_WIDTH // 2 - 110, 320, button_w, button_h, f"Map: {map_name}", self.font),
            Button(SCREEN_WIDTH // 2 - 110, 380, button_w, button_h, f"Voice Rec: {rec_status}", self.font),
            Button(SCREEN_WIDTH // 2 - 110, 460, button_w, button_h, "Back", self.ui_font),
        ]

    def start_new_game(self):
        map_name = self.available_maps[self.selected_map_index] if self.available_maps else "default_3x3"
        ai_label = self.ai_types[self.selected_ai_index]
        if ai_label in ["AI 1", "AI 2", "AI 3"]:
            actual_ai_type = "Conservative"
        elif ai_label == "AI 0":
            actual_ai_type = "Aggressive"
            map_name = "moba"
        else:
            actual_ai_type = "Aggressive"

        self.state = GameState(
            mode=self.selected_mode,
            map_name=map_name,
            ai_type=actual_ai_type,
            record_replay=True,
        )
        self.ui_state = UIState.PLAYING
        self.camera_x = 0
        self.camera_y = 0
        self.is_dragging = False
        self.ai_thinking = False
        self.ai_think_timer = 0
        self.pending_game_over = False
        self.pending_midgame_prompt = False
        self.feedback_entries = []
        self.feedback_is_final = False
        self.match_folder = create_match_folder()

        self.audio_recorder.enabled = self.voice_recording_enabled
        self.audio_recorder.init_session()
        self.audio_recorder.start_recording()
        self.audio_recorder.mark_turn(self.state.turn_count)

    def open_replay_menu(self):
        self.replay_list = list_replays()
        self.replay_scroll = 0
        self.ui_state = UIState.REPLAY_MENU

    def start_replay(self, entry, full_map=True):
        data = load_replay(entry["replay_path"])
        self.replay_player = ReplayPlayer(data, full_map_view=full_map)
        self.state = self.replay_player.state
        self.ui_state = UIState.REPLAYING
        self.camera_x = 0
        self.camera_y = 0
        self._rebuild_replay_controls()

    def _rebuild_replay_controls(self):
        view_label = "Full Map" if self.replay_player.full_map_view else "Player POV"
        play_label = "Pause" if self.replay_player.playing else "Play"
        px = SCREEN_WIDTH - REPLAY_PANEL_WIDTH + 20
        bw = REPLAY_PANEL_WIDTH - 40
        self.replay_buttons = [
            Button(px, 80, bw, 40, play_label, self.font),
            Button(px, 140, bw, 40, "Step Forward", self.font),
            Button(px, 200, bw, 40, "Step Back", self.font),
            Button(px, 260, bw, 40, view_label, self.font),
            Button(px, 320, bw, 40, "Exit", self.font),
        ]

    def begin_feedback(self, final=False):
        self.feedback_is_final = final
        self.ui_state = UIState.FEEDBACK
        self.feedback_rating = 3
        self.feedback_input = TextInput(
            SCREEN_WIDTH // 2 - 300,
            340,
            600,
            40,
            self.font,
            placeholder="Describe what you think the AI is doing...",
            numeric_only=False,
            max_length=400,
        )
        self.feedback_input.active = True

    def submit_feedback(self):
        description = self.feedback_input.get_text().strip() if self.feedback_input else ""
        if not description:
            self.notifications.append({"text": "Please write a description", "life": 120})
            return

        entry = {
            "turn": self.state.turn_count if self.state else None,
            "phase": "endgame" if self.feedback_is_final else "midgame",
            "difficulty": self.feedback_rating,
            "description": description,
        }
        self.feedback_entries.append(entry)

        if self.feedback_is_final:
            if self.match_folder and self.state:
                save_replay(self.match_folder, self.state)
                save_feedback(self.match_folder, self.feedback_entries)
            self.audio_recorder.stop_recording()
            self.state = None
            self.match_folder = None
            self.feedback_entries = []
            self.ui_state = UIState.MAIN_MENU
        else:
            self.ui_state = UIState.PLAYING
            self.feedback_input = None

    def get_node_pos(self, node):
        x = GRID_OFFSET_X + node.x * (CELL_SIZE + 20) + CELL_SIZE // 2 + self.camera_x
        y = GRID_OFFSET_Y + node.y * (CELL_SIZE + 20) + CELL_SIZE // 2 + self.camera_y
        return int(x), int(y)

    def get_node_at_mouse(self, pos):
        mx, my = pos
        for node in self.state.nodes:
            nx, ny = self.get_node_pos(node)
            if ((mx - nx) ** 2 + (my - ny) ** 2) ** 0.5 <= NODE_RADIUS:
                return node
        return None

    def _draw_units_on_node(self, node, intel, force_full=False):
        units = self.state.get_units_at(node)
        if not units:
            return

        nx, ny = self.get_node_pos(node)
        show_full = force_full or intel == "full"

        if intel == "silhouette" and not force_full:
            # Anonymous enemy presence only
            enemies = [u for u in units if u.owner == 1]
            allies = [u for u in units if u.owner == 0]
            if allies:
                # Own units still fully visible on silhouette tiles? Plan: own presence full.
                # Silhouette intel means enemy content hidden; own units always shown fully.
                self._draw_unit_markers([u for u in units if u.owner == 0], nx, ny, full=True)
            if enemies:
                pygame.draw.circle(self.screen, (160, 60, 60), (nx + 12, ny + 8), NODE_RADIUS - 14)
                pygame.draw.circle(self.screen, BLACK, (nx + 12, ny + 8), NODE_RADIUS - 14, 1)
            return

        self._draw_unit_markers(units, nx, ny, full=show_full)

    def _draw_unit_markers(self, units, nx, ny, full=True):
        # Group by (owner, type)
        groups = {}
        for u in units:
            key = (u.owner, u.unit_type)
            groups[key] = groups.get(key, 0) + u.count

        items = list(groups.items())
        n = len(items)
        for i, ((owner, unit_type), count) in enumerate(items):
            angle = (2 * math.pi * i / max(n, 1)) - math.pi / 2
            radius = 0 if n == 1 else 16
            ox = int(math.cos(angle) * radius)
            oy = int(math.sin(angle) * radius)
            color = BLUE if owner == 0 else RED
            cx, cy = nx + ox, ny + oy
            pygame.draw.circle(self.screen, color, (cx, cy), NODE_RADIUS - 14)
            pygame.draw.circle(self.screen, BLACK, (cx, cy), NODE_RADIUS - 14, 1)
            if full:
                letter = UNIT_TYPE_LETTER.get(unit_type, "?")
                label = f"{letter}{count}"
                text = self.small_font.render(label, True, WHITE)
                self.screen.blit(text, (cx - text.get_width() // 2, cy - text.get_height() // 2))

    def draw_gameplay(self, is_replay=False):
        self.screen.fill(WHITE)

        play_width = SCREEN_WIDTH - (REPLAY_PANEL_WIDTH if is_replay else 0)

        force_full = False
        if is_replay and self.replay_player and self.replay_player.full_map_view:
            force_full = True
            player_visibility = set(self.state.nodes)
        elif self.state.game_over and not is_replay:
            force_full = True
            player_visibility = set(self.state.nodes)
        else:
            player_visibility = self.state.visible_nodes[0]

        drawn_edges = set()
        for node in self.state.nodes:
            nx, ny = self.get_node_pos(node)
            for neighbor in node.neighbors:
                edge_key = (min(node.id, neighbor.id), max(node.id, neighbor.id))
                if edge_key in drawn_edges:
                    continue
                nnx, nny = self.get_node_pos(neighbor)
                pygame.draw.line(self.screen, BLACK, (nx, ny), (nnx, nny), 1)
                drawn_edges.add(edge_key)

        for node in self.state.nodes:
            nx, ny = self.get_node_pos(node)
            name_text = self.font.render(node.name, True, BLACK)
            self.screen.blit(name_text, (nx - name_text.get_width() // 2, ny - NODE_RADIUS - 18))

            visible = node in player_visibility or force_full or self.state.mode == "God"
            if not visible:
                pygame.draw.circle(self.screen, FOG, (nx, ny), NODE_RADIUS)
                continue

            color = GRAY
            if node == self.state.player_castle_node:
                color = BLUE
            elif node == self.state.enemy_castle_node:
                color = RED

            pygame.draw.circle(self.screen, color, (nx, ny), NODE_RADIUS)
            pygame.draw.circle(self.screen, BLACK, (nx, ny), NODE_RADIUS, 2)

            intel = "full" if force_full or self.state.mode == "God" else self.state.get_intel(0, node)
            if node.structure and intel == "full":
                s_text = self.font.render(node.structure[0], True, BLACK)
                self.screen.blit(s_text, (nx - 5, ny - 28))

            self._draw_units_on_node(node, intel, force_full=force_full)

        # Bottom panel (excludes right replay strip when replaying)
        panel_y = SCREEN_HEIGHT - BOTTOM_PANEL_HEIGHT
        pygame.draw.rect(self.screen, GRAY, (0, panel_y, play_width, BOTTOM_PANEL_HEIGHT))
        pygame.draw.line(self.screen, BLACK, (0, panel_y), (play_width, panel_y), 2)

        section_w = play_width // 3
        sec1_x = 10
        curr_y = panel_y + 15
        self.screen.blit(pygame.font.SysFont("Arial", 18, bold=True).render("Kingdom Info", True, BLACK), (sec1_x, curr_y))
        mode_label = self.replay_data_mode() if is_replay else self.state.mode
        self.screen.blit(self.font.render(f"Mode: {mode_label}", True, BLACK), (sec1_x, curr_y + 30))
        self.screen.blit(self.font.render("Your Turn" if not is_replay else "Replay", True, BLUE), (sec1_x, curr_y + 55))
        self.screen.blit(self.font.render(f"Turn #: {self.state.turn_count}", True, BLACK), (sec1_x, curr_y + 80))

        if self.audio_recorder.is_recording and not is_replay:
            pulse = int(50 * (1 + math.sin(pygame.time.get_ticks() / 150)))
            rec_color = (255, 100 + pulse, 100 + pulse)
            pygame.draw.circle(self.screen, rec_color, (sec1_x + 10, curr_y + 120), 6)
            self.screen.blit(self.font.render("REC", True, rec_color), (sec1_x + 20, curr_y + 110))

        pygame.draw.line(self.screen, BLACK, (section_w, panel_y), (section_w, SCREEN_HEIGHT), 2)

        sec2_x = section_w + 10
        curr_y = panel_y + 15
        self.screen.blit(pygame.font.SysFont("Arial", 18, bold=True).render("Available Orders", True, BLACK), (sec2_x, curr_y))
        if is_replay and self.replay_player:
            total = len(self.replay_player.actions)
            idx = self.replay_player.index
            self.screen.blit(self.font.render(f"Action {idx}/{total}", True, BLACK), (sec2_x, curr_y + 30))
            if self.replay_player.done():
                self.screen.blit(self.font.render("Replay finished", True, GREEN), (sec2_x, curr_y + 55))
        else:
            available = 0 if self.state.has_acted[0] else 1
            self.screen.blit(self.font.render(f"{available}/1", True, BLACK), (sec2_x, curr_y + 30))
            if self.state.has_acted[0]:
                self.screen.blit(self.font.render("Order Executed", True, RED), (sec2_x, curr_y + 55))
            else:
                self.screen.blit(self.font.render("Awaiting Order...", True, DARK_GRAY), (sec2_x, curr_y + 55))

        pygame.draw.line(self.screen, BLACK, (section_w * 2, panel_y), (section_w * 2, SCREEN_HEIGHT), 2)

        sec3_x = section_w * 2 + 10
        curr_y = panel_y + 15
        self.screen.blit(pygame.font.SysFont("Arial", 18, bold=True).render("Quick Controls", True, BLACK), (sec3_x, curr_y))
        controls = (
            ["See right panel", "for replay controls"]
            if is_replay
            else ["R-Click: Order (instant)", "SPACE: End Turn", "W>A>Z>W advantage"]
        )
        for i, ctrl in enumerate(controls):
            self.screen.blit(self.font.render(ctrl, True, BLACK), (sec3_x, curr_y + 30 + i * 25))

        if is_replay:
            self._draw_replay_panel()

        self.context_menu.draw(self.screen)

        for msg in self.floating_messages[:]:
            alpha = min(255, msg["life"] * 5)
            text_surf = self.ui_font.render(msg["text"], True, RED)
            s = pygame.Surface(text_surf.get_size(), pygame.SRCALPHA)
            s.fill((255, 255, 255, alpha))
            text_surf.blit(s, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self.screen.blit(text_surf, msg["pos"])
            msg["pos"] = (msg["pos"][0], msg["pos"][1] - 1)
            msg["life"] -= 1
            if msg["life"] <= 0:
                self.floating_messages.remove(msg)

        notif_y = 50
        for notif in self.notifications[:]:
            notif_w = 280
            notif_h = 40
            notif_rect = pygame.Rect(SCREEN_WIDTH - notif_w - 20, notif_y, notif_w, notif_h)
            alpha = min(255, notif["life"] * 5)
            s = pygame.Surface((notif_w, notif_h), pygame.SRCALPHA)
            pygame.draw.rect(s, (100, 255, 100, alpha), s.get_rect(), border_radius=5)
            pygame.draw.rect(s, (0, 0, 0, alpha), s.get_rect(), 2, border_radius=5)
            s.blit(self.font.render(notif["text"], True, (0, 0, 0)), (10, 10))
            self.screen.blit(s, notif_rect)
            notif_y += notif_h + 10
            notif["life"] -= 1
            if notif["life"] <= 0:
                self.notifications.remove(notif)

        if self.ai_thinking and not is_replay:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            self.screen.blit(overlay, (0, 0))
            think_text = self.ui_font.render("AI is thinking...", True, YELLOW)
            self.screen.blit(think_text, think_text.get_rect(center=(play_width // 2, MAP_HEIGHT // 2)))

        if self.state.game_over and not is_replay and self.ui_state == UIState.PLAYING:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            self.screen.blit(overlay, (0, 0))
            winner_text = f"GAME OVER! {'Victory!' if self.state.winner == 0 else 'Defeat!'}"
            text_surf = self.ui_font.render(winner_text, True, GREEN if self.state.winner == 0 else RED)
            self.screen.blit(text_surf, (SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2 - 40))
            hint = self.font.render("Continuing to feedback...", True, WHITE)
            self.screen.blit(hint, (SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 + 10))

    def replay_data_mode(self):
        if self.replay_player:
            return self.replay_player.replay_data.get("mode", self.state.mode)
        return self.state.mode

    def _draw_replay_panel(self):
        panel_x = SCREEN_WIDTH - REPLAY_PANEL_WIDTH
        pygame.draw.rect(self.screen, DARK_GRAY, (panel_x, 0, REPLAY_PANEL_WIDTH, SCREEN_HEIGHT))
        pygame.draw.line(self.screen, BLACK, (panel_x, 0), (panel_x, SCREEN_HEIGHT), 2)
        title = self.ui_font.render("Replay", True, WHITE)
        self.screen.blit(title, (panel_x + 20, 25))
        if self.replay_player:
            total = len(self.replay_player.actions)
            idx = self.replay_player.index
            self.screen.blit(
                self.font.render(f"{idx} / {total}", True, WHITE),
                (panel_x + 20, 380),
            )
            status = "Finished" if self.replay_player.done() else ("Playing..." if self.replay_player.playing else "Paused")
            self.screen.blit(self.font.render(status, True, YELLOW), (panel_x + 20, 410))
        for btn in self.replay_buttons:
            btn.draw(self.screen)

    def draw_feedback(self):
        self.screen.fill(DARK_GRAY)
        if self.state:
            self.draw_gameplay()
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            self.screen.blit(overlay, (0, 0))

        if self.feedback_is_final:
            title_text = "Final AI Feedback"
            subtitle = ""
            if self.state:
                subtitle = "Victory!" if self.state.winner == 0 else "Defeat!"
            subtitle = f"{subtitle} — This form cannot be skipped."
        else:
            title_text = "Mid-Game AI Feedback"
            subtitle = f"Turn {self.state.turn_count if self.state else '?'} — This form cannot be skipped."

        title = self.ui_font.render(title_text, True, WHITE)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 120)))
        self.screen.blit(
            self.font.render(subtitle, True, YELLOW),
            (SCREEN_WIDTH // 2 - 180, 160),
        )
        entry_count = len(self.feedback_entries)
        self.screen.blit(
            self.font.render(f"Responses so far: {entry_count}", True, WHITE),
            (SCREEN_WIDTH // 2 - 80, 190),
        )

        self.screen.blit(self.font.render("Difficulty (1 = Easy, 5 = Hard):", True, WHITE), (SCREEN_WIDTH // 2 - 300, 220))
        for i in range(1, 6):
            rect = pygame.Rect(SCREEN_WIDTH // 2 - 300 + (i - 1) * 70, 250, 55, 40)
            color = YELLOW if self.feedback_rating == i else GRAY
            pygame.draw.rect(self.screen, color, rect)
            pygame.draw.rect(self.screen, BLACK, rect, 2)
            label = self.ui_font.render(str(i), True, BLACK)
            self.screen.blit(label, label.get_rect(center=rect.center))

        self.screen.blit(
            self.font.render("What do you think the AI is doing?", True, WHITE),
            (SCREEN_WIDTH // 2 - 300, 310),
        )
        if self.feedback_input:
            self.feedback_input.draw(self.screen)

        submit = Button(SCREEN_WIDTH // 2 - 100, 420, 200, 50, "Submit", self.ui_font)
        submit.is_hovered = submit.rect.collidepoint(pygame.mouse.get_pos())
        submit.draw(self.screen)
        self._feedback_submit_btn = submit

        for notif in self.notifications[:]:
            self.screen.blit(self.font.render(notif["text"], True, RED), (SCREEN_WIDTH // 2 - 120, 490))
            notif["life"] -= 1
            if notif["life"] <= 0:
                self.notifications.remove(notif)

    def draw_replay_menu(self):
        self.screen.fill(DARK_GRAY)
        title = self.title_font.render("Replays", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 80)))

        back = Button(40, 40, 120, 40, "Back", self.font)
        back.is_hovered = back.rect.collidepoint(pygame.mouse.get_pos())
        back.draw(self.screen)
        self._replay_back_btn = back

        if not self.replay_list:
            self.screen.blit(
                self.ui_font.render("No replays saved yet.", True, WHITE),
                (SCREEN_WIDTH // 2 - 140, 300),
            )
            return

        y = 140 - self.replay_scroll
        self._replay_entry_rects = []
        for entry in self.replay_list:
            if y > 120 and y < SCREEN_HEIGHT - 80:
                rect = pygame.Rect(SCREEN_WIDTH // 2 - 350, y, 700, 50)
                pygame.draw.rect(self.screen, GRAY, rect)
                pygame.draw.rect(self.screen, BLACK, rect, 2)
                self.screen.blit(self.font.render(entry["name"], True, BLACK), (rect.x + 15, rect.y + 15))
                play_btn = pygame.Rect(rect.right - 100, rect.y + 8, 85, 34)
                pygame.draw.rect(self.screen, GREEN, play_btn)
                pygame.draw.rect(self.screen, BLACK, play_btn, 1)
                self.screen.blit(self.font.render("Play", True, BLACK), (play_btn.x + 22, play_btn.y + 6))
                self._replay_entry_rects.append((play_btn, entry))
            y += 60

    def draw_menu(self):
        self.screen.fill(BLUE)
        title_surf = self.title_font.render("Don't Shoot the Messenger", True, WHITE)
        self.screen.blit(title_surf, title_surf.get_rect(center=(SCREEN_WIDTH // 2, 150)))
        subtitle_surf = self.font.render("A Strategy Game", True, WHITE)
        self.screen.blit(subtitle_surf, subtitle_surf.get_rect(center=(SCREEN_WIDTH // 2, 210)))
        for btn in self.menu_buttons:
            btn.draw(self.screen)

    def draw_settings(self):
        self.screen.fill(DARK_GRAY)
        title_surf = self.title_font.render("Settings", True, WHITE)
        self.screen.blit(title_surf, title_surf.get_rect(center=(SCREEN_WIDTH // 2, 100)))
        ai_type = self.ai_types[self.selected_ai_index]
        info_surf = self.ui_font.render(f"Current Mode: {self.selected_mode} | AI: {ai_type}", True, YELLOW)
        self.screen.blit(info_surf, info_surf.get_rect(center=(SCREEN_WIDTH // 2, 180)))
        for btn in self.settings_buttons:
            btn.draw(self.screen)

    def draw(self):
        if self.ui_state == UIState.MAIN_MENU:
            self.draw_menu()
        elif self.ui_state == UIState.SETTINGS:
            self.draw_settings()
        elif self.ui_state == UIState.PLAYING:
            self.draw_gameplay()
        elif self.ui_state == UIState.FEEDBACK:
            self.draw_feedback()
        elif self.ui_state == UIState.REPLAY_MENU:
            self.draw_replay_menu()
        elif self.ui_state == UIState.REPLAYING:
            self.draw_gameplay(is_replay=True)
        pygame.display.flip()

    def handle_menu_events(self, event, running_ref):
        for i, btn in enumerate(self.menu_buttons):
            if btn.handle_event(event):
                if i == 0:
                    self.start_new_game()
                elif i == 1:
                    self.open_replay_menu()
                elif i == 2:
                    self.ui_state = UIState.SETTINGS
                elif i == 3:
                    running_ref[0] = False

    def handle_settings_events(self, event):
        for i, btn in enumerate(self.settings_buttons):
            if btn.handle_event(event):
                if i == 0:
                    curr_idx = self.mode_options.index(self.selected_mode)
                    self.selected_mode = self.mode_options[(curr_idx + 1) % len(self.mode_options)]
                    self._rebuild_settings_buttons()
                elif i == 1:
                    self.selected_ai_index = (self.selected_ai_index + 1) % len(self.ai_types)
                    self._rebuild_settings_buttons()
                elif i == 2:
                    if self.available_maps and self.ai_types[self.selected_ai_index] != "AI 0":
                        self.selected_map_index = (self.selected_map_index + 1) % len(self.available_maps)
                        self._rebuild_settings_buttons()
                elif i == 3:
                    self.voice_recording_enabled = not self.voice_recording_enabled
                    self._rebuild_settings_buttons()
                elif i == 4:
                    self.audio_recorder.stop_recording()
                    self.ui_state = UIState.MAIN_MENU

    def handle_feedback_events(self, event):
        if self.feedback_input:
            self.feedback_input.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(1, 6):
                rect = pygame.Rect(SCREEN_WIDTH // 2 - 300 + (i - 1) * 70, 250, 55, 40)
                if rect.collidepoint(event.pos):
                    self.feedback_rating = i
            if hasattr(self, "_feedback_submit_btn") and self._feedback_submit_btn.rect.collidepoint(event.pos):
                self.submit_feedback()

        # Block ESC / quit shortcuts from skipping — only allow window close via QUIT in run()
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            pass

    def handle_replay_menu_events(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if hasattr(self, "_replay_back_btn") and self._replay_back_btn.rect.collidepoint(event.pos):
                self.ui_state = UIState.MAIN_MENU
                return
            for rect, entry in getattr(self, "_replay_entry_rects", []):
                if rect.collidepoint(event.pos):
                    self.start_replay(entry, full_map=True)
                    return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.replay_scroll = max(0, self.replay_scroll + (-30 if event.button == 4 else 30))

    def handle_replaying_events(self, event):
        for i, btn in enumerate(self.replay_buttons):
            if btn.handle_event(event):
                if i == 0:
                    self.replay_player.playing = not self.replay_player.playing
                    self._rebuild_replay_controls()
                elif i == 1:
                    self.replay_player.step()
                    self.state = self.replay_player.state
                elif i == 2:
                    self.replay_player.step_back()
                    self.state = self.replay_player.state
                    self._rebuild_replay_controls()
                elif i == 3:
                    self.replay_player.set_full_map_view(not self.replay_player.full_map_view)
                    self._rebuild_replay_controls()
                elif i == 4:
                    self.replay_player = None
                    self.state = None
                    self.ui_state = UIState.REPLAY_MENU
                    self.open_replay_menu()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            in_map = (
                event.pos[0] < SCREEN_WIDTH - REPLAY_PANEL_WIDTH
                and event.pos[1] < SCREEN_HEIGHT - BOTTOM_PANEL_HEIGHT
            )
            if in_map:
                self.is_dragging = True
                self.drag_start_x = event.pos[0]
                self.drag_start_y = event.pos[1]
                self.camera_start_x = self.camera_x
                self.camera_start_y = self.camera_y
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.is_dragging = False
        if event.type == pygame.MOUSEMOTION and self.is_dragging:
            self.camera_x = self.camera_start_x + (event.pos[0] - self.drag_start_x)
            self.camera_y = self.camera_start_y + (event.pos[1] - self.drag_start_y)

    def _issue_player_order(self, source_node, target_node, count, unit_type):
        if self.state.has_acted[0]:
            self.floating_messages.append({
                "text": "1 Order Per Turn",
                "pos": pygame.mouse.get_pos(),
                "life": 60,
            })
            return
        ok = self.state.issue_order_to_tile(
            0, source_node, "move_attack", target_node, count=count, unit_type=unit_type
        )
        if not ok:
            self.floating_messages.append({
                "text": "1 Order Per Turn",
                "pos": pygame.mouse.get_pos(),
                "life": 60,
            })
            return
        self.state.execute_player_order_immediately()
        if self.state.game_over:
            self.pending_game_over = True

    def run(self):
        running_ref = [True]
        game_over_delay = 0

        while running_ref[0]:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    if self.ui_state == UIState.FEEDBACK:
                        # Still allow closing the window, but prefer forcing submit path
                        # Keep unskippable for ESC/menu; QUIT exits app.
                        running_ref[0] = False
                    else:
                        running_ref[0] = False

                keys = pygame.key.get_pressed()
                if (
                    self.ui_state not in (UIState.FEEDBACK,)
                    and keys[pygame.K_a]
                    and keys[pygame.K_o]
                    and keys[pygame.K_p]
                ):
                    if self.ui_state == UIState.PLAYING:
                        # Don't abandon mid-match without feedback path via shortcut while prompting
                        pass
                    self.audio_recorder.stop_recording()
                    self.ui_state = UIState.MAIN_MENU
                    pygame.time.delay(200)

                if self.ui_state == UIState.MAIN_MENU:
                    self.handle_menu_events(event, running_ref)
                elif self.ui_state == UIState.SETTINGS:
                    self.handle_settings_events(event)
                elif self.ui_state == UIState.FEEDBACK:
                    self.handle_feedback_events(event)
                elif self.ui_state == UIState.REPLAY_MENU:
                    self.handle_replay_menu_events(event)
                elif self.ui_state == UIState.REPLAYING:
                    self.handle_replaying_events(event)
                elif self.ui_state == UIState.PLAYING and self.state and not self.state.game_over:
                    if self.context_menu.visible and self.context_menu.text_input:
                        if self.context_menu.text_input.handle_event(event):
                            for opt in self.context_menu.options:
                                if opt.get("is_splitter"):
                                    val = self.context_menu.text_input.get_value()
                                    if val is not None:
                                        source_node, target_node = opt["data"]
                                        self._issue_player_order(
                                            source_node, target_node, val, opt.get("unit_type")
                                        )
                                        self.context_menu.hide()
                                    break

                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if event.button == 1:
                            in_map = event.pos[1] < SCREEN_HEIGHT - BOTTOM_PANEL_HEIGHT
                            if self.context_menu.visible:
                                menu_result = self.context_menu.handle_click(event.pos, hide_automatically=False)
                                if menu_result:
                                    if menu_result.get("prepare_split"):
                                        source_node, target_node = menu_result["data"]
                                        unit_type = menu_result.get("unit_type")
                                        stack = self.state.get_unit_at(source_node, 0, unit_type)
                                        amount = stack.count if stack else 1
                                        self.context_menu.show(
                                            event.pos,
                                            [
                                                {
                                                    "label": f"Move All {unit_type} -> {target_node.name}",
                                                    "command": "move_attack",
                                                    "data": (source_node, target_node),
                                                    "unit_type": unit_type,
                                                    "amount": amount,
                                                },
                                                {
                                                    "label": "Split & Move:",
                                                    "command": "move_attack",
                                                    "data": (source_node, target_node),
                                                    "unit_type": unit_type,
                                                    "is_splitter": True,
                                                    "amount": max(1, amount // 2),
                                                },
                                                {"label": "Cancel", "command": "hide"},
                                            ],
                                            target_node,
                                        )
                                        continue

                                    if menu_result.get("is_splitter") and self.context_menu.text_input:
                                        val = self.context_menu.text_input.get_value()
                                        if val is not None:
                                            menu_result["amount"] = val

                                    self.context_menu.hide()
                                    cmd = menu_result["command"]
                                    if cmd == "hide":
                                        continue
                                    if cmd == "move_attack":
                                        source_node, target_node = menu_result["data"]
                                        count = menu_result.get("amount")
                                        self._issue_player_order(
                                            source_node,
                                            target_node,
                                            count,
                                            menu_result.get("unit_type"),
                                        )
                                    elif cmd == "select_unit":
                                        # Show destinations for chosen stack
                                        unit_type = menu_result["unit_type"]
                                        node = menu_result["data"]
                                        options = []
                                        for neighbor in node.neighbors:
                                            options.append({
                                                "label": f"Move {unit_type} -> {neighbor.name}",
                                                "command": "move_attack",
                                                "prepare_split": True,
                                                "unit_type": unit_type,
                                                "data": (node, neighbor),
                                            })
                                        options.append({"label": "Cancel", "command": "hide"})
                                        self.context_menu.show(event.pos, options, node)
                            elif in_map:
                                self.is_dragging = True
                                self.drag_start_x = event.pos[0]
                                self.drag_start_y = event.pos[1]
                                self.camera_start_x = self.camera_x
                                self.camera_start_y = self.camera_y
                            else:
                                self.context_menu.hide()

                        elif event.button == 3:
                            if event.pos[1] < SCREEN_HEIGHT - BOTTOM_PANEL_HEIGHT:
                                if self.state.has_acted[0]:
                                    self.floating_messages.append({
                                        "text": "1 Order Per Turn",
                                        "pos": event.pos,
                                        "life": 60,
                                    })
                                    continue

                                node = self.get_node_at_mouse(event.pos)
                                if node:
                                    allied = [u for u in self.state.units if u.node == node and u.owner == 0]
                                    if not allied:
                                        self.floating_messages.append({
                                            "text": "Requires Allied Units",
                                            "pos": event.pos,
                                            "life": 60,
                                        })
                                        continue

                                    options = []
                                    types_present = sorted({u.unit_type for u in allied})
                                    if len(types_present) == 1:
                                        unit_type = types_present[0]
                                        for neighbor in node.neighbors:
                                            options.append({
                                                "label": f"Move {unit_type} -> {neighbor.name}",
                                                "command": "move_attack",
                                                "prepare_split": True,
                                                "unit_type": unit_type,
                                                "data": (node, neighbor),
                                            })
                                    else:
                                        for unit_type in types_present:
                                            stack = self.state.get_unit_at(node, 0, unit_type)
                                            options.append({
                                                "label": f"Select {unit_type} ({stack.count})",
                                                "command": "select_unit",
                                                "unit_type": unit_type,
                                                "data": node,
                                            })
                                    if options:
                                        self.context_menu.show(event.pos, options, node)
                                else:
                                    self.context_menu.hide()

                        elif event.button in (4, 5):
                            if self.context_menu.visible:
                                change = 1 if event.button == 4 else -1
                                for opt in self.context_menu.options:
                                    if opt.get("is_splitter"):
                                        opt["amount"] = max(1, opt["amount"] + change)
                                        if self.context_menu.text_input:
                                            self.context_menu.text_input.set_text(str(opt["amount"]))

                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_SPACE and not self.ai_thinking:
                            self.state.end_turn()
                            self.context_menu.hide()
                            if self.state.game_over:
                                self.pending_game_over = True
                                game_over_delay = 90
                            else:
                                self.ai_thinking = True
                                self.ai_think_timer = 30
                                # Mid-game prompt every N turns (after AI has acted)
                                if (
                                    self.state.turn_count > 1
                                    and self.state.turn_count % MIDGAME_PROMPT_INTERVAL == 1
                                ):
                                    self.pending_midgame_prompt = True
                            self.audio_recorder.mark_turn(self.state.turn_count)

                    if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                        self.is_dragging = False

                    if event.type == pygame.MOUSEMOTION and self.is_dragging:
                        self.camera_x = self.camera_start_x + (event.pos[0] - self.drag_start_x)
                        self.camera_y = self.camera_start_y + (event.pos[1] - self.drag_start_y)

            if self.ai_thinking:
                self.ai_think_timer -= 1
                if self.ai_think_timer <= 0:
                    self.ai_thinking = False
                    if self.pending_midgame_prompt and self.state and not self.state.game_over:
                        self.pending_midgame_prompt = False
                        self.begin_feedback(final=False)

            if self.ui_state == UIState.PLAYING and self.state and self.state.game_over:
                if self.pending_game_over:
                    game_over_delay -= 1
                    if game_over_delay <= 0:
                        self.pending_game_over = False
                        self.begin_feedback(final=True)
                elif not self.pending_game_over:
                    self.pending_game_over = True
                    game_over_delay = 90

            if self.ui_state == UIState.REPLAYING and self.replay_player:
                self.replay_player.tick()
                self.state = self.replay_player.state

            self.draw()
            self.clock.tick(60)

        self.audio_recorder.stop_recording()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    game = Game()
    game.run()
