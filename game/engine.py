import math
import os
import random
from collections import deque
from .graph import create_grid, create_map_from_json
from .pigeon import Pigeon

class Unit:
    def __init__(self, owner, unit_type, node, count=10):
        self.owner = owner # 0 for player, 1 for enemy
        self.unit_type = unit_type
        self.node = node
        self.count = count # Number of soldiers in this unit stack
        self.has_moved = False
        self.pending_command = None # Command sent via pigeon
        
        # Travel state for multi-turn movement
        self.travel_target = None
        self.travel_remaining = 0
        self.travel_command = None # Store the command to execute on arrival (e.g. move_attack)

class GameState:
    def __init__(self, mode="God", automated_phases=True, map_name="default_3x3"):
        self.automated_phases = automated_phases
        self.map_name = map_name
        
        # Load map from JSON
        maps_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "maps")
        map_path = os.path.join(maps_dir, f"{map_name}.json")
        
        if os.path.exists(map_path):
            self.nodes, self.player_castle_node, self.enemy_castle_node = create_map_from_json(map_path)
        else:
            # Fallback to legacy grid
            self.nodes = create_grid(3, 3)
            self.player_castle_node = self.get_node(0, 0)
            self.enemy_castle_node = self.get_node(2, 2)
            self.player_castle_node.structure = "Castle"
            self.player_castle_node.structure_owner = 0
            self.enemy_castle_node.structure = "Castle"
            self.enemy_castle_node.structure_owner = 1
        
        self.units = []
        self.turn = 0  # 0 for player, 1 for enemy
        self.resources = [
            {"gold": 20, "food": 10, "stone": 10, "wood": 10},
            {"gold": 20, "food": 10, "stone": 10, "wood": 10}
        ]
        self.pigeons = []
        self.pigeon_limit = [1, 1]
        self.turn_count = 1
        self.reports = [[], []]  # Stores list of reports for each player
        
        # Phase Management
        self.phases = [
            "Information (Reports)",
            "Give Orders",
            "Order Give/Receive",
            "Pigeon Actions",
            "Unit Actions",
            "End of Turn"
        ]
        self.current_phase_index = 0
        self.process_reports_phase()
        self.advance_phase()
        
        # Game modes: "God", "Fog", "Realistic"
        self.mode = mode
        self.visible_nodes = [set(), set()]
        
        # Distribute some resources on the map (only on nodes without structures)
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

    def calculate_travel_time(self, source, target):
        """BFS to find shortest travel time between source and target."""
        if source == target:
            return 0
        
        visited = {source: 0}
        queue = deque([(source, 0)])
        
        while queue:
            node, time = queue.popleft()
            for neighbor in node.neighbors:
                travel = node.get_travel_time(neighbor)
                new_time = time + travel
                if neighbor == target:
                    return new_time
                if neighbor not in visited or visited[neighbor] > new_time:
                    visited[neighbor] = new_time
                    queue.append((neighbor, new_time))
        
        return 999  # Unreachable

    def send_pigeon(self, player_id, unit, command_type, data=None):
        active_pigeons = [p for p in self.pigeons if p.owner == player_id]
        if len(active_pigeons) < self.pigeon_limit[player_id]:
            source = self.player_castle_node if player_id == 0 else self.enemy_castle_node
            unit_travel_time = self.calculate_travel_time(source, unit.node)
            travel_time = math.ceil(unit_travel_time / 2)
            new_pigeon = Pigeon(player_id, source, unit.node, {"type": command_type, "data": data}, units=[unit])
            new_pigeon.turns_to_reach = travel_time
            new_pigeon.total_turns = travel_time
            self.pigeons.append(new_pigeon)
            return True
        return False

    def send_pigeon_to_tile(self, player_id, target_node, command_type, data, count=None):
        """Sends a pigeon to a specific tile to issue orders to any friendly units there."""
        active_pigeons = [p for p in self.pigeons if p.owner == player_id]
        if len(active_pigeons) < self.pigeon_limit[player_id]:
            source = self.player_castle_node if player_id == 0 else self.enemy_castle_node
            unit_travel_time = self.calculate_travel_time(source, target_node)
            travel_time = math.ceil(unit_travel_time / 2)
            command = {"type": command_type, "data": data}
            if count is not None:
                command["count"] = count
            new_pigeon = Pigeon(player_id, source, target_node, command, units=[])
            new_pigeon.turns_to_reach = travel_time
            new_pigeon.total_turns = travel_time
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
        if command["type"] == "move_attack":
            target_node = command["data"]
            if target_node in unit.node.neighbors:
                requested_count = command.get("count", unit.count)
                move_count = min(requested_count, unit.count)
                if move_count <= 0: return None

                # Handle Split
                if move_count < unit.count:
                    # Create detachment
                    moving_unit = Unit(unit.owner, unit.unit_type, unit.node, count=move_count)
                    unit.count -= move_count
                    self.units.append(moving_unit)
                else:
                    moving_unit = unit

                # Initiate multi-turn travel
                travel_time = moving_unit.node.get_travel_time(target_node)
                moving_unit.travel_target = target_node
                moving_unit.travel_remaining = travel_time
                moving_unit.travel_command = command
                
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

    def finalize_move_attack(self, moving_unit):
        """Actually performs the move/attack logic once travel is finished"""
        if moving_unit not in self.units:
            return

        target_node = moving_unit.travel_target
        enemies = [u for u in self.get_units_at(target_node) if u.owner != moving_unit.owner]
        
        if not enemies:
            # Empty tile - just move
            moving_unit.node = target_node
            # Merge with existing friendly units at target
            friendlies = [u for u in self.get_units_at(target_node) if u.owner == moving_unit.owner and u != moving_unit]
            if friendlies:
                friendlies[0].count += moving_unit.count
                if moving_unit in self.units:
                    self.units.remove(moving_unit)
        else:
            # Enemy present - attack (All units at source fight, but only survivors continue)
            self.resolve_combat(moving_unit.node, target_node)
            
            # Check if the moving detachment survived
            if moving_unit in self.units:
                remaining_enemies = [u for u in self.get_units_at(target_node) if u.owner != moving_unit.owner]
                if not remaining_enemies:
                    # All enemies defeated - move in
                    moving_unit.node = target_node
                    friendlies = [u for u in self.get_units_at(target_node) if u.owner == moving_unit.owner and u != moving_unit]
                    if friendlies:
                        friendlies[0].count += moving_unit.count
                        if moving_unit in self.units:
                            self.units.remove(moving_unit)
        
        # Clear travel state
        moving_unit.travel_target = None
        moving_unit.travel_remaining = 0
        moving_unit.travel_command = None

    def advance_phase(self):
        """Advances the game to the next phase. Returns True if turn ended."""
        self.current_phase_index += 1
        
        if self.current_phase_index >= len(self.phases):
            self.current_phase_index = 0
            # If we reached the end of the turn process, we switch players
            # This is handled by process_end_of_turn
            return True
            
        # Execute phase logic
        phase = self.phases[self.current_phase_index]
        
        if phase == "Information (Reports)":
            self.process_reports_phase()
        elif phase == "Order Give/Receive":
            self.process_order_give_receive_phase()
        elif phase == "Pigeon Actions":
            self.process_pigeon_actions_phase()
        elif phase == "Unit Actions":
            self.process_unit_actions_phase()
        elif phase == "End of Turn":
            self.process_end_of_turn()
            
        return False

    def process_reports_phase(self):
        """Phase 1: Process returning pigeons that have already arrived at the castle"""
        for pigeon in self.pigeons[:]:
            if pigeon.owner == self.turn and pigeon.returning:
                if pigeon.arrived:
                    if pigeon.payload:
                        pigeon.payload['turn_received'] = self.turn_count
                        self.reports[pigeon.owner].append(pigeon.payload)
                    self.pigeons.remove(pigeon)

    def process_order_give_receive_phase(self):
        """Phase 3: Order Give/Receive - Dispatch new orders and units receive arrived ones"""
        # 1. Receive Arrived Orders
        for pigeon in self.pigeons:
            if pigeon.owner == self.turn and not pigeon.returning and pigeon.arrived and getattr(pigeon, 'dispatched', False):
                # Pigeon has arrived at unit from previous turn's travel, deliver now
                units_to_command = pigeon.units if pigeon.units else self.get_units_at(pigeon.target_node)
                friendly_units = [u for u in units_to_command if u.owner == pigeon.owner]
                
                if friendly_units:
                    for unit in friendly_units:
                        if unit in self.units:
                            unit.pending_command = pigeon.command
                else:
                    # No units found at target node
                    pigeon.payload = {
                        'position': (pigeon.target_node.x, pigeon.target_node.y),
                        'message': "No units found at destination to execute order",
                        'count': 0,
                        'friendly_adjacent': [],
                        'enemy_adjacent': []
                    }
                
                # Immediately prepare for return trip using halved path travel time
                unit_travel_back_time = self.calculate_travel_time(pigeon.target_node, pigeon.source_node)
                travel_back_time = math.ceil(unit_travel_back_time / 2)
                pigeon.returning = True
                pigeon.arrived = False
                pigeon.turns_to_reach = travel_back_time 
                pigeon.total_turns = travel_back_time
        
        # 2. Dispatch New Orders
        for pigeon in self.pigeons:
            if pigeon.owner == self.turn and not pigeon.returning and not getattr(pigeon, 'dispatched', False):
                pigeon.dispatched = True

    def process_pigeon_actions_phase(self):
        """Phase 4: Update movement for all dispatched pigeons (outward or returning)"""
        print(f"DEBUG: Processing Pigeon Actions for Turn {self.turn}")
        for pigeon in self.pigeons[:]:
            if pigeon.owner == self.turn and getattr(pigeon, 'dispatched', False):
                print(f"DEBUG: Pigeon {pigeon.owner} updating movement. Progress: {pigeon.get_progress():.2f}")
                pigeon.update()

    def process_unit_actions_phase(self):
        """Phase 5: Units execute their pending commands and progress their travel"""
        print(f"DEBUG: Processing Unit Actions for Turn {self.turn}")
        
        # 1. Start new actions for units with pending orders
        for unit in self.units:
            if unit.owner == self.turn and unit.pending_command:
                print(f"DEBUG: Unit {unit.owner} starting command {unit.pending_command['type']}")
                result = self.execute_command(unit, unit.pending_command)
                # If command was a report, find the pigeon that delivered it to store the result
                if result:
                    # Find any pigeon that just arrived at this unit's node and is returning
                    for pigeon in self.pigeons:
                        if pigeon.owner == unit.owner and pigeon.returning and pigeon.target_node == unit.node:
                            pigeon.payload = result
                
                unit.pending_command = None

        # 2. Progress travel for all units belonging to the current player
        # Use a list copy as finalize might remove units (merging or combat)
        current_units = [u for u in self.units if u.owner == self.turn]
        for unit in current_units:
            if unit.travel_remaining > 0:
                unit.travel_remaining -= 1
                print(f"DEBUG: Unit {unit.owner} travel progress. Remaining: {unit.travel_remaining}")
                if unit.travel_remaining == 0:
                    print(f"DEBUG: Unit {unit.owner} arrived at target!")
                    if unit.travel_command and unit.travel_command["type"] == "move_attack":
                        self.finalize_move_attack(unit)

    def process_end_of_turn(self):
        """Phase 6: Resource generation and turn transition"""
        # Resource Generation (Structures only)
        for node in self.nodes:
            if node.structure and node.structure_owner is not None:
                owner = node.structure_owner
                for res, amount in node.resources.items():
                    if amount > 0:
                        harvest = 5 
                        self.resources[owner][res] += harvest

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
        
        # Check win condition
        p1_at_enemy_castle = [u for u in self.get_units_at(self.enemy_castle_node) if u.owner == 0]
        p2_at_player_castle = [u for u in self.get_units_at(self.player_castle_node) if u.owner == 1]
        
        player_units = [u for u in self.units if u.owner == 0]
        enemy_units = [u for u in self.units if u.owner == 1]
        
        if p1_at_enemy_castle:
            self.game_over = True
            self.winner = 0
        elif p2_at_player_castle:
            self.game_over = True
            self.winner = 1
        elif not enemy_units and self.resources[1]["gold"] < 10 and self.turn_count > 10:
            self.game_over = True
            self.winner = 0
        elif not player_units and self.resources[0]["gold"] < 10 and self.turn_count > 10:
            self.game_over = True
            self.winner = 1
        
        # Reset phase for next player (they start at phase 0: Information)
        self.current_phase_index = 0
        self.process_reports_phase() # Process reports immediately for the new current player

    def end_turn(self):
        """Advances through phases. If automated_phases is True, loops until 'Give Orders'."""
        if self.automated_phases:
            while True:
                self.advance_phase()
                if self.phases[self.current_phase_index] == "Give Orders":
                    break
        else:
            self.advance_phase()

