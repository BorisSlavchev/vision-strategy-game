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
SCREEN_WIDTH = 1100
SCREEN_HEIGHT = 800
GRID_SIZE = 3
CELL_SIZE = 80
LEFT_PANEL_WIDTH = 250
REPORT_PANEL_WIDTH = 300
MAP_WIDTH = SCREEN_WIDTH - LEFT_PANEL_WIDTH - REPORT_PANEL_WIDTH
GRID_OFFSET_X = LEFT_PANEL_WIDTH + (MAP_WIDTH - (GRID_SIZE * (CELL_SIZE + 20))) // 2
GRID_OFFSET_Y = 150
NODE_RADIUS = 30

from enum import Enum
class UIState(Enum):
    MAIN_MENU = 1
    SETTINGS = 2
    PLAYING = 3
    GAMEOVER = 4

from game.ui_components import Button

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
        
    def show(self, pos, options, target_node):
        self.visible = True
        self.pos = pos
        self.options = options
        self.target_node = target_node
        
    def hide(self):
        self.visible = False
        self.options = []
        self.target_node = None
        
    def get_rect(self):
        if not self.options:
            return pygame.Rect(0, 0, 0, 0)
        
        def get_label(opt):
            label = opt["label"]
            if opt.get("is_splitter"):
                label = f"{opt['label']} {opt.get('amount', 0)} (Scroll to adjust)"
            return label

        width = max(self.font.size(get_label(opt))[0] for opt in self.options) + self.padding * 2
        height = len(self.options) * self.option_height
        return pygame.Rect(self.pos[0], self.pos[1], width, height)
    
    def draw(self, screen):
        if not self.visible or not self.options:
            return
        
        rect = self.get_rect()
        pygame.draw.rect(screen, WHITE, rect)
        pygame.draw.rect(screen, BLACK, rect, 2)
        
        for i, opt in enumerate(self.options):
            y = self.pos[1] + i * self.option_height
            opt_rect = pygame.Rect(self.pos[0], y, rect.width, self.option_height)
            
            # Highlight on hover
            if opt_rect.collidepoint(pygame.mouse.get_pos()):
                pygame.draw.rect(screen, GRAY, opt_rect)
            
            label = opt["label"]
            if opt.get("is_splitter"):
                label = f"{opt['label']} {opt.get('amount', 0)} (Scroll to adjust)"
            
            text_surf = self.font.render(label, True, BLACK)
            screen.blit(text_surf, (self.pos[0] + self.padding, y + 5))
            
    def handle_click(self, pos, hide_automatically=True):
        if not self.visible:
            return None
        
        rect = self.get_rect()
        if not rect.collidepoint(pos):
            self.hide()
            return None
        
        for i, opt in enumerate(self.options):
            y = self.pos[1] + i * self.option_height
            opt_rect = pygame.Rect(self.pos[0], y, rect.width, self.option_height)
            if opt_rect.collidepoint(pos):
                result = opt
                if hide_automatically:
                    self.hide()
                return result
        
        self.hide()
        return None


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
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
        """Rebuild settings buttons with current map name."""
        button_w, button_h = 200, 50
        map_name = self.available_maps[self.selected_map_index] if self.available_maps else "none"
        self.settings_buttons = [
            Button(SCREEN_WIDTH//2 - 100, 200, button_w, button_h, "Mode: God", self.font),
            Button(SCREEN_WIDTH//2 - 100, 260, button_w, button_h, "Mode: Fog", self.font),
            Button(SCREEN_WIDTH//2 - 100, 320, button_w, button_h, "Mode: Realistic", self.font),
            Button(SCREEN_WIDTH//2 - 100, 380, button_w, button_h, "Phase: Auto", self.font),
            Button(SCREEN_WIDTH//2 - 100, 440, button_w, button_h, f"Map: {map_name}", self.font),
            Button(SCREEN_WIDTH//2 - 100, 520, button_w, button_h, "Back", self.ui_font)
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

        # Draw UI Sidebar (Left)
        pygame.draw.rect(self.screen, GRAY, (0, 0, LEFT_PANEL_WIDTH, SCREEN_HEIGHT))
        pygame.draw.line(self.screen, BLACK, (LEFT_PANEL_WIDTH, 0), (LEFT_PANEL_WIDTH, SCREEN_HEIGHT), 2)
        
        title_surf = pygame.font.SysFont("Arial", 22, bold=True).render("Kingdom Info", True, BLACK)
        self.screen.blit(title_surf, (10, 10))
        
        mode_text = f"Mode: {self.state.mode}"
        self.screen.blit(self.font.render(mode_text, True, BLACK), (10, 50))
        
        turn_text = f"Turn: {'Player (Blue)' if self.state.turn == 0 else 'Enemy (Red)'}"
        self.screen.blit(self.font.render(turn_text, True, BLUE if self.state.turn == 0 else RED), (10, 80))
        
        turn_count_text = f"Turn #: {self.state.turn_count}"
        self.screen.blit(self.font.render(turn_count_text, True, BLACK), (10, 110))
        
        # Phase Display
        phase_name = self.state.phases[self.state.current_phase_index]
        phase_surf = self.font.render(f"Phase: {phase_name}", True, PURPLE)
        self.screen.blit(phase_surf, (10, 140))
        
        # Resources UI
        res_y = 180
        self.screen.blit(self.font.render("Resources:", True, BLACK), (10, res_y))
        res_y += 25
        gold = self.state.gold[self.state.turn]
        self.screen.blit(self.font.render(f"Gold: {gold}", True, BLACK), (20, res_y))
        res_y += 20
            
        # Pigeons UI
        pigeon_y = 300
        active_pigeons = [p for p in self.state.pigeons if p.owner == self.state.turn]
        self.screen.blit(self.font.render(f"Pigeons: {len(active_pigeons)}/{self.state.pigeon_limit[self.state.turn]}", True, BLACK), (10, pigeon_y))
        pigeon_y += 25
        for i, p in enumerate(active_pigeons):
            status = "Returning" if p.returning else f"Traveling ({p.turns_to_reach} turns)"
            p_info = f"P{i+1}: {p.command['type']} -> {status}"
            self.screen.blit(self.font.render(p_info, True, DARK_GRAY), (20, pigeon_y))
            pigeon_y += 20
            
        # Controls Hint
        ctrl_y = 500
        controls = [
            "R-Click Tile: Issue Order",
            "SPACE: End Turn",
            "ESC: Main Menu"
        ]
        self.screen.blit(self.font.render("Quick Controls:", True, BLACK), (10, ctrl_y))
        for ctrl in controls:
            ctrl_y += 20
            self.screen.blit(self.font.render(ctrl, True, BLACK), (10, ctrl_y))

        # Draw Report Panel (Right)
        pygame.draw.rect(self.screen, GRAY, (SCREEN_WIDTH - REPORT_PANEL_WIDTH, 0, REPORT_PANEL_WIDTH, SCREEN_HEIGHT))
        pygame.draw.line(self.screen, BLACK, (SCREEN_WIDTH - REPORT_PANEL_WIDTH, 0), (SCREEN_WIDTH - REPORT_PANEL_WIDTH, SCREEN_HEIGHT), 2)
        
        report_header = f"{'Player' if self.state.turn == 0 else 'Enemy'} Reports"
        header_surf = self.ui_font.render(report_header, True, BLACK)
        self.screen.blit(header_surf, (SCREEN_WIDTH - REPORT_PANEL_WIDTH + 10, 10))
        
        # Draw accumulated reports for current player
        current_reports = self.state.reports[self.state.turn]
        report_y = 50
        
        # Helper for word wrapping
        def get_wrapped_lines(text, max_width, font):
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

        # Show newest at top
        for report in reversed(current_reports):
            # Header height + padding
            header_h = 25
            max_txt_w = REPORT_PANEL_WIDTH - 20
            
            # Calculate content height
            if 'message' in report:
                report_lines = get_wrapped_lines(report['message'], max_txt_w, self.font)
                content_h = len(report_lines) * 18
            else:
                num_sightings = len(report.get('friendly_adjacent', [])) + len(report.get('enemy_adjacent', []))
                content_h = 20 # Strength line
                if num_sightings > 0:
                    content_h += 20 # "Sightings" header (implied or just space)
                    content_h += num_sightings * 18
            
            box_h = max(60, header_h + content_h + 10)
            if report_y + box_h > SCREEN_HEIGHT: break
            
            box_rect = pygame.Rect(SCREEN_WIDTH - REPORT_PANEL_WIDTH + 5, report_y, REPORT_PANEL_WIDTH - 10, box_h)
            pygame.draw.rect(self.screen, WHITE, box_rect)
            pygame.draw.rect(self.screen, BLACK, box_rect, 1)
            
            y = report_y + 5
            x = SCREEN_WIDTH - REPORT_PANEL_WIDTH + 10
            max_txt_w = REPORT_PANEL_WIDTH - 20
            
            # Header: Turn and Pos
            turn_received = report.get('turn_received', '?')
            header_text = f"Turn {turn_received} | Pos: {report['position']}"
            if 'available_turn' in report:
                header_text += f" | Re-avail: {report['available_turn']}"
            self.screen.blit(pygame.font.SysFont("Arial", 14, bold=True).render(header_text, True, BLACK), (x, y))
            y += 20
            
            if 'message' in report:
                for line in report_lines:
                    self.screen.blit(self.font.render(line, True, RED), (x, y))
                    y += 18
            else:
                self.screen.blit(self.font.render(f"Strength: {report['count']}", True, BLACK), (x, y))
                y += 20
                
                # Sightings with vertex names
                for f in report.get('friendly_adjacent', []):
                    txt = f"Ally: {f['count']} @{f['pos']}"
                    self.screen.blit(self.font.render(txt, True, BLUE), (x, y))
                    y += 18
                for e in report.get('enemy_adjacent', []):
                    txt = f"ENEMY: {e['count']} @{e['pos']}"
                    self.screen.blit(self.font.render(txt, True, RED), (x, y))
                    y += 18
            
            report_y += box_h + 5

        # Draw context menu on top
        self.context_menu.draw(self.screen)

        if self.state.game_over:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            self.screen.blit(overlay, (0,0))
            winner_text = f"GAME OVER! Winner: {'Player' if self.state.winner == 0 else 'Enemy'}"
            text_surf = self.ui_font.render(winner_text, True, GREEN)
            self.screen.blit(text_surf, (SCREEN_WIDTH//2 - 150, SCREEN_HEIGHT//2))



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
                elif i == 5: self.ui_state = UIState.MAIN_MENU

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.ui_state = UIState.MAIN_MENU
                        continue

                if self.ui_state == UIState.MAIN_MENU:
                    self.handle_menu_events(event)
                elif self.ui_state == UIState.SETTINGS:
                    self.handle_settings_events(event)
                elif self.ui_state == UIState.PLAYING:
                    if not self.state.game_over:
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            if event.button == 1:  # Left click
                                # Check if in map area for potential drag start
                                in_map_area = LEFT_PANEL_WIDTH < event.pos[0] < SCREEN_WIDTH - REPORT_PANEL_WIDTH
                                
                                if self.context_menu.visible:
                                    # Restriction: Only allow context menu actions in "Give Orders" phase
                                    if self.state.phases[self.state.current_phase_index] != "Give Orders":
                                        self.context_menu.hide()
                                        continue

                                    # Don't hide yet if we might transition to a sub-menu
                                    menu_result = self.context_menu.handle_click(event.pos, hide_automatically=False)
                                    if menu_result:
                                        if menu_result.get("prepare_split"):
                                            source_node, target_node = menu_result["data"]
                                            self.context_menu.options = [
                                                {"label": f"Move All -> {target_node.name}", "command": "move_attack", "data": (source_node, target_node)},
                                                {"label": "Split & Move:", "command": "move_attack", "data": (source_node, target_node), "is_splitter": True, "amount": 10},
                                                {"label": "Cancel", "command": "hide"}
                                            ]
                                            # Keep menu visible for sub-options
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
                                # Clip mouse interaction to map area
                                if LEFT_PANEL_WIDTH < event.pos[0] < SCREEN_WIDTH - REPORT_PANEL_WIDTH:
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
                                if self.context_menu.visible:
                                    change = 1 if event.button == 4 else -1
                                    for opt in self.context_menu.options:
                                        if opt.get("is_splitter"):
                                            opt["amount"] = max(1, opt["amount"] + change)

                        if event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_SPACE:
                                self.state.end_turn()
                                self.context_menu.hide()
                        
                        # Handle mouse button release (stop dragging)
                        if event.type == pygame.MOUSEBUTTONUP:
                            if event.button == 1:
                                self.is_dragging = False
                        
                        # Handle mouse motion (panning)
                        if event.type == pygame.MOUSEMOTION:
                            if self.is_dragging:
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
