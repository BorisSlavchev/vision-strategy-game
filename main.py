import pygame
import sys
from game.engine import GameState

# Constants
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
GRID_SIZE = 3
CELL_SIZE = 100
GRID_OFFSET_X = 250
GRID_OFFSET_Y = 150
NODE_RADIUS = 30

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
RED = (255, 100, 100)
BLUE = (100, 100, 255)
GREEN = (100, 255, 100)
YELLOW = (255, 255, 100)

class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Strategy Game")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 20)
        
        self.state = GameState()
        self.selected_unit = None

    def get_node_pos(self, node):
        x = GRID_OFFSET_X + node.x * CELL_SIZE + CELL_SIZE // 2
        y = GRID_OFFSET_Y + node.y * CELL_SIZE + CELL_SIZE // 2
        return x, y

    def get_node_at_mouse(self, pos):
        mx, my = pos
        for node in self.state.nodes:
            nx, ny = self.get_node_pos(node)
            dist = ((mx - nx)**2 + (my - ny)**2)**0.5
            if dist <= NODE_RADIUS:
                return node
        return None

    def draw(self):
        self.screen.fill(WHITE)
        
        # Draw connections
        for node in self.state.nodes:
            nx, ny = self.get_node_pos(node)
            for neighbor in node.neighbors:
                # Draw line to neighbor (only if neighbor index > node index to avoid double drawing)
                if neighbor.id > node.id:
                    nnx, nny = self.get_node_pos(neighbor)
                    pygame.draw.line(self.screen, BLACK, (nx, ny), (nnx, nny), 2)

        # Draw nodes
        for node in self.state.nodes:
            nx, ny = self.get_node_pos(node)
            color = GRAY
            if node == self.state.player_castle_node:
                color = BLUE
            elif node == self.state.enemy_castle_node:
                color = RED
            
            pygame.draw.circle(self.screen, color, (nx, ny), NODE_RADIUS)
            pygame.draw.circle(self.screen, BLACK, (nx, ny), NODE_RADIUS, 2)

        # Draw units
        for unit in self.state.units:
            nx, ny = self.get_node_pos(unit.node)
            color = BLUE if unit.owner == 0 else RED
            # Draw unit as a smaller circle inside the node
            pygame.draw.circle(self.screen, color, (nx, ny), NODE_RADIUS - 10)
            
            # Draw HP
            hp_text = self.font.render(str(unit.hp), True, WHITE)
            self.screen.blit(hp_text, (nx - 5, ny - 10))
            
            if unit == self.selected_unit:
                pygame.draw.circle(self.screen, YELLOW, (nx, ny), NODE_RADIUS - 5, 2)

        # Draw UI
        turn_text = f"Turn: {'Player (Blue)' if self.state.turn == 0 else 'Enemy (Red)'}"
        self.screen.blit(self.font.render(turn_text, True, BLACK), (10, 10))
        
        gold_text = f"Gold: P1(Blue): {self.state.gold[0]}  P2(Red): {self.state.gold[1]}"
        self.screen.blit(self.font.render(gold_text, True, BLACK), (10, 40))
        
        controls_text = "Controls: Click unit to select, Click neighbor to move/attack"
        self.screen.blit(self.font.render(controls_text, True, BLACK), (10, SCREEN_HEIGHT - 60))
        
        recruit_text = "Press 'R' to Recruit (Cost: 5)"
        self.screen.blit(self.font.render(recruit_text, True, BLACK), (10, SCREEN_HEIGHT - 30))
        
        end_turn_text = "Press 'SPACE' to End Turn"
        self.screen.blit(self.font.render(end_turn_text, True, BLACK), (300, SCREEN_HEIGHT - 30))

        if self.state.game_over:
            winner_text = f"GAME OVER! Winner: {'Player' if self.state.winner == 0 else 'Enemy'}"
            text_surf = self.font.render(winner_text, True, GREEN)
            self.screen.blit(text_surf, (SCREEN_WIDTH//2 - 100, SCREEN_HEIGHT//2))

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
                            node = self.get_node_at_mouse(event.pos)
                            if node:
                                unit = self.state.get_unit_at(node)
                                if self.selected_unit:
                                    # Try to move
                                    if self.state.move_unit(self.selected_unit, node):
                                        self.selected_unit = None
                                    elif unit and unit.owner == self.state.turn:
                                        # Select new unit
                                        self.selected_unit = unit
                                    else:
                                        # Deselect
                                        self.selected_unit = None
                                elif unit and unit.owner == self.state.turn:
                                    # Select unit
                                    self.selected_unit = unit
                    
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_r:
                            self.state.recruit_unit(self.state.turn)
                        elif event.key == pygame.K_SPACE:
                            self.state.end_turn()
                            self.selected_unit = None

            self.draw()
            self.clock.tick(60)

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = Game()
    game.run()
