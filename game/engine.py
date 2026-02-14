import math
import os
import random
from collections import deque
from .graph import create_grid, create_map_from_json
from .pigeon import Pigeon
from .ai import create_ai

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

        # Event History
        self.history_log = []
        self.last_observed = {} # {node_id: {'count': count, 'owner': owner}}

    def log_event(self, event_type, turn, details):
        """Append a new event to the history log"""
        self.history_log.append({
            'type': event_type,
            'turn': turn,
            'details': details
        })

    def get_and_clear_log(self):
        """Returns the current log and empties it"""
        log = self.history_log[:]
        self.history_log = []
        return log

    def observe_surroundings(self, game_state):
        """Passively observe adjacent tiles and log changes, including movements between visible tiles"""
        if getattr(self, 'travel_remaining', 0) > 0:
            return

        # 1. Collect current counts for all neighbors
        observations = {} # {node_id: {owner: count}}
        for neighbor in self.node.neighbors:
            units_here = game_state.get_units_at(neighbor)
            visible_units = [u for u in units_here if getattr(u, 'travel_remaining', 0) == 0]
            current_counts = {}
            for u in visible_units:
                current_counts[u.owner] = current_counts.get(u.owner, 0) + u.count
            observations[neighbor.id] = current_counts

        # 2. Process changes per owner
        for owner in [0, 1]:
            owner_label = "Ally" if owner == self.owner else "ENEMY"
            departures = [] # (node_name, diff, remaining)
            arrivals = []   # (node_name, diff, total)
            
            for neighbor in self.node.neighbors:
                curr_count = observations[neighbor.id].get(owner, 0)
                prev_count = self.last_observed.get(neighbor.id, {}).get(owner, 0)
                
                if curr_count < prev_count:
                    departures.append((neighbor.name, prev_count - curr_count, curr_count))
                elif curr_count > prev_count:
                    arrivals.append((neighbor.name, curr_count - prev_count, curr_count))
                elif curr_count > 0 and prev_count == 0:
                    # This case handled by arrivals logic above, keeping as comment for clarity
                    pass

            # 3. Match movements between visible neighbors
            used_arrivals = set()
            used_departures = set()
            
            # Match exact counts first
            for i, (d_node, d_diff, d_rem) in enumerate(departures):
                for j, (a_node, a_diff, a_total) in enumerate(arrivals):
                    if j not in used_arrivals and d_diff == a_diff:
                        self.log_event(f"{owner_label.lower()}_move", game_state.turn_count,
                                     f"Observed {d_diff} {owner_label}s moving from {d_node} to {a_node}")
                        used_arrivals.add(j)
                        used_departures.add(i)
                        break
            
            # Log remaining departures
            for i, (d_node, d_diff, d_rem) in enumerate(departures):
                if i not in used_departures:
                    # Try to see if there's any arrival that could be a destination (even if partial)
                    possible_dest = [a[0] for j, a in enumerate(arrivals) if j not in used_arrivals]
                    dest_str = f" towards {possible_dest[0]}" if possible_dest else " into the fog"
                    remaining_str = f" ({d_rem} remain)" if d_rem > 0 else " (None remain)"
                    self.log_event(f"{owner_label.lower()}_departure", game_state.turn_count,
                                 f"Observed {d_diff} {owner_label}s leaving {d_node}{dest_str}{remaining_str}")

            # Log remaining arrivals
            for j, (a_node, a_diff, a_total) in enumerate(arrivals):
                if j not in used_arrivals:
                    self.log_event(f"{owner_label.lower()}_arrival", game_state.turn_count,
                                 f"Observed {a_diff} {owner_label}s arriving at {a_node} (Total: {a_total})")

        # 4. Update memory
        for neighbor in self.node.neighbors:
            self.last_observed[neighbor.id] = observations[neighbor.id]

