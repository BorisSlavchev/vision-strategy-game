import math
import os
import random
from collections import deque
from .graph import create_grid, create_map_from_json
from .ai import create_ai

class Unit:
    def __init__(self, owner, unit_type, node, count=10):
        self.owner = owner # 0 for player, 1 for enemy
        self.unit_type = unit_type
        self.node = node
        self.count = count # Number of soldiers in this unit stack
        self.has_moved = False
        self.pending_command = None

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
        if False:
            return

        # 1. Collect current counts for all neighbors
        observations = {} # {node_id: {owner: count}}
        for neighbor in self.node.neighbors:
            units_here = game_state.get_units_at(neighbor)
            visible_units = units_here
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
        self.turn = 0  # 0 for player, 1 for AI
        self.pending_orders = [None, None]
        self.turn_count = 1
        self.reports = [[], []]  # Reports only used for player (index 0)
        self.pending_reports = [[], []]
        
        # Phase Management
        self.phases = [
            "Information (Reports)",
            "Give Orders",
            "Execute Orders",
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
        
        if ai_type == "Tutorial":
            u1_base = Unit(1, "Soldier", self.enemy_castle_node, count=5)
            u1_base.log_event("spawn", 1, f"Initial deployment at {self.enemy_castle_node.name}")
            self.units.append(u1_base)
            
            c_node = next((n for n in self.nodes if n.name == "C"), None)
            if c_node:
                u1_c = Unit(1, "Soldier", c_node, count=5)
                u1_c.log_event("spawn", 1, f"Initial deployment at {c_node.name}")
                self.units.append(u1_c)
        else:
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


    def merge_units(self):
        """Merges all units of the same owner on the same node"""
        for node in self.nodes:
            for owner in [0, 1]:
                # Only merge units that are not currently traveling
                units_here = [u for u in self.get_units_at(node) if u.owner == owner]
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

    def issue_order_to_tile(self, player_id, target_node, command_type, data, count=None):
        """Issues exactly 1 order to a specific tile for the current turn."""
        if self.pending_orders[player_id] is not None:
            return False # Only 1 order per turn allowed
            
        command = {"type": command_type, "data": data, "target_node": target_node}
        if count is not None:
            command["count"] = count
            
        self.pending_orders[player_id] = command
            
        return True

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

        def get_combat_roll(ratio, sides):
            if random.random() < ratio:
                # Overcrowding penalty: disadvantage (roll 2 dice, take lower)
                return min(random.randint(1, sides), random.randint(1, sides))
            return random.randint(1, sides)

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
                r_a = get_combat_roll(a_ratio, 10)
                r_d = get_combat_roll(d_ratio, 10)
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
                    r_a = get_combat_roll(a_ratio, 10)
                    r_d = get_combat_roll(d_ratio, 10)
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
                    r_a = get_combat_roll(a_ratio, 10)
                    r_d = get_combat_roll(d_ratio, 10)
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
                    unit.count -= move_count
                    self.units.append(moving_unit)
                    
                    unit.log_event("split", self.turn_count, f"Detached {move_count} units for move to {target_node.name}")
                    moving_unit.log_event("split", self.turn_count, f"Detached from main force at {unit.node.name}")
                else:
                    moving_unit = unit

                # Instant travel execution
                moving_unit.travel_target = target_node
                moving_unit.log_event("move_start", self.turn_count, f"Started move to {target_node.name}")
                self.finalize_move_attack(moving_unit)
                
        return None

    def finalize_move_attack(self, moving_unit):
        """Actually performs the move/attack logic"""
        if moving_unit not in self.units:
            return

        target_node = getattr(moving_unit, 'travel_target', None)
        if not target_node:
            return

        moving_unit.log_event("move_arrive", self.turn_count, f"Arrived at {target_node.name}")

        enemies = [u for u in self.get_units_at(target_node) if u.owner != moving_unit.owner]
        
        if not enemies:
            # Empty tile or only friendly units - just move in
            moving_unit.node = target_node
            # Merge with existing friendly units at target
            friendlies = [u for u in self.get_units_at(target_node) if u.owner == moving_unit.owner and u != moving_unit]
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
            allies_at_target = [u for u in self.get_units_at(target_node) if u.owner == moving_unit.owner]
            attackers = [moving_unit] + allies_at_target
            self.resolve_combat(attackers, enemies)
            
            # Check if any attackers survived and enemies are cleared
            if moving_unit in self.units or any(u in self.units for u in allies_at_target):
                remaining_enemies = [u for u in self.get_units_at(target_node) if u.owner != moving_unit.owner]
                if not remaining_enemies:
                    # All enemies defeated - move in if survived
                    if moving_unit in self.units:
                        moving_unit.node = target_node
                        # Final check for merge after moving in
                        friendlies = [u for u in self.get_units_at(target_node) if u.owner == moving_unit.owner and u != moving_unit]
                        if friendlies:
                            old_count = friendlies[0].count
                            friendlies[0].count += moving_unit.count
                            friendlies[0].history_log.extend(moving_unit.history_log)
                            friendlies[0].log_event("merge", self.turn_count, f"Merged {moving_unit.count} battle survivors with {old_count} stationed at {target_node.name}")
                            if moving_unit in self.units:
                                self.units.remove(moving_unit)
        
        if hasattr(moving_unit, 'travel_target'):
            delattr(moving_unit, 'travel_target')

    def advance_phase(self):
        """Advances the game to the next phase. Returns True if turn ended."""
        self.current_phase_index += 1
        
        if self.current_phase_index >= len(self.phases):
            self.current_phase_index = 0
            return True
            
        # Execute phase logic
        phase = self.phases[self.current_phase_index]
        
        if phase == "Information (Reports)":
            self.process_reports_phase()
        elif phase == "Execute Orders":
            self.process_execute_orders_phase()
        elif phase == "End of Turn":
            self.process_end_of_turn()
            
        return False

    def process_reports_phase(self):
        """Phase 1: Process reports that were requested last turn"""
        for report in self.pending_reports[self.turn]:
            report['turn_received'] = self.turn_count
            self.reports[self.turn].append(report)
        self.pending_reports[self.turn].clear()

    def process_execute_orders_phase(self):
        """Phase 3: Execute the pending order for the turn"""
        order = self.pending_orders[self.turn]
        self.pending_orders[self.turn] = None
        
        if not order:
            return
            
        target_node = order["target_node"]
        
        if order["type"] == "report":
            units_at_target = self.get_units_at(target_node)
            friendly_count = sum(u.count for u in units_at_target if u.owner == self.turn)
            
            if friendly_count == 0:
                payload = {
                    'position': target_node.name,
                    'message': "No friendly units present to provide a report.",
                    'count': 0,
                    'friendly_adjacent': [],
                    'enemy_adjacent': []
                }
            else:
                enemy_count = sum(u.count for u in units_at_target if u.owner != self.turn)
                friendly_adj = []
                enemy_adj = []
                for neighbor in target_node.neighbors:
                    n_units = self.get_units_at(neighbor)
                    for u in n_units:
                        if u.owner == self.turn:
                            friendly_adj.append({'pos': neighbor.name, 'count': u.count})
                        else:
                            enemy_adj.append({'pos': neighbor.name, 'count': u.count})
                
                payload = {
                    'position': target_node.name,
                    'is_report': True,
                    'friendly_count': friendly_count,
                    'enemy_count': enemy_count,
                    'friendly_adjacent': friendly_adj,
                    'enemy_adjacent': enemy_adj
                }
            
            # Append to pending reports
            self.pending_reports[self.turn].append(payload)
                
        elif order["type"] == "move_attack":
            friendly_units = [u for u in self.get_units_at(target_node) if u.owner == self.turn]
            if friendly_units:
                self.execute_command(friendly_units[0], order)

    def process_end_of_turn(self):
        """Phase 6: Resource generation and end-of-side processing"""
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
        elif not enemy_units:
            self.game_over = True
            self.winner = 0
        elif not player_units:
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

