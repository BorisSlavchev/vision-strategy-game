from .graph import create_grid

class Unit:
    def __init__(self, owner, unit_type, node):
        self.owner = owner # 0 for player, 1 for enemy
        self.unit_type = unit_type
        self.node = node
        self.has_moved = False
        self.hp = 10
        self.attack = 3

class GameState:
    def __init__(self):
        self.nodes = create_grid(3, 3)
        self.units = []
        self.turn = 0 # 0 for player, 1 for enemy
        self.gold = [10, 10] # Player 0, Player 1
        self.turn_count = 1
        
        # Setup Castles
        self.player_castle_node = self.get_node(0, 0)
        self.enemy_castle_node = self.get_node(2, 2)
        
        self.game_over = False
        self.winner = None

    def get_node(self, x, y):
        for node in self.nodes:
            if node.x == x and node.y == y:
                return node
        return None

    def get_unit_at(self, node):
        for unit in self.units:
            if unit.node == node:
                return unit
        return None

    def recruit_unit(self, player_id):
        cost = 5
        if self.gold[player_id] >= cost:
            spawn_node = self.player_castle_node if player_id == 0 else self.enemy_castle_node
            if self.get_unit_at(spawn_node) is None:
                self.gold[player_id] -= cost
                new_unit = Unit(player_id, "Soldier", spawn_node)
                self.units.append(new_unit)
                return True
        return False

    def move_unit(self, unit, target_node):
        if unit.owner != self.turn:
            return False
        if unit.has_moved:
            return False
        if target_node not in unit.node.neighbors:
            return False
        
        target_unit = self.get_unit_at(target_node)
        
        if target_unit:
            if target_unit.owner != unit.owner:
                # Combat
                self.resolve_combat(unit, target_unit)
                unit.has_moved = True
                return True
            else:
                # Cannot move to friendly occupied node
                return False
        else:
            # Move
            unit.node = target_node
            unit.has_moved = True
            
            # Check win condition
            if unit.owner == 0 and unit.node == self.enemy_castle_node:
                self.game_over = True
                self.winner = 0
            elif unit.owner == 1 and unit.node == self.player_castle_node:
                self.game_over = True
                self.winner = 1
                
            return True

    def resolve_combat(self, attacker, defender):
        # Simple combat: Attacker deals damage first
        defender.hp -= attacker.attack
        if defender.hp <= 0:
            self.units.remove(defender)
            attacker.node = defender.node # Move into space
            
            # Check win condition after combat move
            if attacker.owner == 0 and attacker.node == self.enemy_castle_node:
                self.game_over = True
                self.winner = 0
            elif attacker.owner == 1 and attacker.node == self.player_castle_node:
                self.game_over = True
                self.winner = 1
        else:
            # Counter attack
            attacker.hp -= defender.attack
            if attacker.hp <= 0:
                self.units.remove(attacker)

    def end_turn(self):
        self.turn = 1 - self.turn
        if self.turn == 0:
            self.turn_count += 1
            # Income phase for both at start of round (or per turn? let's do per turn start for active player)
        
        # Give gold to the player whose turn it just became
        self.gold[self.turn] += 2
        
        # Reset movement
        for unit in self.units:
            if unit.owner == self.turn:
                unit.has_moved = False
