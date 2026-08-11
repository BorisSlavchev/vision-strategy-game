"""
Modular AI system for the strategy game.
AI has full map vision. Issues one move_attack order per turn with unit_type.
"""

from collections import deque
import random


class AIController:
    """Base AI controller. Subclass to create different strategy profiles."""

    SCOUTING_DELAY = 2
    DELAY_INTERVAL = 5

    def __init__(self):
        self.turns_played = 0

    def take_turn(self, game_state):
        self.turns_played += 1
        if self._should_delay():
            return

        orders = self.get_orders(game_state)
        if orders:
            target_node, command_type, data, count, unit_type = orders[0]
            game_state.issue_order_to_tile(
                1, target_node, command_type, data, count=count, unit_type=unit_type
            )

    def _should_delay(self):
        return random.random() < 0.20

    def get_orders(self, game_state):
        return []

    def _get_ai_units(self, game_state):
        return [
            u for u in game_state.units
            if u.owner == 1 and getattr(u, "travel_remaining", 0) == 0
            and u.pending_command is None
        ]

    def _get_player_units(self, game_state):
        return [u for u in game_state.units if u.owner == 0]

    def _can_issue_order(self, game_state):
        return (
            game_state.pending_orders[1] is None
            and not game_state.has_acted[1]
        )

    def _get_distance(self, source, target):
        if source == target:
            return 0
        visited = {source: 0}
        queue = deque([(source, 0)])
        while queue:
            node, d = queue.popleft()
            for neighbor in node.neighbors:
                if neighbor == target:
                    return d + 1
                if neighbor not in visited:
                    visited[neighbor] = d + 1
                    queue.append((neighbor, d + 1))
        return 999

    def _find_shortest_path_next_step(self, game_state, source, target):
        if source == target:
            return None

        visited = {source: (0, None)}
        queue = deque([(source, 0)])

        while queue:
            node, cost = queue.popleft()
            for neighbor in node.neighbors:
                new_cost = cost + 1
                if neighbor not in visited or visited[neighbor][0] > new_cost:
                    visited[neighbor] = (new_cost, node)
                    queue.append((neighbor, new_cost))

        if target not in visited:
            return None

        current = target
        while visited[current][1] != source:
            current = visited[current][1]
            if current is None:
                return None
        return current

    def _get_units_with_pending_orders(self, game_state):
        nodes_with_orders = set()
        order = game_state.pending_orders[1]
        if order is not None:
            nodes_with_orders.add(order["target_node"])
        return nodes_with_orders

    def get_units_at(self, game_state, node):
        return [u for u in game_state.units if u.node == node]

    def _preferred_type_vs(self, enemy_type):
        """Pick the type that beats the enemy."""
        beats = {"Archer": "Warrior", "Wizard": "Archer", "Warrior": "Wizard"}
        return beats.get(enemy_type, "Warrior")


