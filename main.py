import os
import sys
import warnings

# Suppress pygame startup messages and AVX2 warnings
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = 'hide'
# Suppress the AVX2 warning from being printed to stderr
warnings.filterwarnings("ignore", message="Your system is avx2 capable")

import pygame
from game.engine import GameState
from game.graph import get_available_maps

# Constants
# Initial dimensions for windowed mode
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 800

# Desktop dimensions will be stored here
DESKTOP_WIDTH = 0
DESKTOP_HEIGHT = 0

# Screen dimensions will be set dynamically
SCREEN_WIDTH = WINDOW_WIDTH
SCREEN_HEIGHT = WINDOW_HEIGHT

GRID_SIZE = 3
CELL_SIZE = 80
BOTTOM_PANEL_HEIGHT = 150
REPORT_PANEL_WIDTH = 300
MAP_WIDTH = SCREEN_WIDTH - REPORT_PANEL_WIDTH
MAP_HEIGHT = SCREEN_HEIGHT - BOTTOM_PANEL_HEIGHT

GRID_OFFSET_X = (MAP_WIDTH - (GRID_SIZE * (CELL_SIZE + 20))) // 2
GRID_OFFSET_Y = (MAP_HEIGHT - (GRID_SIZE * (CELL_SIZE + 20))) // 2
NODE_RADIUS = 30

from enum import Enum
class UIState(Enum):
    MAIN_MENU = 1
    SETTINGS = 2
    PLAYING = 3
    GAMEOVER = 4

from game.ui_components import Button, TextInput

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
DARK_GRAY = (100, 100, 100)
RED = (255, 100, 100)
BLUE = (100, 100, 255)
GREEN = (100, 255, 100)
YELLOW = (255, 255, 100)
FOG = (50, 50, 50)
GOLD = (255, 215, 0)
PURPLE = (180, 100, 200)

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
        
        # Initialize text input if splitter is present
        for opt in options:
            if opt.get("is_splitter"):
                input_w = 60
                input_h = 24
                # Position it will be set in draw
                self.text_input = TextInput(0, 0, input_w, input_h, self.font)
                self.text_input.set_text(str(opt.get("amount", 0)))
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
                input_w = 60 # Default text input width
                suffix_w = self.font.size(" (Scroll to adjust)")[0]
                return prefix_w + input_w + suffix_w + 20
            return self.font.size(label)[0]

        width = max(get_label_width(opt) for opt in self.options) + self.padding * 2
        height = len(self.options) * self.option_height
        return pygame.Rect(self.pos[0], self.pos[1], width, height)
    
    def draw(self, screen):
        if not self.visible or not self.options:
            return
        
        rect = self.get_rect()
        pygame.draw.rect(screen, WHITE, rect)
        pygame.draw.rect(screen, BLACK, rect, 2)
        
        # Clamp menu position to screen
        if self.pos[0] + rect.width > SCREEN_WIDTH:
            rect.x = SCREEN_WIDTH - rect.width
        if self.pos[1] + rect.height > SCREEN_HEIGHT:
            rect.y = SCREEN_HEIGHT - rect.height

        curr_y = rect.y
        for i, opt in enumerate(self.options):
            opt_rect = pygame.Rect(rect.x, curr_y, rect.width, self.option_height)
            
            # Highlight on hover (unless text input is being used)
            if not (self.text_input and self.text_input.rect.collidepoint(pygame.mouse.get_pos())):
                if opt_rect.collidepoint(pygame.mouse.get_pos()):
                    pygame.draw.rect(screen, GRAY, opt_rect)
            
            if opt.get("is_splitter"):
                label = opt["label"]
                # Render prefix
                prefix_surf = self.font.render(label, True, BLACK)
                screen.blit(prefix_surf, (rect.x + self.padding, curr_y + 5))
                prefix_w = prefix_surf.get_width()
                
                # Position and draw text input
                if self.text_input:
                    self.text_input.rect.x = rect.x + self.padding + prefix_w + 5
                    self.text_input.rect.y = curr_y + 3
                    self.text_input.draw(screen)
                    input_w = self.text_input.rect.width
                else:
                    input_w = 0
                
                # Render suffix
                suffix_surf = self.font.render(" (Scroll to adjust)", True, BLACK)
                screen.blit(suffix_surf, (rect.x + self.padding + prefix_w + input_w + 10, curr_y + 5))
            else:
                label = opt["label"]
                text_surf = self.font.render(label, True, BLACK)
                screen.blit(text_surf, (rect.x + self.padding, curr_y + 5))
            
            curr_y += self.option_height
            
    def handle_click(self, pos, hide_automatically=True):
        if not self.visible:
            return None
        
        if self.text_input and self.text_input.rect.collidepoint(pos):
            self.text_input.active = True
            return None # Don't trigger a click on options if clicking input
        
        rect = self.get_rect()
        # Account for possible clamping in draw
        if self.pos[0] + rect.width > SCREEN_WIDTH: rect.x = SCREEN_WIDTH - rect.width
        if self.pos[1] + rect.height > SCREEN_HEIGHT: rect.y = SCREEN_HEIGHT - rect.height

        if not rect.collidepoint(pos):
            self.hide()
            return None
        
        curr_y = rect.y
        for i, opt in enumerate(self.options):
            opt_rect = pygame.Rect(rect.x, curr_y, rect.width, self.option_height)
            if opt_rect.collidepoint(pos):
                result = opt
                if hide_automatically:
                    self.hide()
                return result
            
            curr_y += self.option_height
            if opt.get("is_splitter") and self.text_input:
                pass # Already handled in option loop
        
        self.hide()
        return None