class GameState:
    def __init__(self, mode="God", automated_phases=True, map_name="moba", ai_type="Balanced"):
        self.automated_phases = automated_phases
        self.map_name = map_name
        
        # AI Controller
        self.ai_controller = create_ai(ai_type)
        self.ai_type = ai_type
        
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
        self.turn = 0  # 0 for player, 1 for AI (used internally during phase processing)
        self.gold = [20, 20]
        self.pigeons = []
        self.pigeon_limit = [1, 1]
        self.turn_count = 1
        self.reports = [[], []]  # Reports only used for player (index 0)
        self.returned_pigeons = [] # Track pigeons that just returned this turn
        
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
        
        self.game_over = False
        self.winner = None
        
        # Add starting units
        u0 = Unit(0, "Soldier", self.player_castle_node, count=10)
        u0.log_event("spawn", 1, f"Initial deployment at {self.player_castle_node.name}")
        self.units.append(u0)
        
        u1 = Unit(1, "Soldier", self.enemy_castle_node, count=10)
        u1.log_event("spawn", 1, f"Initial deployment at {self.enemy_castle_node.name}")
        self.units.append(u1)
        
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
            'position': unit.node.name,
            'count': unit.count,
            'friendly_adjacent': [],
            'enemy_adjacent': [],
            'history': []
        }
        
        # Immediate sightings for the report UI (not logged to history here as history is polled next)
        for neighbor in unit.node.neighbors:
            units_at_neighbor = self.get_units_at(neighbor)
            for u in units_at_neighbor:
                info = {'pos': neighbor.name, 'count': u.count}
                if u.owner == unit.owner:
                    report['friendly_adjacent'].append(info)
                else:
                    report['enemy_adjacent'].append(info)
        
        report['history'] = unit.get_and_clear_log()
        return report

    def recruit_unit(self, player_id):
        cost = 10 
        if self.gold[player_id] >= cost:
            spawn_node = self.player_castle_node if player_id == 0 else self.enemy_castle_node
            friendly_units = [u for u in self.get_units_at(spawn_node) if u.owner == player_id]
            
            if friendly_units:
                friendly_units[0].count += 10
                friendly_units[0].log_event("recruit_added", self.turn_count, "10 reinforcements recruited")
            else:
                new_unit = Unit(player_id, "Soldier", spawn_node, count=10)
                new_unit.log_event("spawn", self.turn_count, f"Recruited at {spawn_node.name}")
                self.units.append(new_unit)
            
            self.gold[player_id] -= cost
            return True
        return False
    
    def merge_units(self):
        """Merges all units of the same owner on the same node"""
        for node in self.nodes:
            for owner in [0, 1]:
                # Only merge units that are not currently traveling
                units_here = [u for u in self.get_units_at(node) if u.owner == owner and (getattr(u, 'travel_remaining', 0) == 0)]
                if len(units_here) > 1:
                    total_count = sum(u.count for u in units_here)
                    # Keep the first unit, update its count, remove the others
                    main_unit = units_here[0]
                    main_unit.count = total_count
                    
                    # Merge history logs and track counts
                    merged_counts = []
                    for extra_unit in units_here[1:]:
                        merged_counts.append(str(extra_unit.count))
                        main_unit.history_log.extend(extra_unit.history_log)
                        if extra_unit in self.units:
                            self.units.remove(extra_unit)
                    
                    counts_str = ", ".join(merged_counts)
                    main_unit.log_event("merge", self.turn_count, f"Merged with {len(merged_counts)} groups ({counts_str}) at {node.name}. Total: {total_count}")

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
            travel_time = self.calculate_travel_time(source, unit.node)
            new_pigeon = Pigeon(player_id, source, unit.node, {"type": command_type, "data": data}, units=[unit])
            new_pigeon.turns_to_reach = travel_time
            new_pigeon.total_turns = travel_time
            self.pigeons.append(new_pigeon)
            self.create_dispatch_report(player_id, new_pigeon, unit.node)
            return True
        return False

    def send_pigeon_to_tile(self, player_id, target_node, command_type, data, count=None):
        """Sends a pigeon to a specific tile to issue orders to any friendly units there."""
        active_pigeons = [p for p in self.pigeons if p.owner == player_id]
        if len(active_pigeons) < self.pigeon_limit[player_id]:
            source = self.player_castle_node if player_id == 0 else self.enemy_castle_node
            travel_time = self.calculate_travel_time(source, target_node)
            command = {"type": command_type, "data": data}
            if count is not None:
                command["count"] = count
            new_pigeon = Pigeon(player_id, source, target_node, command, units=[])
            new_pigeon.turns_to_reach = travel_time
            new_pigeon.total_turns = travel_time
            self.pigeons.append(new_pigeon)
            self.create_dispatch_report(player_id, new_pigeon, target_node)
            return True
        return False

    def create_dispatch_report(self, player_id, pigeon, target_node):
        """Creates an instant mini-report when a pigeon is dispatched."""
        # Skip report generation for AI
        if player_id == 1:
            return
        
        # Even with distance 0, a pigeon takes at least 1 turn to deliver and 1 to return
        # due to the phase-based movement (update in Phase 4, deliver/return in Phase 3).
        effective_dist = max(1, pigeon.turns_to_reach)
        return_time = effective_dist * 2  # Outbound + return trip
        
        cmd_type = pigeon.command.get('type', 'unknown')
        source_tile = target_node.name
        
        lines = [f"Target: {source_tile}"]
        
        if cmd_type == 'move_attack':
            move_target = pigeon.command.get('data')
            target_tile = move_target.name if hasattr(move_target, 'name') else str(move_target)
            lines.append(f"Task: Move -> {target_tile}")
        elif cmd_type == 'report':
            lines.append(f"Task: Scouting")
        else:
            lines.append(f"Task: {cmd_type.title()}")
            
        report = {
            'position': target_node.name,
            'turn_sent': self.turn_count,
            'destination': target_node.name,
            'task': cmd_type,
            'available_turn': self.turn_count + return_time,
            'message': "\n".join(lines),
            'turn_received': self.turn_count  # Show immediately
        }
        self.reports[player_id].append(report)

    def resolve_combat(self, attackers, defenders):
        """Pairwise duel system: Each unit pairs up against an enemy unit. Both roll d6."""
        if not attackers or not defenders:
            return

        # Sum up total units on each side
        a_total = sum(u.count for u in attackers)
        d_total = sum(u.count for u in defenders)
        
        # Calculate overcrowding ratios
        # Any soldier from a stack > 100 suffers disadvantage (2d6 take lower)
        a_penalty_count = sum(u.count for u in attackers if u.count > 100)
        d_penalty_count = sum(u.count for u in defenders if u.count > 100)
        
        # Probabilistic ratios for the totals
        a_ratio = a_penalty_count / a_total if a_total > 0 else 0
        d_ratio = d_penalty_count / d_total if d_total > 0 else 0

        def get_combat_roll(ratio):
            if random.random() < ratio:
                # Overcrowding penalty: disadvantage (roll 2d6, take lower)
                return min(random.randint(1, 6), random.randint(1, 6))
            return random.randint(1, 6)

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
                r_a = get_combat_roll(a_ratio)
                r_d = get_combat_roll(d_ratio)
                if r_a > r_d: # Attacker wins
                    a_survivors += 1
                elif r_d > r_a: # Defender wins
                    d_survivors += 1
                else: # Tie
                    a_survivors += 1
                    d_survivors += 1
            
            # 2. Extra units from A fight survivors of D
            if a_ready > 0 and d_survivors > 0:
                num_extra = min(a_ready, d_survivors)
                a_ready -= num_extra
                d_temp_survivors = 0
                for _ in range(num_extra):
                    r_a = get_combat_roll(a_ratio)
                    r_d = get_combat_roll(d_ratio)
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
                    r_a = get_combat_roll(a_ratio)
                    r_d = get_combat_roll(d_ratio)
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
        def distribute_count(unit_list, new_total):
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

        # Log combat result
        for u in attackers:
            if u in self.units:
                u.log_event("combat", self.turn_count, f"Combat result: {u.count} survivors")
        for u in defenders:
            if u in self.units:
                u.log_event("combat", self.turn_count, f"Combat result: {u.count} survivors")

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
                
            # Fog mode: only see the vertex where the unit stands (no adjacent visibility)
            for unit in self.units:
                if unit.owner == p:
                    self.visible_nodes[p].add(unit.node)

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
                    # Do not copy history as it leads to duplication upon re-merge.
                    # The split event provides sufficient context.
                    
                    unit.count -= move_count
                    self.units.append(moving_unit)
                    
                    unit.log_event("split", self.turn_count, f"Detached {move_count} units for move to {target_node.name}")
                    moving_unit.log_event("split", self.turn_count, f"Detached from main force at {unit.node.name}")
                else:
                    moving_unit = unit

                # Initiate multi-turn travel
                travel_time = moving_unit.node.get_travel_time(target_node)
                moving_unit.travel_target = target_node
                moving_unit.travel_remaining = travel_time
                moving_unit.travel_command = command
                
                moving_unit.log_event("move_start", self.turn_count, f"Started move to {target_node.name} (ETA: {travel_time} turns)")
                
        elif command["type"] == "report":
            return self.get_unit_report(unit)
        return None

    def finalize_move_attack(self, moving_unit):
        """Actually performs the move/attack logic once travel is finished"""
        if moving_unit not in self.units:
            return

        target_node = moving_unit.travel_target
        moving_unit.log_event("move_arrive", self.turn_count, f"Arrived at {target_node.name}")

        # Only fight with enemies already at the target node (not those also traveling elsewhere)
        enemies = [u for u in self.get_units_at(target_node) if u.owner != moving_unit.owner and getattr(u, 'travel_remaining', 0) == 0]
        
        if not enemies:
            # Empty tile or only friendly/traveling units - just move in
            moving_unit.node = target_node
            # Merge with existing non-traveling friendly units at target
            friendlies = [u for u in self.get_units_at(target_node) if u.owner == moving_unit.owner and u != moving_unit and getattr(u, 'travel_remaining', 0) == 0]
            if friendlies:
                old_count = friendlies[0].count
                friendlies[0].count += moving_unit.count
                # Merge history logs
                friendlies[0].history_log.extend(moving_unit.history_log)
                friendlies[0].log_event("merge", self.turn_count, f"Merged {moving_unit.count} arriving soldiers with {old_count} stationed at {target_node.name}")
                if moving_unit in self.units:
                    self.units.remove(moving_unit)
        else:
            # Enemy present - attack
            moving_unit.log_event("enemy_spotted", self.turn_count, f"Engaged enemy at {target_node.name}")
            # Only the arriving unit fights (plus any non-traveling allies already at target)
            allies_at_target = [u for u in self.get_units_at(target_node) if u.owner == moving_unit.owner and getattr(u, 'travel_remaining', 0) == 0]
            attackers = [moving_unit] + allies_at_target
            self.resolve_combat(attackers, enemies)
            
            # Check if any attackers survived and enemies are cleared
            if moving_unit in self.units or any(u in self.units for u in allies_at_target):
                remaining_enemies = [u for u in self.get_units_at(target_node) if u.owner != moving_unit.owner and getattr(u, 'travel_remaining', 0) == 0]
                if not remaining_enemies:
                    # All enemies defeated - move in if survived
                    if moving_unit in self.units:
                        moving_unit.node = target_node
                        # Final check for merge after moving in
                        friendlies = [u for u in self.get_units_at(target_node) if u.owner == moving_unit.owner and u != moving_unit and getattr(u, 'travel_remaining', 0) == 0]
                        if friendlies:
                            old_count = friendlies[0].count
                            friendlies[0].count += moving_unit.count
                            friendlies[0].history_log.extend(moving_unit.history_log)
                            friendlies[0].log_event("merge", self.turn_count, f"Merged {moving_unit.count} battle survivors with {old_count} stationed at {target_node.name}")
                            if moving_unit in self.units:
                                self.units.remove(moving_unit)
        
        # Clear travel state if unit still exists
        for u in self.units:
            if u == moving_unit:
                u.travel_target = None
                u.travel_remaining = 0
                u.travel_command = None

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
        self.returned_pigeons = []
        for pigeon in self.pigeons[:]:
            if pigeon.owner == self.turn and pigeon.returning:
                if pigeon.arrived:
                    # Only generate reports for player, skip for AI
                    if pigeon.owner == 0 and pigeon.payload:
                        pigeon.payload['turn_received'] = self.turn_count
                        self.reports[pigeon.owner].append(pigeon.payload)
                    self.returned_pigeons.append(pigeon)
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
                        'position': pigeon.target_node.name,
                        'message': "No units found at destination to execute order",
                        'count': 0,
                        'friendly_adjacent': [],
                        'enemy_adjacent': []
                    }
                
                # Immediately prepare for return trip using full path travel time (same as units)
                travel_back_time = self.calculate_travel_time(pigeon.target_node, pigeon.source_node)
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
        """Phase 6: Resource generation and end-of-side processing"""
        # Base income (both sides get income once per full turn)
        if self.turn == 0:
            self.gold[0] += 5
            self.gold[1] += 3 # AI generates 3 gold instead of 5

        # Only player units passively observe (AI has full vision)
        if self.turn == 0:
            for unit in self.units:
                if unit.owner == 0:
                    unit.observe_surroundings(self)

        # Merge units to clean up map
        self.merge_units()

        # Reset movement
        for unit in self.units:
            if unit.owner == self.turn:
                unit.has_moved = False

    def _check_win_condition(self):
        """Check if the game has been won by either side."""
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
        elif not enemy_units and self.gold[1] < 10 and self.turn_count > 10:
            self.game_over = True
            self.winner = 0
        elif not player_units and self.gold[0] < 10 and self.turn_count > 10:
            self.game_over = True
            self.winner = 1

    def _process_side_phases(self):
        """Process all phases from current position through End of Turn for self.turn side."""
        while True:
            self.advance_phase()
            if self.current_phase_index == 0:
                # Wrapped around — end of turn phase was processed
                break

    def end_turn(self):
        """Process both player and AI turns. Called when player presses SPACE."""
        # --- Player's remaining phases ---
        self.turn = 0
        self._process_side_phases()
        
        if self.game_over:
            return

        # --- AI's full turn ---
        self.turn = 1
        self.current_phase_index = 0
        
        # Process reports phase first to clear returned pigeons
        self.process_reports_phase()
        
        # AI decides actions ("Give Orders" equivalent)
        self.ai_controller.take_turn(self)
        
        # Process AI's remaining phases (Order Give/Receive through End of Turn)
        self._process_side_phases()
        
        # --- Advance to next turn ---
        self.turn_count += 1
        self.turn = 0
        
        # Check win condition after both sides have acted
        self._check_win_condition()
        
        if self.game_over:
            return
        
        # Update visibility for the player's new turn
        self.update_visibility()
        
        # Start player's new turn at phase 0
        self.current_phase_index = 0
        self.process_reports_phase()
        self.advance_phase()  # Move to "Give Orders"

