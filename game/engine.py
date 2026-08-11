import os
import random
from collections import deque
from .graph import create_grid, create_map_from_json
from .ai import create_ai

UNIT_TYPES = ("Warrior", "Archer", "Wizard")
UNIT_TYPE_LETTER = {"Warrior": "W", "Archer": "A", "Wizard": "Z"}

# Warrior beats Archer, Archer beats Wizard, Wizard beats Warrior
RPS_BEATS = {
    "Warrior": "Archer",
    "Archer": "Wizard",
    "Wizard": "Warrior",
}


class Unit:
    def __init__(self, owner, unit_type, node, count=3):
        self.owner = owner  # 0 for player, 1 for enemy
        self.unit_type = unit_type
        self.node = node
        self.count = count
        self.has_moved = False
        self.pending_command = None

    def log_event(self, event_type, turn, details):
        pass


class GameState:
    def __init__(self, mode="God", map_name="moba", ai_type="Balanced", rng_seed=None, record_replay=True):
        self.map_name = map_name
        self.ai_controller = create_ai(ai_type)
        self.ai_type = ai_type

        self.rng_seed = rng_seed if rng_seed is not None else random.randint(0, 2**31 - 1)
        random.seed(self.rng_seed)
        # Dedicated RNG for combat so replays stay in sync when AI decisions are skipped
        self.rng = random.Random(self.rng_seed)

        maps_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "maps")
        map_path = os.path.join(maps_dir, f"{map_name}.json")

        if os.path.exists(map_path):
            self.nodes, self.player_castle_node, self.enemy_castle_node = create_map_from_json(map_path)
        else:
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
        self.has_acted = [False, False]  # one action per side per turn
        self.turn_count = 1

        self.mode = mode
        self.visible_nodes = [set(), set()]
        # intel_level[player][node] -> "full" | "silhouette"
        self.intel_level = [{}, {}]

        self.game_over = False
        self.winner = None

        # Replay recording
        self.record_replay = record_replay
        self.replay_actions = []

        self._spawn_starting_units()
        self.update_visibility()
        self.merge_units()

    def _spawn_starting_units(self):
        for owner, castle in ((0, self.player_castle_node), (1, self.enemy_castle_node)):
            for unit_type in UNIT_TYPES:
                self.units.append(Unit(owner, unit_type, castle, count=3))

    def get_node(self, x, y):
        for node in self.nodes:
            if node.x == x and node.y == y:
                return node
        return None

    def get_node_by_id(self, node_id):
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_units_at(self, node):
        return [unit for unit in self.units if unit.node == node]

    def get_unit_at(self, node, owner, unit_type):
        for unit in self.get_units_at(node):
            if unit.owner == owner and unit.unit_type == unit_type:
                return unit
        return None

    def merge_units(self):
        """Merge stacks of the same owner and unit_type on the same node."""
        for node in self.nodes:
            for owner in [0, 1]:
                for unit_type in UNIT_TYPES:
                    units_here = [
                        u for u in self.get_units_at(node)
                        if u.owner == owner and u.unit_type == unit_type
                    ]
                    if len(units_here) <= 1:
                        continue
                    main_unit = units_here[0]
                    for extra in units_here[1:]:
                        main_unit.count += extra.count
                        if extra in self.units:
                            self.units.remove(extra)

    def calculate_travel_time(self, source, target):
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

        return 999

    def graph_distance(self, source, target):
        """Hop count (unweighted BFS) between two nodes."""
        if source == target:
            return 0
        visited = {source}
        queue = deque([(source, 0)])
        while queue:
            node, dist = queue.popleft()
            for neighbor in node.neighbors:
                if neighbor == target:
                    return dist + 1
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, dist + 1))
        return 999

    def issue_order_to_tile(self, player_id, target_node, command_type, data, count=None, unit_type=None):
        """Issues exactly 1 order for the current turn."""
        if self.has_acted[player_id] or self.pending_orders[player_id] is not None:
            return False

        command = {
            "type": command_type,
            "data": data,
            "target_node": target_node,
        }
        if count is not None:
            command["count"] = count
        if unit_type is not None:
            command["unit_type"] = unit_type

        self.pending_orders[player_id] = command
        return True

    def execute_player_order_immediately(self):
        """Execute the player's pending order right away (still one per turn)."""
        if self.has_acted[0]:
            return False
        if self.pending_orders[0] is None:
            return False
        self.turn = 0
        self.process_execute_orders(0)
        self.has_acted[0] = True
        self.merge_units()
        self._check_win_condition()
        self.update_visibility()
        return True

    @staticmethod
    def _has_advantage(attacker_type, defender_type):
        return RPS_BEATS.get(attacker_type) == defender_type

    def _combat_roll(self, has_advantage, overcrowding_ratio):
        sides = 10
        if has_advantage:
            roll = max(self.rng.randint(1, sides), self.rng.randint(1, sides))
        else:
            roll = self.rng.randint(1, sides)
        if overcrowding_ratio > 0 and self.rng.random() < overcrowding_ratio:
            roll = min(roll, self.rng.randint(1, sides))
        return roll

    def resolve_combat(self, attackers, defenders):
        """Typed pairwise duels with RPS advantage (2d10 keep higher)."""
        if not attackers or not defenders:
            return

        def expand(stacks):
            fighters = []
            for u in stacks:
                for _ in range(u.count):
                    fighters.append(u.unit_type)
            return fighters

        a_fighters = expand(attackers)
        d_fighters = expand(defenders)

        a_total = len(a_fighters)
        d_total = len(d_fighters)
        if a_total == 0 or d_total == 0:
            return

        a_penalty = sum(u.count for u in attackers if u.count > 100)
        d_penalty = sum(u.count for u in defenders if u.count > 100)
        a_ratio = a_penalty / a_total if a_total else 0
        d_ratio = d_penalty / d_total if d_total else 0

        while a_fighters and d_fighters:
            self.rng.shuffle(a_fighters)
            self.rng.shuffle(d_fighters)

            next_a = []
            next_d = []
            num_duels = min(len(a_fighters), len(d_fighters))
            extras_a = a_fighters[num_duels:]
            extras_d = d_fighters[num_duels:]

            for i in range(num_duels):
                a_type = a_fighters[i]
                d_type = d_fighters[i]
                r_a = self._combat_roll(self._has_advantage(a_type, d_type), a_ratio)
                r_d = self._combat_roll(self._has_advantage(d_type, a_type), d_ratio)
                if r_a > r_d:
                    next_a.append(a_type)
                elif r_d > r_a:
                    next_d.append(d_type)
                else:
                    next_a.append(a_type)
                    next_d.append(d_type)

            if extras_a and next_d:
                self.rng.shuffle(extras_a)
                self.rng.shuffle(next_d)
                num_extra = min(len(extras_a), len(next_d))
                leftover_a = extras_a[num_extra:]
                leftover_d = next_d[num_extra:]
                survivors_a = list(next_a)
                survivors_d = []
                for i in range(num_extra):
                    a_type = extras_a[i]
                    d_type = next_d[i]
                    r_a = self._combat_roll(self._has_advantage(a_type, d_type), a_ratio)
                    r_d = self._combat_roll(self._has_advantage(d_type, a_type), d_ratio)
                    if r_a > r_d:
                        survivors_a.append(a_type)
                    elif r_d > r_a:
                        survivors_d.append(d_type)
                    else:
                        survivors_a.append(a_type)
                        survivors_d.append(d_type)
                next_a = survivors_a + leftover_a
                next_d = survivors_d + leftover_d
            elif extras_d and next_a:
                self.rng.shuffle(extras_d)
                self.rng.shuffle(next_a)
                num_extra = min(len(extras_d), len(next_a))
                leftover_d = extras_d[num_extra:]
                leftover_a = next_a[num_extra:]
                survivors_d = list(next_d)
                survivors_a = []
                for i in range(num_extra):
                    d_type = extras_d[i]
                    a_type = next_a[i]
                    r_a = self._combat_roll(self._has_advantage(a_type, d_type), a_ratio)
                    r_d = self._combat_roll(self._has_advantage(d_type, a_type), d_ratio)
                    if r_d > r_a:
                        survivors_d.append(d_type)
                    elif r_a > r_d:
                        survivors_a.append(a_type)
                    else:
                        survivors_d.append(d_type)
                        survivors_a.append(a_type)
                next_a = survivors_a + leftover_a
                next_d = survivors_d + leftover_d
            else:
                next_a.extend(extras_a)
                next_d.extend(extras_d)

            if len(next_a) == len(a_fighters) and len(next_d) == len(d_fighters):
                break
            a_fighters = next_a
            d_fighters = next_d

        self._apply_survivor_counts(attackers, a_fighters)
        self._apply_survivor_counts(defenders, d_fighters)

    def _apply_survivor_counts(self, stacks, surviving_types):
        """Write survivor counts back onto the given stacks by unit type."""
        if not stacks:
            return

        counts = {}
        for t in surviving_types:
            counts[t] = counts.get(t, 0) + 1

        owner = stacks[0].owner
        # Prefer keeping stacks on their current nodes; pick a home node for new types
        home_node = stacks[0].node

        # Zero existing participating stacks
        by_type = {}
        for u in stacks:
            u.count = 0
            by_type.setdefault(u.unit_type, u)

        for unit_type, count in counts.items():
            if unit_type in by_type:
                by_type[unit_type].count = count
            else:
                # New type among survivors — attach to home node stack if one exists
                existing = self.get_unit_at(home_node, owner, unit_type)
                if existing:
                    existing.count += count
                else:
                    nu = Unit(owner, unit_type, home_node, count=count)
                    self.units.append(nu)

        for u in list(stacks):
            if u.count <= 0 and u in self.units:
                self.units.remove(u)
    def update_visibility(self):
        for p in range(2):
            self.visible_nodes[p].clear()
            self.intel_level[p].clear()
            castle = self.player_castle_node if p == 0 else self.enemy_castle_node

            if self.mode == "God":
                for node in self.nodes:
                    self.visible_nodes[p].add(node)
                    self.intel_level[p][node] = "full"
                continue

            if self.mode == "Realistic":
                for node in self.nodes:
                    if node.structure and node.structure_owner == p:
                        self.visible_nodes[p].add(node)
                        self.intel_level[p][node] = "full"
                continue

            # Fog: vision from own units and castle, up to 2 hops
            sources = [castle]
            for unit in self.units:
                if unit.owner == p and unit.node not in sources:
                    sources.append(unit.node)

            best_dist = {}
            for source in sources:
                queue = deque([(source, 0)])
                local = {source: 0}
                while queue:
                    node, dist = queue.popleft()
                    if node not in best_dist or dist < best_dist[node]:
                        best_dist[node] = dist
                    if dist >= 2:
                        continue
                    for neighbor in node.neighbors:
                        nd = dist + 1
                        if neighbor not in local or local[neighbor] > nd:
                            local[neighbor] = nd
                            queue.append((neighbor, nd))

            for node, dist in best_dist.items():
                if dist <= 2:
                    self.visible_nodes[p].add(node)
                    own_here = any(u.owner == p and u.node == node for u in self.units)
                    if own_here or dist <= 1 or node == castle:
                        self.intel_level[p][node] = "full"
                    else:
                        self.intel_level[p][node] = "silhouette"

    def get_intel(self, player_id, node):
        if self.mode == "God":
            return "full"
        return self.intel_level[player_id].get(node)

    def execute_command(self, unit, command):
        if command["type"] != "move_attack":
            return None

        target_node = command["data"]
        if target_node not in unit.node.neighbors:
            return None

        requested_count = command.get("count", unit.count)
        move_count = min(requested_count, unit.count)
        if move_count <= 0:
            return None

        if move_count < unit.count:
            moving_unit = Unit(unit.owner, unit.unit_type, unit.node, count=move_count)
            unit.count -= move_count
            self.units.append(moving_unit)
        else:
            moving_unit = unit

        moving_unit.travel_target = target_node
        self.finalize_move_attack(moving_unit)
        return None

    def finalize_move_attack(self, moving_unit):
        if moving_unit not in self.units:
            return

        target_node = getattr(moving_unit, "travel_target", None)
        if not target_node:
            return

        enemies = [u for u in self.get_units_at(target_node) if u.owner != moving_unit.owner]

        if not enemies:
            moving_unit.node = target_node
            friendlies = [
                u for u in self.get_units_at(target_node)
                if u.owner == moving_unit.owner
                and u.unit_type == moving_unit.unit_type
                and u != moving_unit
            ]
            if friendlies:
                friendlies[0].count += moving_unit.count
                if moving_unit in self.units:
                    self.units.remove(moving_unit)
        else:
            allies_at_target = [u for u in self.get_units_at(target_node) if u.owner == moving_unit.owner]
            attackers = [moving_unit] + allies_at_target
            self.resolve_combat(attackers, enemies)

            remaining_enemies = [u for u in self.get_units_at(target_node) if u.owner != moving_unit.owner]
            if not remaining_enemies and moving_unit in self.units and moving_unit.count > 0:
                moving_unit.node = target_node
                friendlies = [
                    u for u in self.get_units_at(target_node)
                    if u.owner == moving_unit.owner
                    and u.unit_type == moving_unit.unit_type
                    and u != moving_unit
                ]
                if friendlies:
                    friendlies[0].count += moving_unit.count
                    if moving_unit in self.units:
                        self.units.remove(moving_unit)

            self.merge_units()

        if hasattr(moving_unit, "travel_target"):
            delattr(moving_unit, "travel_target")
    def process_execute_orders(self, player_id):
        """Execute the pending order for a side."""
        order = self.pending_orders[player_id]
        self.pending_orders[player_id] = None

        if not order:
            self._record_action(player_id, None)
            self.has_acted[player_id] = True
            return

        self._record_action(player_id, order)
        self.has_acted[player_id] = True

        if order["type"] == "move_attack":
            target_node = order["target_node"]
            unit_type = order.get("unit_type")
            friendly_units = [u for u in self.get_units_at(target_node) if u.owner == player_id]
            if unit_type:
                friendly_units = [u for u in friendly_units if u.unit_type == unit_type]
            if friendly_units:
                self.execute_command(friendly_units[0], order)

    def _record_action(self, player_id, order):
        if not self.record_replay:
            return
        if order is None:
            self.replay_actions.append({
                "turn": self.turn_count,
                "side": player_id,
                "command": None,
            })
            return

        dest = order.get("data")
        self.replay_actions.append({
            "turn": self.turn_count,
            "side": player_id,
            "command": order["type"],
            "unit_type": order.get("unit_type"),
            "from_node_id": order["target_node"].id if order.get("target_node") else None,
            "to_node_id": dest.id if dest is not None else None,
            "count": order.get("count"),
        })

    def process_end_of_turn(self, player_id):
        self.merge_units()
        for unit in self.units:
            if unit.owner == player_id:
                unit.has_moved = False

    def _check_win_condition(self):
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

    def end_turn(self):
        """End player turn (order already executed immediately, or noop) → AI → next turn."""
        self.turn = 0
        # Player may still have a pending order (edge case) or need a recorded skip
        if self.pending_orders[0] is not None:
            self.process_execute_orders(0)
        elif not self.has_acted[0]:
            self._record_action(0, None)
            self.has_acted[0] = True

        self.process_end_of_turn(0)
        self._check_win_condition()
        if self.game_over:
            self.update_visibility()
            return

        self.turn = 1
        self.ai_controller.take_turn(self)
        self.process_execute_orders(1)
        self.process_end_of_turn(1)
        self._check_win_condition()

        self.turn_count += 1
        self.turn = 0
        self.has_acted = [False, False]
        self.update_visibility()

    def apply_replay_action(self, action):
        """Re-issue a recorded action for deterministic playback (does not re-record)."""
        side = action["side"]
        if action.get("command") is None:
            self.pending_orders[side] = None
            return

        from_node = self.get_node_by_id(action["from_node_id"])
        to_node = self.get_node_by_id(action["to_node_id"])
        self.issue_order_to_tile(
            side,
            from_node,
            action["command"],
            to_node,
            count=action.get("count"),
            unit_type=action.get("unit_type"),
        )

    def get_replay_metadata(self):
        return {
            "rng_seed": self.rng_seed,
            "map_name": self.map_name,
            "mode": self.mode,
            "ai_type": self.ai_type,
            "actions": self.replay_actions,
            "winner": self.winner,
            "final_turn": self.turn_count,
        }