class Game:
    def __init__(self):
        pygame.init()
        
        # Get desktop resolution and store it
        info = pygame.display.Info()
        global DESKTOP_WIDTH, DESKTOP_HEIGHT, SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT, GRID_OFFSET_X, GRID_OFFSET_Y
        DESKTOP_WIDTH = info.current_w
        DESKTOP_HEIGHT = info.current_h
        
        # Use a window sized slightly smaller than desktop to account for taskbars/titlebars
        # This ensures the bottom isn't cut off and window buttons are visible
        SCREEN_WIDTH = DESKTOP_WIDTH
        SCREEN_HEIGHT = DESKTOP_HEIGHT - 80 
        
        # Re-calculate constants that depend on screen size
        MAP_WIDTH = SCREEN_WIDTH - REPORT_PANEL_WIDTH
        MAP_HEIGHT = SCREEN_HEIGHT - BOTTOM_PANEL_HEIGHT
        GRID_OFFSET_X = (MAP_WIDTH - (GRID_SIZE * (CELL_SIZE + 20))) // 2
        GRID_OFFSET_Y = (MAP_HEIGHT - (GRID_SIZE * (CELL_SIZE + 20))) // 2

        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.fullscreen = True
        
        pygame.display.set_caption("Don't Shoot the Messenger - Strategy Game")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 18)
        self.title_font = pygame.font.SysFont("Arial", 48, bold=True)
        self.ui_font = pygame.font.SysFont("Arial", 24, bold=True)
        
        self.ui_state = UIState.MAIN_MENU
        self.selected_mode = "God"
        self.automated_phases = True
        self.state = None  # Initialized when game starts
        self.mode_options = ["God", "Fog", "Realistic"]
        self.context_menu = ContextMenu(self.font)
        
        # Camera/Viewport panning
        self.camera_x = 0
        self.camera_y = 0
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.camera_start_x = 0
        self.camera_start_y = 0
        
        # Report UI State
        self.report_popup_visible = False
        self.report_popup_content = None
        self.sidebar_scroll_offset = 0
        self.popup_scroll_offset = 0
        self.report_boxes = [] # Track areas (rect, report) for click detection
        
        # Map selection
        self.maps_dir = os.path.join(os.path.dirname(__file__), "maps")
        self.available_maps = get_available_maps(self.maps_dir)
        self.selected_map_index = 0
        if "default_3x3" in self.available_maps:
            self.selected_map_index = self.available_maps.index("default_3x3")
        
        # UI Elements for Main Menu
        button_w, button_h = 200, 50
        self.menu_buttons = [
            Button(SCREEN_WIDTH//2 - 100, 300, button_w, button_h, "Start Game", self.ui_font),
            Button(SCREEN_WIDTH//2 - 100, 370, button_w, button_h, "Settings", self.ui_font),
            Button(SCREEN_WIDTH//2 - 100, 440, button_w, button_h, "Quit", self.ui_font)
        ]
        
        # UI Elements for Settings (will be rebuilt with map button)
        self._rebuild_settings_buttons()

    def _rebuild_settings_buttons(self):
        """Rebuild settings buttons with current map name and fullscreen state."""
        button_w, button_h = 200, 50
        map_name = self.available_maps[self.selected_map_index] if self.available_maps else "none"
        fs_text = "Fullscreen: ON" if self.fullscreen else "Fullscreen: OFF"
        self.settings_buttons = [
            Button(SCREEN_WIDTH//2 - 100, 200, button_w, button_h, "Mode: God", self.font),
            Button(SCREEN_WIDTH//2 - 100, 260, button_w, button_h, "Mode: Fog", self.font),
            Button(SCREEN_WIDTH//2 - 100, 320, button_w, button_h, "Mode: Realistic", self.font),
            Button(SCREEN_WIDTH//2 - 100, 380, button_w, button_h, "Phase: Auto", self.font),
            Button(SCREEN_WIDTH//2 - 100, 440, button_w, button_h, f"Map: {map_name}", self.font),
            Button(SCREEN_WIDTH//2 - 100, 500, button_w, button_h, fs_text, self.font),
            Button(SCREEN_WIDTH//2 - 100, 580, button_w, button_h, "Back", self.ui_font)
        ]

    def start_new_game(self):
        map_name = self.available_maps[self.selected_map_index] if self.available_maps else "default_3x3"
        self.state = GameState(mode=self.selected_mode, automated_phases=self.automated_phases, map_name=map_name)
        self.ui_state = UIState.PLAYING
        # Reset camera for new game
        self.camera_x = 0
        self.camera_y = 0
        self.is_dragging = False

    def update_unit_panel(self):
        pass  # Method removed as per plan

    def get_node_pos(self, node):
        """Get screen position for a node, accounting for camera offset."""
        x = GRID_OFFSET_X + node.x * (CELL_SIZE + 20) + CELL_SIZE // 2 + self.camera_x
        y = GRID_OFFSET_Y + node.y * (CELL_SIZE + 20) + CELL_SIZE // 2 + self.camera_y
        return x, y

    def get_node_at_mouse(self, pos):
        mx, my = pos
        for node in self.state.nodes:
            nx, ny = self.get_node_pos(node)
            dist = ((mx - nx)**2 + (my - ny)**2)**0.5
            if dist <= NODE_RADIUS:
                return node
        return None

    def draw_pigeons(self):
        """Draw pigeons as small triangles traveling between nodes"""
        return # Pigeons are now invisible in all modes

        for pigeon in self.state.pigeons:

            progress = pigeon.get_progress()
            
            if pigeon.returning:
                # From target back to source (castle)
                start_pos = self.get_node_pos(pigeon.target_node)
                end_pos = self.get_node_pos(pigeon.source_node)
            else:
                # From source (castle) to target
                start_pos = self.get_node_pos(pigeon.source_node)
                end_pos = self.get_node_pos(pigeon.target_node)
            
            # Interpolate position
            curr_x = start_pos[0] + (end_pos[0] - start_pos[0]) * progress
            curr_y = start_pos[1] + (end_pos[1] - start_pos[1]) * progress
            
            # Draw pigeon as a small colored triangle
            color = BLUE if pigeon.owner == 0 else RED
            size = 8
            points = [
                (curr_x, curr_y - size),
                (curr_x - size, curr_y + size),
                (curr_x + size, curr_y + size)
            ]
            pygame.draw.polygon(self.screen, color, points)
            pygame.draw.polygon(self.screen, BLACK, points, 1)
            
            # Draw a small "P" label
            p_text = self.font.render("P", True, WHITE)
            self.screen.blit(p_text, (curr_x - 4, curr_y - 5))

    def draw_gameplay(self):
        self.screen.fill(WHITE)
        
        # Override visibility for game-over reveal
        if self.state.game_over:
            player_visibility = set(self.state.nodes)  # All nodes visible
        else:
            player_visibility = self.state.visible_nodes[self.state.turn]

        # Draw connections with travel time labels (Always Visible)
        drawn_edges = set()  # Track drawn edges to avoid duplicates
        for node in self.state.nodes:
            nx, ny = self.get_node_pos(node)
            for neighbor in node.neighbors:
                # Create edge key to avoid drawing twice
                edge_key = (min(node.id, neighbor.id), max(node.id, neighbor.id))
                if edge_key in drawn_edges:
                    continue
                
                nnx, nny = self.get_node_pos(neighbor)
                pygame.draw.line(self.screen, BLACK, (nx, ny), (nnx, nny), 1)
                
                # Draw travel time at midpoint of edge
                travel_time = node.get_travel_time(neighbor)
                mid_x = (nx + nnx) // 2
                mid_y = (ny + nny) // 2
                time_text = self.font.render(str(travel_time), True, PURPLE)
                # Offset slightly to avoid overlapping the line
                self.screen.blit(time_text, (mid_x - 5, mid_y - 10))
                
                drawn_edges.add(edge_key)

        # Draw nodes
        for node in self.state.nodes:
            nx, ny = self.get_node_pos(node)
            
            # Draw node name above the tile (Always Visible)
            name_text = self.font.render(node.name, True, BLACK)
            name_width = name_text.get_width()
            self.screen.blit(name_text, (nx - name_width // 2, ny - NODE_RADIUS - 20))

            if node not in player_visibility and self.state.mode != "God":
                pygame.draw.circle(self.screen, FOG, (nx, ny), NODE_RADIUS)
                continue

            color = GRAY
            if node == self.state.player_castle_node:
                color = BLUE
            elif node == self.state.enemy_castle_node:
                color = RED
            
            pygame.draw.circle(self.screen, color, (nx, ny), NODE_RADIUS)
            pygame.draw.circle(self.screen, BLACK, (nx, ny), NODE_RADIUS, 2)
            
            # Draw structure icon
            if node.structure:
                s_text = self.font.render(node.structure[0], True, BLACK)
                self.screen.blit(s_text, (nx - 5, ny - 15))

        # Draw units
        for unit in self.state.units:
            if unit.node not in player_visibility and self.state.mode != "God" and not self.state.game_over:
                continue
                
            # If unit is traveling, interpolate its position
            if getattr(unit, 'travel_remaining', 0) > 0 and unit.travel_target:
                start_pos = self.get_node_pos(unit.node)
                end_pos = self.get_node_pos(unit.travel_target)
                
                # Get total travel time from the edge weight
                total_travel = unit.node.get_travel_time(unit.travel_target)
                # Calculate progress (0.0 at start, 1.0 at destination)
                progress = 1.0 - (unit.travel_remaining / total_travel)
                
                nx = start_pos[0] + (end_pos[0] - start_pos[0]) * progress
                ny = start_pos[1] + (end_pos[1] - start_pos[1]) * progress
            else:
                nx, ny = self.get_node_pos(unit.node)
            
            color = BLUE if unit.owner == 0 else RED
            
            pygame.draw.circle(self.screen, color, (nx, ny), NODE_RADIUS - 10)
            
            # Show unit count in God mode, game over, or if at a Castle
            if self.state.mode == "God" or self.state.game_over or unit.node.structure == "Castle":
                count_text = self.font.render(str(unit.count), True, WHITE)
                self.screen.blit(count_text, (nx - 10, ny - 10))

        # Draw pigeons
        self.draw_pigeons()

        # Draw UI Sidebar (Bottom Panel)
        panel_y = SCREEN_HEIGHT - BOTTOM_PANEL_HEIGHT
        panel_w = SCREEN_WIDTH - REPORT_PANEL_WIDTH
        pygame.draw.rect(self.screen, GRAY, (0, panel_y, panel_w, BOTTOM_PANEL_HEIGHT))
        pygame.draw.line(self.screen, BLACK, (0, panel_y), (panel_w, panel_y), 2)
        
        # Section 1: Kingdom Info (Left)
        info_x = 20
        curr_y = panel_y + 15
        title_surf = pygame.font.SysFont("Arial", 20, bold=True).render("Kingdom Info", True, BLACK)
        self.screen.blit(title_surf, (info_x, curr_y))
        
        mode_text = f"Mode: {self.state.mode}"
        self.screen.blit(self.font.render(mode_text, True, BLACK), (info_x, curr_y + 30))
        
        turn_text = f"Turn: {'Player (Blue)' if self.state.turn == 0 else 'Enemy (Red)'}"
        self.screen.blit(self.font.render(turn_text, True, BLUE if self.state.turn == 0 else RED), (info_x, curr_y + 55))
        
        turn_count_text = f"Turn #: {self.state.turn_count}"
        self.screen.blit(self.font.render(turn_count_text, True, BLACK), (info_x, curr_y + 80))
        
        phase_name = self.state.phases[self.state.current_phase_index]
        phase_surf = self.font.render(f"Phase: {phase_name}", True, PURPLE)
        self.screen.blit(phase_surf, (info_x, curr_y + 105))
        
        # Section 2: Resources & Pigeons (Center)
        center_x = panel_w // 3
        curr_y = panel_y + 15
        self.screen.blit(self.font.render("Resources:", True, BLACK), (center_x, curr_y))
        gold = self.state.gold[self.state.turn]
        self.screen.blit(self.font.render(f"Gold: {gold}", True, BLACK), (center_x + 10, curr_y + 25))
            
        pigeon_x = center_x + 150
        active_pigeons = [p for p in self.state.pigeons if p.owner == self.state.turn]
        self.screen.blit(self.font.render(f"Pigeons: {len(active_pigeons)}/{self.state.pigeon_limit[self.state.turn]}", True, BLACK), (pigeon_x, curr_y))
        
        for i, p in enumerate(active_pigeons[:4]): # Show up to 4 pigeons in bottom bar
            status = "Returning" if p.returning else f"Traveling ({p.turns_to_reach}t)"
            p_info = f"P{i+1}: {p.command['type']} -> {status}"
            self.screen.blit(self.font.render(p_info, True, DARK_GRAY), (pigeon_x + 10, curr_y + 25 + i * 20))
            
        # Section 3: Quick Controls (Right)
        ctrl_x = (panel_w * 2) // 3
        curr_y = panel_y + 15
        controls = [
            "R-Click Tile: Issue Order",
            "SPACE: End Turn",
            "ESC: Main Menu"
        ]
        self.screen.blit(self.font.render("Quick Controls:", True, BLACK), (ctrl_x, curr_y))
        for i, ctrl in enumerate(controls):
            self.screen.blit(self.font.render(ctrl, True, BLACK), (ctrl_x + 10, curr_y + 25 + i * 20))

        # Draw Report Panel (Right)
        sidebar_rect = pygame.Rect(SCREEN_WIDTH - REPORT_PANEL_WIDTH, 0, REPORT_PANEL_WIDTH, SCREEN_HEIGHT)
        pygame.draw.rect(self.screen, GRAY, sidebar_rect)
        pygame.draw.line(self.screen, BLACK, (SCREEN_WIDTH - REPORT_PANEL_WIDTH, 0), (SCREEN_WIDTH - REPORT_PANEL_WIDTH, SCREEN_HEIGHT), 2)
        
        report_header = f"{'Player' if self.state.turn == 0 else 'Enemy'} Reports"
        header_surf = self.ui_font.render(report_header, True, BLACK)
        self.screen.blit(header_surf, (SCREEN_WIDTH - REPORT_PANEL_WIDTH + 10, 10))
        
        # Draw accumulated reports for current player with clipping and scrolling
        current_reports = self.state.reports[self.state.turn]
        
        # Define sidebar content area for clipping
        content_rect = pygame.Rect(SCREEN_WIDTH - REPORT_PANEL_WIDTH, 50, REPORT_PANEL_WIDTH, SCREEN_HEIGHT - 50)
        self.screen.set_clip(content_rect)
        
        report_y = 50 - self.sidebar_scroll_offset
        self.report_boxes = []
        
        # Show newest at top
        for report in reversed(current_reports):
            # Summary Box
            box_h = 40
            box_rect = pygame.Rect(SCREEN_WIDTH - REPORT_PANEL_WIDTH + 5, report_y, REPORT_PANEL_WIDTH - 10, box_h)
            
            # Only draw and track if visible (or partially visible) in the clip area
            if box_rect.bottom > content_rect.top and box_rect.top < content_rect.bottom:
                pygame.draw.rect(self.screen, WHITE, box_rect)
                pygame.draw.rect(self.screen, BLACK, box_rect, 1)
                
                # Highlight if hovered
                if box_rect.collidepoint(pygame.mouse.get_pos()) and not self.report_popup_visible:
                    pygame.draw.rect(self.screen, (240, 240, 255), box_rect)
                    pygame.draw.rect(self.screen, BLUE, box_rect, 1)
                
                turn_received = report.get('turn_received', '?')
                summary = f"Turn {turn_received} | Pos: {report['position']}"
                if report.get('message'):
                    summary += " | Message"
                elif 'history' in report and report['history']:
                    summary += " | History"
                
                sum_surf = self.font.render(summary, True, BLACK)
                self.screen.blit(sum_surf, (box_rect.x + 10, box_rect.y + 10))
                
                # Track for clicks
                self.report_boxes.append((box_rect, report))
                
            report_y += box_h + 5
            
        self.screen.set_clip(None)

        # Draw report popup if visible
        if self.report_popup_visible:
            self.draw_report_popup()

        # Draw context menu on top
        self.context_menu.draw(self.screen)

        if self.state.game_over:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            self.screen.blit(overlay, (0,0))
            winner_text = f"GAME OVER! Winner: {'Player' if self.state.winner == 0 else 'Enemy'}"
            text_surf = self.ui_font.render(winner_text, True, GREEN)
            self.screen.blit(text_surf, (SCREEN_WIDTH//2 - 150, SCREEN_HEIGHT//2))



    def draw_report_popup(self):
        if not self.report_popup_content:
            return

        report = self.report_popup_content
        
        # Dim background
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 100))
        self.screen.blit(overlay, (0, 0))
        
        popup_w = 600
        popup_h = 500
        popup_rect = pygame.Rect((SCREEN_WIDTH - popup_w) // 2, (SCREEN_HEIGHT - popup_h) // 2, popup_w, popup_h)
        
        pygame.draw.rect(self.screen, WHITE, popup_rect)
        pygame.draw.rect(self.screen, BLACK, popup_rect, 2)
        
        # Header
        header_h = 40
        header_rect = pygame.Rect(popup_rect.x, popup_rect.y, popup_rect.width, header_h)
        pygame.draw.rect(self.screen, (230, 230, 230), header_rect)
        pygame.draw.line(self.screen, BLACK, (popup_rect.x, popup_rect.y + header_h), (popup_rect.right, popup_rect.y + header_h), 1)
        
        turn = report.get('turn_received', '?')
        title = f"Report: Turn {turn} | Location: {report['position']}"
        self.screen.blit(self.ui_font.render(title, True, BLACK), (popup_rect.x + 15, popup_rect.y + 5))
        
        # Close button "X"
        close_btn_rect = pygame.Rect(popup_rect.right - 35, popup_rect.y + 5, 30, 30)
        pygame.draw.rect(self.screen, RED, close_btn_rect)
        pygame.draw.rect(self.screen, BLACK, close_btn_rect, 1)
        self.screen.blit(self.font.render("X", True, WHITE), (close_btn_rect.x + 10, close_btn_rect.y + 5))
        self.close_btn_rect = close_btn_rect # Save for click detection
        self.popup_rect = popup_rect # Save for click detection
        
        # Content with Scrolling
        content_rect = pygame.Rect(popup_rect.x + 15, popup_rect.y + header_h + 10, popup_rect.width - 30, popup_rect.height - header_h - 25)
        self.screen.set_clip(content_rect)
        
        curr_y = content_rect.y - self.popup_scroll_offset
        max_w = content_rect.width - 20
        
        def draw_text(text, color=BLACK, bold=False):
            nonlocal curr_y
            f = pygame.font.SysFont("Arial", 18, bold=bold)
            lines = self.get_wrapped_lines(text, max_w, f)
            for line in lines:
                surf = f.render(line, True, color)
                self.screen.blit(surf, (content_rect.x, curr_y))
                curr_y += 22

        if 'message' in report:
            draw_text("ORDER DETAILS", bold=True)
            curr_y += 5
            draw_text(report['message'])
            curr_y += 10
            if 'available_turn' in report:
                draw_text(f"Pigeon return turn: {report['available_turn']}", color=DARK_GRAY)
        else:
            draw_text("UNIT STATUS", bold=True)
            curr_y += 5
            draw_text(f"Soldiers remaining: {report['count']}")
            curr_y += 15
            
            draw_text("SIGHTINGS", bold=True)
            curr_y += 5
            if not report.get('friendly_adjacent') and not report.get('enemy_adjacent'):
                draw_text("No nearby units spotted.", color=DARK_GRAY)
            else:
                for f in report.get('friendly_adjacent', []):
                    draw_text(f"Ally: {f['count']} @{f['pos']}", color=BLUE)
                for e in report.get('enemy_adjacent', []):
                    draw_text(f"ENEMY: {e['count']} @{e['pos']}", color=RED)
            curr_y += 15
            
            # History Section
            draw_text("EVENT LOG", bold=True)
            curr_y += 5
            history = report.get('history', [])
            if not history:
                draw_text("No recent events logged.", color=DARK_GRAY)
            else:
                # Group history by turn
                history_by_turn = {}
                for h in history:
                    t = h['turn']
                    if t not in history_by_turn: history_by_turn[t] = []
                    history_by_turn[t].append(h)

                EVENT_COLORS = {
                    'spawn': (0, 150, 0),   # Green
                    'move_start': (100, 50, 150),  # Purple
                    'move_arrive': (100, 50, 150),
                    'split': (255, 165, 0),  # Orange
                    'merge': (255, 165, 0),
                    'combat': (139, 0, 0),  # Dark Red
                    'recruit_added': (0, 150, 0),
                    'ally_spotted': BLUE,
                    'enemy_spotted': RED,
                    'ally_move': BLUE,
                    'enemy_move': RED,
                    'ally_departure': BLUE,
                    'enemy_departure': RED,
                    'ally_arrival': BLUE,
                    'enemy_arrival': RED,
                }
                
                for t in sorted(history_by_turn.keys(), reverse=True):
                    draw_text(f"--- Turn {t} ---", color=DARK_GRAY)
                    for h in history_by_turn[t]:
                        e_type = h['type']
                        color = EVENT_COLORS.get(e_type, BLACK)
                        draw_text(f"[{e_type.upper()}] {h['details']}", color=color)
        
        self.screen.set_clip(None)

    def get_wrapped_lines(self, text, max_width, font):
        paragraphs = text.split('\n')
        all_lines = []
        for para in paragraphs:
            words = para.split(' ')
            line = ""
            for word in words:
                test_line = line + word + " "
                if font.size(test_line)[0] < max_width:
                    line = test_line
                else:
                    all_lines.append(line)
                    line = word + " "
            all_lines.append(line)
        return all_lines

    def draw(self):
        if self.ui_state == UIState.MAIN_MENU:
            self.draw_menu()
        elif self.ui_state == UIState.SETTINGS:
            self.draw_settings()
        elif self.ui_state == UIState.PLAYING:
            self.draw_gameplay()
        
        pygame.display.flip()

    def draw_menu(self):
        self.screen.fill(BLUE)
        title_surf = self.title_font.render("Don't Shoot the Messenger", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 150))
        self.screen.blit(title_surf, title_rect)
        
        subtitle_surf = self.font.render("A Pigeon-Based Strategy Game", True, WHITE)
        subtitle_rect = subtitle_surf.get_rect(center=(SCREEN_WIDTH//2, 210))
        self.screen.blit(subtitle_surf, subtitle_rect)
        
        for btn in self.menu_buttons:
            btn.draw(self.screen)

    def draw_settings(self):
        self.screen.fill(DARK_GRAY)
        title_surf = self.title_font.render("Settings", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 100))
        self.screen.blit(title_surf, title_rect)
        
        mode_info = f"Current Mode: {self.selected_mode} | Auto-Phase: {'ON' if self.automated_phases else 'OFF'}"
        info_surf = self.ui_font.render(mode_info, True, YELLOW)
        info_rect = info_surf.get_rect(center=(SCREEN_WIDTH//2, 180))
        self.screen.blit(info_surf, info_rect)
        
        for btn in self.settings_buttons:
            btn.draw(self.screen)

    def handle_menu_events(self, event):
        for i, btn in enumerate(self.menu_buttons):
            if btn.handle_event(event):
                if i == 0: # Start
                    self.start_new_game()
                elif i == 1: # Settings
                    self.ui_state = UIState.SETTINGS
                elif i == 2: # Quit
                    pygame.quit()
                    sys.exit()

    def handle_settings_events(self, event):
        for i, btn in enumerate(self.settings_buttons):
            if btn.handle_event(event):
                if i == 0: self.selected_mode = "God"
                elif i == 1: self.selected_mode = "Fog"
                elif i == 2: self.selected_mode = "Realistic"
                elif i == 3:
                    self.automated_phases = not self.automated_phases
                    self.settings_buttons[3].text = f"Phase: {'Auto' if self.automated_phases else 'Manual'}"
                elif i == 4:
                    # Cycle through available maps
                    if self.available_maps:
                        self.selected_map_index = (self.selected_map_index + 1) % len(self.available_maps)
                        self._rebuild_settings_buttons()
                elif i == 5:
                    self.toggle_fullscreen()
                elif i == 6: self.ui_state = UIState.MAIN_MENU

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        global SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT, GRID_OFFSET_X, GRID_OFFSET_Y
        
        if self.fullscreen:
            SCREEN_WIDTH = DESKTOP_WIDTH
            SCREEN_HEIGHT = DESKTOP_HEIGHT - 80
            # Removed NOFRAME to show window decorations (minimize/close buttons)
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        else:
            SCREEN_WIDTH = WINDOW_WIDTH
            SCREEN_HEIGHT = WINDOW_HEIGHT
            if 'SDL_VIDEO_WINDOW_POS' in os.environ:
                del os.environ['SDL_VIDEO_WINDOW_POS']
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
            
        # Re-calculate constants for both modes
        MAP_WIDTH = SCREEN_WIDTH - REPORT_PANEL_WIDTH
        MAP_HEIGHT = SCREEN_HEIGHT - BOTTOM_PANEL_HEIGHT
        GRID_OFFSET_X = (MAP_WIDTH - (GRID_SIZE * (CELL_SIZE + 20))) // 2
        GRID_OFFSET_Y = (MAP_HEIGHT - (GRID_SIZE * (CELL_SIZE + 20))) // 2
        
        # Rebuild UI elements for new dimensions
        button_w, button_h = 200, 50
        self.menu_buttons = [
            Button(SCREEN_WIDTH//2 - 100, 300, button_w, button_h, "Start Game", self.ui_font),
            Button(SCREEN_WIDTH//2 - 100, 370, button_w, button_h, "Settings", self.ui_font),
            Button(SCREEN_WIDTH//2 - 100, 440, button_w, button_h, "Quit", self.ui_font)
        ]
        self._rebuild_settings_buttons()

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.report_popup_visible:
                            self.report_popup_visible = False
                        else:
                            self.ui_state = UIState.MAIN_MENU
                        continue

                if self.ui_state == UIState.MAIN_MENU:
                    self.handle_menu_events(event)
                elif self.ui_state == UIState.SETTINGS:
                    self.handle_settings_events(event)
                if self.ui_state == UIState.PLAYING:
                    if not self.state.game_over:
                        # Handle text input events if context menu is visible
                        if self.context_menu.visible and self.context_menu.text_input:
                            if self.context_menu.text_input.handle_event(event):
                                # Enter was pressed in text input
                                for opt in self.context_menu.options:
                                    if opt.get("is_splitter"):
                                        val = self.context_menu.text_input.get_value()
                                        if val is not None:
                                            opt["amount"] = val
                                            # Trigger the move action
                                            cmd = opt["command"]
                                            data = opt["data"]
                                            self.state.send_pigeon_to_tile(self.state.turn, data[0], cmd, data[1], count=val)
                                            self.context_menu.hide()
                                            break

                        if event.type == pygame.MOUSEBUTTONDOWN:
                            if event.button == 1:  # Left click
                                # 1. Handle Report Popup
                                if self.report_popup_visible:
                                    if self.close_btn_rect.collidepoint(event.pos):
                                        self.report_popup_visible = False
                                    elif not self.popup_rect.collidepoint(event.pos):
                                        self.report_popup_visible = False
                                    continue # Consume click
                                
                                # 2. Handle Sidebar Click
                                if event.pos[0] > SCREEN_WIDTH - REPORT_PANEL_WIDTH:
                                    for rect, report in self.report_boxes:
                                        if rect.collidepoint(event.pos):
                                            self.report_popup_visible = True
                                            self.report_popup_content = report
                                            self.popup_scroll_offset = 0
                                            break
                                    continue

                                in_map_area = event.pos[0] < SCREEN_WIDTH - REPORT_PANEL_WIDTH and event.pos[1] < SCREEN_HEIGHT - BOTTOM_PANEL_HEIGHT
                                
                                if self.context_menu.visible:
                                    # Restriction: Only allow context menu actions in "Give Orders" phase
                                    if self.state.phases[self.state.current_phase_index] != "Give Orders":
                                        self.context_menu.hide()
                                        continue

                                    # Don't hide yet if we might transition to a sub-menu or interact with text input
                                    menu_result = self.context_menu.handle_click(event.pos, hide_automatically=False)
                                    if menu_result:
                                        if menu_result.get("prepare_split"):
                                            source_node, target_node = menu_result["data"]
                                            self.context_menu.show(event.pos, [
                                                {"label": f"Move All -> {target_node.name}", "command": "move_attack", "data": (source_node, target_node)},
                                                {"label": "Split & Move:", "command": "move_attack", "data": (source_node, target_node), "is_splitter": True, "amount": 10},
                                                {"label": "Cancel", "command": "hide"}
                                            ], target_node)
                                            continue
                                        
                                        # If it wasn't a transition, hide it now
                                        self.context_menu.hide()

                                        cmd = menu_result["command"]
                                        if cmd == "hide":
                                            self.context_menu.hide()
                                            continue

                                        data = menu_result.get("data")
                                        if cmd == "recruit":
                                            self.state.recruit_unit(self.state.turn)
                                        elif cmd == "report":
                                            self.state.send_pigeon_to_tile(self.state.turn, data, "report", None)
                                        elif cmd == "move_attack":
                                            source_node, target_node = data
                                            count = menu_result.get("amount")
                                            self.state.send_pigeon_to_tile(self.state.turn, source_node, "move_attack", target_node, count=count)
                                elif in_map_area:
                                    # Start drag for panning
                                    self.is_dragging = True
                                    self.drag_start_x = event.pos[0]
                                    self.drag_start_y = event.pos[1]
                                    self.camera_start_x = self.camera_x
                                    self.camera_start_y = self.camera_y
                                else:
                                    # Regular click outside map area dismisses menu
                                    self.context_menu.hide()

                            elif event.button == 3: # Right click
                                if self.report_popup_visible: continue
                                
                                # Clip mouse interaction to map area
                                if event.pos[0] < SCREEN_WIDTH - REPORT_PANEL_WIDTH and event.pos[1] < SCREEN_HEIGHT - BOTTOM_PANEL_HEIGHT:
                                    # Restriction: Only allow right-click context menu in "Give Orders" phase
                                    if self.state.phases[self.state.current_phase_index] != "Give Orders":
                                        continue
                                    
                                    node = self.get_node_at_mouse(event.pos)
                                    if node:
                                        options = []
                                        
                                        # Uniform commands for all tiles to maintain uncertainty
                                        options.append({"label": f"Send Report to {node.name}", "command": "report", "data": node})
                                        
                                        for neighbor in node.neighbors:
                                            options.append({
                                                "label": f"Order Move/Attack -> {neighbor.name}",
                                                "command": "move_attack",
                                                "prepare_split": True,
                                                "data": (node, neighbor)
                                            })
                                        
                                        # Recruitment if at castle (This is static info, so it's fine to show)
                                        castle = self.state.player_castle_node if self.state.turn == 0 else self.state.enemy_castle_node
                                        if node == castle:
                                            options.append({"label": "Recruit Soldier (10G)", "command": "recruit", "data": node})
                                        
                                        if options:
                                            self.context_menu.show(event.pos, options, node)
                                    else:
                                        self.context_menu.hide()
                            elif event.button == 4 or event.button == 5: # Scroll wheel
                                scroll_dir = -1 if event.button == 4 else 1 # Negative scroll for wheel up
                                
                                if self.report_popup_visible:
                                    self.popup_scroll_offset = max(0, self.popup_scroll_offset + scroll_dir * 30)
                                elif self.context_menu.visible:
                                    change = 1 if event.button == 4 else -1
                                    for opt in self.context_menu.options:
                                        if opt.get("is_splitter"):
                                            opt["amount"] = max(1, opt["amount"] + change)
                                            if self.context_menu.text_input:
                                                self.context_menu.text_input.set_text(str(opt["amount"]))
                                # Sidebar scroll
                                elif event.pos[0] > SCREEN_WIDTH - REPORT_PANEL_WIDTH:
                                    self.sidebar_scroll_offset = max(0, self.sidebar_scroll_offset + scroll_dir * 30)

                        if event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_SPACE:
                                self.state.end_turn()
                                self.context_menu.hide()
                                # Reset scroll when turn changes
                                self.sidebar_scroll_offset = 0
                        
                        # Handle mouse button release (stop dragging)
                        if event.type == pygame.MOUSEBUTTONUP:
                            if event.button == 1:
                                self.is_dragging = False
                        
                        # Handle mouse motion (panning)
                        if event.type == pygame.MOUSEMOTION:
                            if self.is_dragging and not self.report_popup_visible:
                                dx = event.pos[0] - self.drag_start_x
                                dy = event.pos[1] - self.drag_start_y
                                self.camera_x = self.camera_start_x + dx
                                self.camera_y = self.camera_start_y + dy

            self.draw()
            self.clock.tick(60)

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = Game()
    game.run()
