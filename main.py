import pygame
import sys
from game.engine import GameState

# Constants
SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 800
GRID_SIZE = 3
CELL_SIZE = 120
GRID_OFFSET_X = 350
GRID_OFFSET_Y = 200
NODE_RADIUS = 50

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
        width = max(self.font.size(opt["label"])[0] for opt in self.options) + self.padding * 2
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
            
            text_surf = self.font.render(opt["label"], True, BLACK)
            screen.blit(text_surf, (self.pos[0] + self.padding, y + 5))
            
    def handle_click(self, pos):
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
        self.title_font = pygame.font.SysFont("Arial", 28, bold=True)
        
        self.state = GameState(mode="God") # Start in God mode to see pigeons
        self.selected_unit = None
        self.mode_options = ["God", "Fog", "Realistic"]
        self.context_menu = ContextMenu(self.font)

    def get_node_pos(self, node):
        x = GRID_OFFSET_X + node.x * (CELL_SIZE + 20) + CELL_SIZE // 2
        y = GRID_OFFSET_Y + node.y * (CELL_SIZE + 20) + CELL_SIZE // 2
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
        player_visibility = self.state.visible_nodes[self.state.turn]
            
        for pigeon in self.state.pigeons:
            # Visibility check for pigeons
            is_visible = self.state.mode == "God" or pigeon.owner == 0
            if not is_visible:
                # Check if pigeon is near a visible node
                if pigeon.source_node in player_visibility or pigeon.target_node in player_visibility:
                    is_visible = True
            
            if not is_visible:
                continue

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

    def draw(self):
        self.screen.fill(WHITE)
        
        player_visibility = self.state.visible_nodes[self.state.turn] # Show what current player sees

        # Draw connections
        for node in self.state.nodes:
            if node not in player_visibility and self.state.mode != "God":
                continue
            nx, ny = self.get_node_pos(node)
            for neighbor in node.neighbors:
                if neighbor.id > node.id:
                    if neighbor not in player_visibility and self.state.mode != "God":
                        continue
                    nnx, nny = self.get_node_pos(neighbor)
                    pygame.draw.line(self.screen, BLACK, (nx, ny), (nnx, nny), 1)

        # Draw nodes
        for node in self.state.nodes:
            nx, ny = self.get_node_pos(node)
            
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
                self.screen.blit(s_text, (nx - 5, ny - 25))

            # Draw resources
            res_str = ""
            for r, amt in node.resources.items():
                if amt > 0:
                    res_str += f"{r[0].upper()}:{amt} "
            if res_str:
                res_surf = self.font.render(res_str.strip(), True, DARK_GRAY)
                self.screen.blit(res_surf, (nx - 20, ny + 35))

        # Draw units
        for unit in self.state.units:
            if unit.node not in player_visibility and self.state.mode != "God":
                continue
                
            nx, ny = self.get_node_pos(unit.node)
            color = BLUE if unit.owner == 0 else RED
            
            pygame.draw.circle(self.screen, color, (nx, ny), NODE_RADIUS - 10)
            
            # Show unit count
            count_text = self.font.render(str(unit.count), True, WHITE)
            self.screen.blit(count_text, (nx - 10, ny - 10))
            
            if unit == self.selected_unit:
                pygame.draw.circle(self.screen, YELLOW, (nx, ny), NODE_RADIUS - 5, 2)

        # Draw pigeons (in God mode)
        self.draw_pigeons()

        # Draw UI Sidebar
        pygame.draw.rect(self.screen, GRAY, (0, 0, 250, SCREEN_HEIGHT))
        pygame.draw.line(self.screen, BLACK, (250, 0), (250, SCREEN_HEIGHT), 2)
        
        self.screen.blit(self.title_font.render("Strategy Game", True, BLACK), (10, 10))
        
        mode_text = f"Mode: {self.state.mode}"
        self.screen.blit(self.font.render(mode_text, True, BLACK), (10, 50))
        
        turn_text = f"Turn: {'Player (Blue)' if self.state.turn == 0 else 'Enemy (Red)'}"
        self.screen.blit(self.font.render(turn_text, True, BLUE if self.state.turn == 0 else RED), (10, 80))
        
        # Resources UI
        res_y = 120
        self.screen.blit(self.font.render("Resources:", True, BLACK), (10, res_y))
        res_y += 25
        res = self.state.resources[self.state.turn]
        for r_name, r_amt in res.items():
            self.screen.blit(self.font.render(f"{r_name.capitalize()}: {r_amt}", True, BLACK), (20, res_y))
            res_y += 20
            
        # Pigeons UI
        pigeon_y = 250
        active_pigeons = [p for p in self.state.pigeons if p.owner == self.state.turn]
        self.screen.blit(self.font.render(f"Pigeons: {len(active_pigeons)}/{self.state.pigeon_limit[self.state.turn]}", True, BLACK), (10, pigeon_y))
        pigeon_y += 25
        for i, p in enumerate(active_pigeons):
            status = "Returning" if p.returning else f"Traveling ({p.turns_to_reach} turns)"
            self.screen.blit(self.font.render(f"P{i+1}: {p.command['type']} -> {status}", True, DARK_GRAY), (20, pigeon_y))
            pigeon_y += 20

        # Controls
        ctrl_y = 450
        controls = [
            "L-Click: Select/Deselect unit",
            "R-Click on node: Command menu",
            "R: Recruit Soldier (10 Gold)",
            "SPACE: End Turn",
            "M: Cycle Game Mode"
        ]
        self.screen.blit(self.font.render("Controls:", True, BLACK), (10, ctrl_y))
        for ctrl in controls:
            ctrl_y += 20
            self.screen.blit(self.font.render(ctrl, True, BLACK), (10, ctrl_y))

        if self.state.game_over:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            self.screen.blit(overlay, (0,0))
            winner_text = f"GAME OVER! Winner: {'Player' if self.state.winner == 0 else 'Enemy'}"
            text_surf = self.title_font.render(winner_text, True, GREEN)
            self.screen.blit(text_surf, (SCREEN_WIDTH//2 - 150, SCREEN_HEIGHT//2))

        # Draw context menu on top
        self.context_menu.draw(self.screen)

        pygame.display.flip()

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                if not self.state.game_over:
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if event.button == 1: # Left click
                            # Check context menu first
                            menu_result = self.context_menu.handle_click(event.pos)
                            if menu_result:
                                # Execute the command from menu
                                cmd_type = menu_result["command"]
                                cmd_data = menu_result.get("data")
                                
                                if cmd_type == "recruit":
                                    self.state.recruit_unit(self.state.turn)
                                elif cmd_type == "end_turn":
                                    self.state.end_turn()
                                    self.selected_unit = None
                                elif cmd_type == "cycle_mode":
                                    curr_idx = self.mode_options.index(self.state.mode)
                                    self.state.mode = self.mode_options[(curr_idx + 1) % len(self.mode_options)]
                                    self.state.update_visibility()
                                elif cmd_type == "recall_pigeon":
                                    if cmd_data in self.state.pigeons:
                                        self.state.pigeons.remove(cmd_data)
                                elif cmd_type == "info":
                                    pass # Just a label for now
                                elif self.selected_unit:
                                    self.state.send_pigeon(self.state.turn, self.selected_unit, cmd_type, cmd_data)
                                    self.selected_unit = None
                            elif not self.context_menu.visible:
                                node = self.get_node_at_mouse(event.pos)
                                if node:
                                    units_here = self.state.get_units_at(node)
                                    friendly_units = [u for u in units_here if u.owner == self.state.turn]
                                    
                                    if friendly_units:
                                        self.selected_unit = friendly_units[0]
                                    else:
                                        self.selected_unit = None
                                else:
                                    self.selected_unit = None
                            else:
                                self.context_menu.hide()
                                
                        elif event.button == 3: # Right click
                            self.context_menu.hide()
                            node = self.get_node_at_mouse(event.pos)
                            
                            if node:
                                options = []
                                units_here = self.state.get_units_at(node)
                                friendly_units = [u for u in units_here if u.owner == self.state.turn]
                                
                                # 1. If right-clicking on a friendly unit, select it and show basic options?
                                # Or if already selected, show unit-specific actions.
                                if friendly_units:
                                    self.selected_unit = friendly_units[0]
                                    options.append({"label": f"Unit at ({node.x}, {node.y})", "command": "info", "data": None})
                                    if node.structure == "Castle":
                                        options.append({"label": "Recruit Soldier (10 Gold)", "command": "recruit", "data": node})
                                    
                                    # If selected unit is on this node, show local actions
                                    if self.selected_unit.node == node:
                                        if node.structure is None:
                                            options.append({"label": "Build Outpost", "command": "build", "data": None})
                                        options.append({"label": "Report Info", "command": "report", "data": None})

                                # 2. If right-clicking on a DIFFERENT node while unit is selected
                                elif self.selected_unit and node != self.selected_unit.node:
                                    if node in self.selected_unit.node.neighbors:
                                        options.append({
                                            "label": f"Move to ({node.x}, {node.y})",
                                            "command": "move",
                                            "data": node
                                        })
                                        options.append({
                                            "label": f"Attack at ({node.x}, {node.y})",
                                            "command": "attack",
                                            "data": node
                                        })
                                
                                # 3. Node-specific actions
                                if node.structure == "Castle" and node == (self.state.player_castle_node if self.state.turn == 0 else self.state.enemy_castle_node):
                                    if not any(opt["command"] == "recruit" for opt in options):
                                        options.append({"label": "Recruit Soldier (10 Gold)", "command": "recruit", "data": node})

                                if options:
                                    self.context_menu.show(event.pos, options, node)
                                    
                            # 4. Check for pigeons
                            else:
                                pigeon_clicked = None
                                for pigeon in self.state.pigeons:
                                    if pigeon.owner != self.state.turn: continue
                                    
                                    progress = pigeon.get_progress()
                                    start_pos = self.get_node_pos(pigeon.target_node if pigeon.returning else pigeon.source_node)
                                    end_pos = self.get_node_pos(pigeon.source_node if pigeon.returning else pigeon.target_node)
                                    
                                    curr_x = start_pos[0] + (end_pos[0] - start_pos[0]) * progress
                                    curr_y = start_pos[1] + (end_pos[1] - start_pos[1]) * progress
                                    
                                    dist = ((event.pos[0] - curr_x)**2 + ((event.pos[1] - curr_y)**2))**0.5
                                    if dist < 15:
                                        pigeon_clicked = pigeon
                                        break
                                
                                if pigeon_clicked:
                                    options = []
                                    options.append({"label": f"Pigeon: {pigeon_clicked.command['type']}", "command": "info", "data": None})
                                    options.append({"label": "Recall Pigeon", "command": "recall_pigeon", "data": pigeon_clicked})
                                    self.context_menu.show(event.pos, options, None)
                                else:
                                    # Global actions if clicking elsewhere
                                    options = []
                                    options.append({"label": f"End Turn ({'Player' if self.state.turn == 0 else 'Enemy'})", "command": "end_turn", "data": None})
                                    options.append({"label": f"Cycle Mode (Current: {self.state.mode})", "command": "cycle_mode", "data": None})
                                    self.context_menu.show(event.pos, options, None)
                    
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_r:
                            self.state.recruit_unit(self.state.turn)
                        elif event.key == pygame.K_SPACE:
                            self.state.end_turn()
                            self.selected_unit = None
                            self.context_menu.hide()
                        elif event.key == pygame.K_m:
                            # Cycle mode
                            curr_idx = self.mode_options.index(self.state.mode)
                            self.state.mode = self.mode_options[(curr_idx + 1) % len(self.mode_options)]
                            self.state.update_visibility()

            self.draw()
            self.clock.tick(60)

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = Game()
    game.run()