class AggressiveAI(AIController):
    """Push toward the player castle; engage nearby enemies with RPS-aware stacks."""

    def get_orders(self, game_state):
        orders = []
        if not self._can_issue_order(game_state):
            return orders

        ai_units = self._get_ai_units(game_state)
        ai_units.sort(
            key=lambda u: self._get_distance(u.node, game_state.player_castle_node),
            reverse=True,
        )

        nodes_with_orders = self._get_units_with_pending_orders(game_state)
        player_castle = game_state.player_castle_node
        ai_castle = game_state.enemy_castle_node
        player_units = self._get_player_units(game_state)

        total_ai_count = sum(u.count for u in game_state.units if u.owner == 1)
        # Keep one stack at home when possible; deploy all when thin
        deploy_garrison = total_ai_count <= 3

        for unit in ai_units:
            if not self._can_issue_order(game_state):
                break
            if unit.node in nodes_with_orders:
                continue

            if unit.node == ai_castle and not deploy_garrison:
                # Leave at least one unit type at castle; send others out
                at_castle = [u for u in ai_units if u.node == ai_castle]
                if len(at_castle) <= 1:
                    continue
                target_node = player_castle
                if player_units:
                    closest_enemy = min(
                        player_units, key=lambda u: self._get_distance(unit.node, u.node)
                    )
                    if self._get_distance(unit.node, closest_enemy.node) <= 3:
                        target_node = closest_enemy.node
                        # Prefer stack that beats closest enemy type
                        preferred = self._preferred_type_vs(closest_enemy.unit_type)
                        preferred_unit = next(
                            (u for u in at_castle if u.unit_type == preferred and u.count > 0),
                            unit,
                        )
                        unit = preferred_unit

                if random.random() < 0.25 and unit.node.neighbors:
                    next_step = random.choice(list(unit.node.neighbors))
                else:
                    next_step = self._find_shortest_path_next_step(
                        game_state, unit.node, target_node
                    )
                if next_step:
                    count_to_move = unit.count
                    if unit.count > 1 and random.random() < 0.4:
                        count_to_move = max(1, unit.count // 2)
                    orders.append(
                        (unit.node, "move_attack", next_step, count_to_move, unit.unit_type)
                    )
                    nodes_with_orders.add(unit.node)
                continue

            target_node = player_castle
            if player_units:
                closest_enemy = min(
                    player_units, key=lambda u: self._get_distance(unit.node, u.node)
                )
                if self._get_distance(unit.node, closest_enemy.node) <= 3:
                    target_node = closest_enemy.node

            if random.random() < 0.25 and unit.node.neighbors:
                next_step = random.choice(list(unit.node.neighbors))
            else:
                next_step = self._find_shortest_path_next_step(
                    game_state, unit.node, target_node
                )
            if next_step:
                count_to_move = None
                if unit.count > 1 and random.random() < 0.4:
                    count_to_move = max(1, unit.count // 2)
                orders.append(
                    (unit.node, "move_attack", next_step, count_to_move, unit.unit_type)
                )
                nodes_with_orders.add(unit.node)

        return orders


class ConservativeAI(AIController):
    """Hold the castle and patrol nearby; engage threats with RPS-aware stacks."""

    def get_orders(self, game_state):
        orders = []
        if not self._can_issue_order(game_state):
            return orders

        ai_units = self._get_ai_units(game_state)
        nodes_with_orders = self._get_units_with_pending_orders(game_state)
        ai_castle = game_state.enemy_castle_node
        player_units = self._get_player_units(game_state)

        total_ai_count = sum(u.count for u in game_state.units if u.owner == 1)
        deploy_garrison = total_ai_count <= 6

        for unit in ai_units:
            if not self._can_issue_order(game_state):
                break
            if unit.node in nodes_with_orders:
                continue

            if unit.node == ai_castle and not deploy_garrison:
                at_castle = [u for u in ai_units if u.node == ai_castle]
                if len(at_castle) <= 2:
                    continue
                neighbors = list(ai_castle.neighbors)
                if neighbors:
                    target_neighbor = neighbors[0]
                    for n in neighbors:
                        if self.get_units_at(game_state, n):
                            target_neighbor = n
                            break
                    if random.random() < 0.25:
                        target_neighbor = random.choice(neighbors)
                    count_to_move = unit.count
                    if unit.count > 1 and random.random() < 0.5:
                        count_to_move = max(1, unit.count // 2)
                    orders.append(
                        (unit.node, "move_attack", target_neighbor, count_to_move, unit.unit_type)
                    )
                    nodes_with_orders.add(unit.node)
                continue

            target_node = None
            enemies_near_base = [
                u for u in player_units if self._get_distance(u.node, ai_castle) <= 3
            ]
            if enemies_near_base:
                closest_enemy = min(
                    enemies_near_base, key=lambda u: self._get_distance(unit.node, u.node)
                )
                target_node = closest_enemy.node
            else:
                if self._get_distance(unit.node, ai_castle) > 2:
                    next_step = self._find_shortest_path_next_step(
                        game_state, unit.node, ai_castle
                    )
                    if next_step:
                        orders.append(
                            (unit.node, "move_attack", next_step, None, unit.unit_type)
                        )
                        nodes_with_orders.add(unit.node)
                    continue
                neighbors = list(ai_castle.neighbors)
                if neighbors:
                    if unit.node in neighbors:
                        idx = neighbors.index(unit.node)
                        target_node = neighbors[(idx + 1) % len(neighbors)]
                    else:
                        target_node = neighbors[0]

            if target_node:
                next_step = self._find_shortest_path_next_step(
                    game_state, unit.node, target_node
                )
                if next_step:
                    orders.append(
                        (unit.node, "move_attack", next_step, None, unit.unit_type)
                    )
                    nodes_with_orders.add(unit.node)

        return orders


AI_TYPES = {
    "Aggressive": AggressiveAI,
    "Conservative": ConservativeAI,
}


def create_ai(ai_type="Aggressive"):
    cls = AI_TYPES.get(ai_type, AggressiveAI)
    return cls()
