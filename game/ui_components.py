import pygame

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
DARK_GRAY = (100, 100, 100)
BLUE = (100, 100, 255)
RED = (255, 100, 100)
YELLOW = (255, 255, 100)
GREEN = (100, 255, 100)

class Button:
    def __init__(self, x, y, width, height, text, font, base_color=GRAY, hover_color=WHITE, text_color=BLACK):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.font = font
        self.base_color = base_color
        self.hover_color = hover_color
        self.text_color = text_color
        self.is_hovered = False

    def draw(self, screen):
        color = self.hover_color if self.is_hovered else self.base_color
        pygame.draw.rect(screen, color, self.rect)
        pygame.draw.rect(screen, BLACK, self.rect, 2)
        
        text_surf = self.font.render(self.text, True, self.text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.is_hovered:
                return True
        return False

class UnitCard:
    def __init__(self, x, y, width, height, unit, font, mask_info=False):
        self.rect = pygame.Rect(x, y, width, height)
        self.unit = unit
        self.font = font
        self.selected = False
        self.mask_info = mask_info
        
    def draw(self, screen):
        bg_color = WHITE if not self.selected else YELLOW
        pygame.draw.rect(screen, bg_color, self.rect)
        pygame.draw.rect(screen, BLACK, self.rect, 1)
        
        # Unit Info
        color = BLUE if self.unit.owner == 0 else RED
        pygame.draw.circle(screen, color, (self.rect.x + 25, self.rect.y + 25), 15)
        
        type_text = self.font.render(f"{self.unit.unit_type}", True, BLACK)
        screen.blit(type_text, (self.rect.x + 50, self.rect.y + 5))
        
        count_val = "?" if self.mask_info else self.unit.count
        count_text = self.font.render(f"Count: {count_val}", True, DARK_GRAY)
        screen.blit(count_text, (self.rect.x + 50, self.rect.y + 25))
        
        pos_val = "Unknown" if self.mask_info else f"({self.unit.node.x}, {self.unit.node.y})"
        pos_text = self.font.render(f"At {pos_val}", True, DARK_GRAY)
        screen.blit(pos_text, (self.rect.x + 50, self.rect.y + 45))

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.rect.collidepoint(event.pos):
                return True
        return False

class CommandPanel:
    def __init__(self, x, y, width, height, font):
        self.rect = pygame.Rect(x, y, width, height)
        self.font = font
        self.buttons = []
        self.visible = False
        
    def set_commands(self, commands):
        """commands is a list of dicts: {'label': str, 'command': str, 'data': any, 'cols': int}"""
        self.buttons = []
        self.visible = True
        padding = 10
        total_w = self.rect.width - 20
        curr_y = self.rect.y + 10
        
        # We'll process commands and layout them based on 'cols'
        i = 0
        while i < len(commands):
            cmd = commands[i]
            cols = cmd.get('cols', 1)
            
            if cols == 1:
                # Full width button
                btn = Button(self.rect.x + padding, curr_y, total_w, 25, cmd['label'], self.font)
                btn.cmd_data = cmd
                self.buttons.append(btn)
                curr_y += 28
                i += 1
            else:
                # Grid row (e.g. 3 columns)
                # Group commands that want the same column count
                row_cmds = []
                for j in range(cols):
                    if i + j < len(commands) and commands[i+j].get('cols', 1) == cols:
                        row_cmds.append(commands[i+j])
                
                btn_w = (total_w - (len(row_cmds)-1)*5) // cols
                for idx, row_cmd in enumerate(row_cmds):
                    btn_x = self.rect.x + padding + idx * (btn_w + 5)
                    btn = Button(btn_x, curr_y, btn_w, 25, row_cmd['label'], self.font)
                    btn.cmd_data = row_cmd
                    self.buttons.append(btn)
                
                curr_y += 28
                i += len(row_cmds)
            
    def draw(self, screen):
        if not self.visible: return
        pygame.draw.rect(screen, GRAY, self.rect)
        pygame.draw.rect(screen, BLACK, self.rect, 2)
        for btn in self.buttons:
            btn.draw(screen)
            
    def handle_event(self, event):
        if not self.visible: return None
        for btn in self.buttons:
            if btn.handle_event(event):
                return btn.cmd_data
        return None

class ScrollPanel:
    def __init__(self, x, y, width, height, title, font):
        self.rect = pygame.Rect(x, y, width, height)
        self.title = title
        self.font = font
        self.scroll_y = 0
        self.items = []
        
    def add_item(self, item):
        self.items.append(item)
        
    def draw(self, screen):
        pygame.draw.rect(screen, GRAY, self.rect)
        pygame.draw.rect(screen, BLACK, self.rect, 2)
        
        # Draw Title
        title_surf = self.font.render(self.title, True, BLACK)
        screen.blit(title_surf, (self.rect.x + 10, self.rect.y + 10))
        
        # Clip area for items
        clip_rect = pygame.Rect(self.rect.x, self.rect.y + 40, self.rect.width, self.rect.height - 45)
        
        # Create a surface to draw items on for simple clipping
        # For simplicity in this demo, we'll just draw them and check bounds
        for i, item in enumerate(self.items):
            item.rect.x = self.rect.x + 10
            item.rect.y = self.rect.y + 45 + i * (item.rect.height + 5) - self.scroll_y
            if clip_rect.contains(item.rect):
                item.draw(screen)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 4: # Scroll Up
                self.scroll_y = max(0, self.scroll_y - 20)
            elif event.button == 5: # Scroll Down
                self.scroll_y += 20
        
        for item in self.items:
            if item.handle_event(event):
                return item
        return None
