import random
from .graph import create_grid
from .pigeon import Pigeon

class Unit:
    def __init__(self, owner, unit_type, node, count=10):
        self.owner = owner # 0 for player, 1 for enemy
        self.unit_type = unit_type
        self.node = node
        self.count = count # Number of soldiers in this unit stack
        self.has_moved = False
        self.pending_command = None # Command sent via pigeon

class GameState:
    def __init__(self, mode="God"):
        self.grid_size = 3
        self.nodes = create_grid(self.grid_size, self.grid_size)
        self.units = []
        self.turn = 0 # 0 for player, 1 for enemy
        self.resources = [
            {"gold": 20, "food": 10, "stone": 10, "wood": 10},
            {"gold": 20, "food": 10, "stone": 10, "wood": 10}
        ]
        self.pigeons = []
        self.pigeon_limit = [1, 1] 
        self.turn_count = 1
        self.latest_report = [None, None] # Stores only the most recent report for each player
        
        # Game modes: "God", "Fog", "Realistic"
        self.mode = mode
        self.visible_nodes = [set(), set()] 
        
        # Setup Castles
        self.player_castle_node = self.get_node(0, 0)
        self.enemy_castle_node = self.get_node(2, 2)
        
        self.player_castle_node.structure = "Castle"
        self.player_castle_node.structure_owner = 0
        self.enemy_castle_node.structure = "Castle"
        self.enemy_castle_node.structure_owner = 1
        
        # Distribute some resources on the map
        for node in self.nodes:
            if node.structure is None and random.random() < 0.4:
                res_type = random.choice(["gold", "food", "stone", "wood"])
                node.resources[res_type] = random.randint(10, 30)

        self.game_over = False
        self.winner = None
        
        # Add starting units
        self.units.append(Unit(0, "Soldier", self.player_castle_node, count=10))
        self.units.append(Unit(1, "Soldier", self.enemy_castle_node, count=10))
        
        self.update_visibility()
        self.merge_units()

    def get_node(self, x, y):
        for node in self.nodes:
            if node.x == x and node.y == y:
                return node
        return None

    def get_units_at(self, node):
        return [unit for unit in self.units if unit.node == node]

    def get_unit_report(self, unit):
        """Returns dict with unit information for report display"""
        report = {
            'position': (unit.node.x, unit.node.y),
            'count': unit.count,
            'friendly_adjacent': [],
            'enemy_adjacent': []
        }
        
        for neighbor in unit.node.neighbors:
            units_at_neighbor = self.get_units_at(neighbor)
            for u in units_at_neighbor:
                info = {'pos': (neighbor.x, neighbor.y), 'count': u.count}
                if u.owner == unit.owner:
                    report['friendly_adjacent'].append(info)
                else:
                    report['enemy_adjacent'].append(info)
        
        return report

    def recruit_unit(self, player_id):
        cost = 10 
        if self.resources[player_id]["gold"] >= cost:
            spawn_node = self.player_castle_node if player_id == 0 else self.enemy_castle_node
            friendly_units = [u for u in self.get_units_at(spawn_node) if u.owner == player_id]
            
            if friendly_units:
                friendly_units[0].count += 10
            else:
                new_unit = Unit(player_id, "Soldier", spawn_node, count=10)
                self.units.append(new_unit)
            
            self.resources[player_id]["gold"] -= cost
            return True
        return False
    
    def merge_units(self):
        """Merges all units of the same owner on the same node"""
        for node in self.nodes:
            for owner in [0, 1]:
                units_here = [u for u in self.get_units_at(node) if u.owner == owner]
                if len(units_here) > 1:
                    total_count = sum(u.count for u in units_here)
                    # Keep the first unit, update its count, remove the others
                    main_unit = units_here[0]
                    main_unit.count = total_count
                    for extra_unit in units_here[1:]:
                        if extra_unit in self.units:
                            self.units.remove(extra_unit)

    def send_pigeon(self, player_id, unit, command_type, data=None):
        active_pigeons = [p for p in self.pigeons if p.owner == player_id]
        if len(active_pigeons) < self.pigeon_limit[player_id]:
            source = self.player_castle_node if player_id == 0 else self.enemy_castle_node
            # Target is the unit's current node (where the pigeon will find them)
            new_pigeon = Pigeon(player_id, source, unit.node, {"type": command_type, "data": data}, units=[unit])
            self.pigeons.append(new_pigeon)
            return True
        return False

    def resolve_combat(self, attacker_node, defender_node):
        """Pairwise duel system: Each unit pairs up against an enemy unit. Both roll d6."""
        attackers = [u for u in self.get_units_at(attacker_node)]
        defenders = [u for u in self.get_units_at(defender_node)]
        
        if not attackers or not defenders:
            return

        # Sum up total units on each side
        a_total = sum(u.count for u in attackers)
        d_total = sum(u.count for u in defenders)
        
        while a_total > 0 and d_total > 0:
            a_ready = a_total
            d_ready = d_total
            a_survivors = 0
            d_survivors = 0
            
            # 1. Main duels
            num_duels = min(a_ready, d_ready)
            a_ready -= num_duels
            d_ready -= num_duels
            
            for _ in range(num_duels):
                r_a = random.randint(1, 6)
                r_d = random.randint(1, 6)
                if r_a > r_d: # Attacker wins
                    a_survivors += 1
                    print(f"Duel Win: A({r_a}) vs D({r_d}) -> D unit lost")
                elif r_d > r_a: # Defender wins
                    d_survivors += 1
                    print(f"Duel Loss: A({r_a}) vs D({r_d}) -> A unit lost")
                else: # Tie
                    a_survivors += 1
                    d_survivors += 1
                    print(f"Duel Tie: A({r_a}) vs D({r_d}) -> Both survive")
            
            # 2. Extra units from A fight survivors of D
            if a_ready > 0 and d_survivors > 0:
                num_extra = min(a_ready, d_survivors)
                a_ready -= num_extra
                d_temp_survivors = 0
                for _ in range(num_extra):
                    r_a = random.randint(1, 6)
                    r_d = random.randint(1, 6)
                    if r_a > r_d: a_survivors += 1 # D survivor died
                    elif r_d > r_a: d_temp_survivors += 1 # A died
                    else: a_survivors += 1; d_temp_survivors += 1
                d_survivors = d_temp_survivors + (d_survivors - num_extra)

            # 3. Extra units from D fight survivors of A
            elif d_ready > 0 and a_survivors > 0:
                num_extra = min(d_ready, a_survivors)
                d_ready -= num_extra
                a_temp_survivors = 0
                for _ in range(num_extra):
                    r_a = random.randint(1, 6)
                    r_d = random.randint(1, 6)
                    if r_d > r_a: d_survivors += 1 # A survivor died
                    elif r_a > r_d: a_temp_survivors += 1 # D died
                    else: d_survivors += 1; a_temp_survivors += 1
                a_survivors = a_temp_survivors + (a_survivors - num_extra)
            
            # Any units that didn't fight at all because other side was fully engaged
            a_survivors += a_ready
            d_survivors += d_ready
            
            # Check for stagnation (no deaths in a round)
            if a_survivors == a_total and d_survivors == d_total:
                break
                
            a_total = a_survivors
            d_total = d_survivors

        # Update unit counts
        # This is a bit tricky with multiple unit stacks, so we distribute losses
        def distribute_count(unit_list, new_total):
            # Simple redistribution: wipe all and set the first one to new_total
            for u in unit_list:
                u.count = 0
            if unit_list and new_total > 0:
                unit_list[0].count = new_total
            
            # Remove empty stacks
            for u in unit_list[:]:
                if u.count <= 0:
                    if u in self.units: self.units.remove(u)

        distribute_count(attackers, a_total)
        distribute_count(defenders, d_total)

    def update_visibility(self):
        for p in range(2):
            self.visible_nodes[p].clear()
            castle = self.player_castle_node if p == 0 else self.enemy_castle_node
            self.visible_nodes[p].add(castle)
            
            if self.mode == "God":
                for node in self.nodes:
                    self.visible_nodes[p].add(node)
                continue
            
            if self.mode == "Realistic":
                # In realistic mode, only see buildings owned by the player
                for node in self.nodes:
                    if node.structure and node.structure_owner == p:
                        self.visible_nodes[p].add(node)
                continue
                
            # Fog mode: see units and their neighbors
            for unit in self.units:
                if unit.owner == p:
                    self.visible_nodes[p].add(unit.node)
                    for neighbor in unit.node.neighbors:
                        self.visible_nodes[p].add(neighbor)

    def execute_command(self, unit, command):
        if command["type"] == "move":
            target_node = command["data"]
            if target_node in unit.node.neighbors:
                # Blocking check: cannot move through or to enemy units
                enemies = [u for u in self.get_units_at(target_node) if u.owner != unit.owner]
                if not enemies:
                    unit.node = target_node
                    # Merge with existing friendly units at target
                    friendlies = [u for u in self.get_units_at(target_node) if u.owner == unit.owner and u != unit]
                    if friendlies:
                        friendlies[0].count += unit.count
                        if unit in self.units:
                            self.units.remove(unit)
        elif command["type"] == "attack":
            target_node = command["data"]
            if target_node in unit.node.neighbors:
                self.resolve_combat(unit.node, target_node)
        elif command["type"] == "build":
            if unit.node.structure is None:
                owner = unit.owner
                if self.resources[owner]["gold"] >= 20:
                    self.resources[owner]["gold"] -= 20
                    unit.node.structure = "Outpost"
                    unit.node.structure_owner = owner
        elif command["type"] == "report":
            return self.get_unit_report(unit)
        return None

    def end_turn(self):
        # Clear previous report for the player whose turn has ended
        self.latest_report[self.turn] = None
        
        # Update pigeons
        for pigeon in self.pigeons[:]:
            if pigeon.owner == self.turn:
                pigeon.update()
                if pigeon.arrived:
                    if not pigeon.returning:
                        # Pigeon arrived at unit, execute commands
                        for unit in pigeon.units:
                            if unit in self.units:
                                result = self.execute_command(unit, pigeon.command)
                                if result:
                                    pigeon.payload = result
                        pigeon.returning = True
                        pigeon.arrived = False
                        pigeon.turns_to_reach = 2 
                    else:
                        # Pigeon returned to castle, deliver report if any
                        if pigeon.payload:
                            self.latest_report[pigeon.owner] = pigeon.payload
                        self.pigeons.remove(pigeon)

        # Resource Generation (Structures only)
        for node in self.nodes:
            if node.structure and node.structure_owner is not None:
                owner = node.structure_owner
                for res, amount in node.resources.items():
                    if amount > 0:
                        harvest = 5 
                        self.resources[owner][res] += harvest
            # No manual unit harvest anymore

        # Base income
        self.resources[0]["gold"] += 5
        self.resources[1]["gold"] += 5

        # Merge units to clean up map
        self.merge_units()

        # Reset movement
        for unit in self.units:
            unit.has_moved = False

        self.turn = 1 - self.turn
        if self.turn == 0:
            self.turn_count += 1
        
        self.update_visibility()
        
        # Check win condition (Castle capture is the primary objective)
        p1_at_enemy_castle = [u for u in self.get_units_at(self.enemy_castle_node) if u.owner == 0]
        p2_at_player_castle = [u for u in self.get_units_at(self.player_castle_node) if u.owner == 1]
        
        player_units = [u for u in self.units if u.owner == 0]
        enemy_units = [u for u in self.units if u.owner == 1]
        
        # Player 0 wins
        if p1_at_enemy_castle:
            print("Player 1 (Blue) Wins! Castle captured.")
            self.game_over = True
            self.winner = 0
        # Player 1 wins
        elif p2_at_player_castle:
            print("Player 2 (Red) Wins! Castle captured.")
            self.game_over = True
            self.winner = 1
        # Wipe-out condition (only if no units AND no gold to recruit)
        elif not enemy_units and self.resources[1]["gold"] < 10 and self.turn_count > 10:
            print("Player 1 (Blue) Wins! Enemy kingdom collapsed.")
            self.game_over = True
            self.winner = 0
        elif not player_units and self.resources[0]["gold"] < 10 and self.turn_count > 10:
            print("Player 2 (Red) Wins! Player kingdom collapsed.")
            self.game_over = True
            self.winner = 1

