"""
Modular AI system for the strategy game.
AI has full map vision but must use the pigeon system for movement.
Includes configurable scouting delays to simulate tempo cost.
"""

from collections import deque


class AIController:
    """Base AI controller. Subclass to create different strategy profiles."""

    # Default tuning parameters
    SCOUTING_DELAY = 2       # Turns to skip orders to simulate scouting
    DELAY_INTERVAL = 5       # Every N turns, skip one turn of orders
    RECRUIT_GOLD_THRESHOLD = 15  # Minimum gold to trigger recruitment

    def __init__(self):
        self.turns_played = 0

    def take_turn(self, game_state):
        """Main entry point. Called once per turn to issue AI orders."""
        self.turns_played += 1

        # Scouting delay: skip issuing orders periodically
        if self._should_delay():
            return

        # Recruit if appropriate
        if self.should_recruit(game_state):
            game_state.recruit_unit(1)

        # Get and execute movement orders
        orders = self.get_orders(game_state)
        for order in orders:
            target_node, command_type, data, count = order
            game_state.send_pigeon_to_tile(1, target_node, command_type, data, count=count)

    def _should_delay(self):
        """Check if the AI should skip this turn to simulate scouting delay."""
        if self.turns_played <= self.SCOUTING_DELAY:
            # Initial delay at the start of the game
            return True
        if self.DELAY_INTERVAL > 0 and self.turns_played % self.DELAY_INTERVAL == 0:
            # Periodic delay every N turns
            return True
        return False

    def should_recruit(self, game_state):
        """Decide whether to recruit this turn."""
        return game_state.gold[1] >= self.RECRUIT_GOLD_THRESHOLD

    def get_orders(self, game_state):
        """
        Return a list of orders to issue this turn.
        Each order is a tuple: (target_node, command_type, data, count)
          - target_node: the node where the pigeon is sent (where the unit is)
          - command_type: 'move_attack'
          - data: the destination node for the move
          - count: number of units to move (None = all)
        """
        return []

    def _get_ai_units(self, game_state):
        """Get all AI units that are stationary (not traveling)."""
        return [u for u in game_state.units
                if u.owner == 1 and getattr(u, 'travel_remaining', 0) == 0
                and u.pending_command is None]

    def _get_player_units(self, game_state):
        """Get all player units (full vision cheat)."""
        return [u for u in game_state.units if u.owner == 0]

    def _has_available_pigeon(self, game_state):
        """Check if the AI has a pigeon available to send."""
        active_pigeons = [p for p in game_state.pigeons if p.owner == 1]
        return len(active_pigeons) < game_state.pigeon_limit[1]

    def _get_distance(self, source, target):
        """Find the distance between two nodes."""
        if source == target:
            return 0
        visited = {source: 0}
        queue = deque([(source, 0)])
        while queue:
            node, d = queue.popleft()
            for neighbor in node.neighbors:
                if neighbor == target:
                    return d + node.get_travel_time(neighbor)
                if neighbor not in visited:
                    visited[neighbor] = d + node.get_travel_time(neighbor)
                    queue.append((neighbor, visited[neighbor]))
        return 999

    def _find_shortest_path_next_step(self, game_state, source, target):
        """BFS to find the next node to move to on the shortest path from source to target."""
        if source == target:
            return None

        visited = {source: (0, None)}  # node: (cost, previous_node)
        queue = deque([(source, 0)])

        while queue:
            node, cost = queue.popleft()
            for neighbor in node.neighbors:
                travel = node.get_travel_time(neighbor)
                new_cost = cost + travel
                if neighbor not in visited or visited[neighbor][0] > new_cost:
                    visited[neighbor] = (new_cost, node)
                    queue.append((neighbor, new_cost))

        # Reconstruct path to find first step
        if target not in visited:
            return None

        current = target
        while visited[current][1] != source:
            current = visited[current][1]
            if current is None:
                return None
        return current

    def _get_units_with_pending_pigeons(self, game_state):
        """Get set of nodes that already have inbound pigeons from AI."""
        nodes_with_orders = set()
        for pigeon in game_state.pigeons:
            if pigeon.owner == 1 and not pigeon.returning:
                nodes_with_orders.add(pigeon.target_node)
        return nodes_with_orders

    def get_units_at(self, game_state, node):
        """Helper to get units at a specific node."""
        return [u for u in game_state.units if u.node == node]


class AggressiveAI(AIController):
    """Rush toward the player's castle via shortest path. Recruits frequently."""

    SCOUTING_DELAY = 1
    DELAY_INTERVAL = 6
    RECRUIT_GOLD_THRESHOLD = 10  # Recruit as soon as possible

    def get_orders(self, game_state):
        orders = []
        if not self._has_available_pigeon(game_state):
            return orders

        ai_units = self._get_ai_units(game_state)
        # Process units furthest from home first to keep them moving
        ai_units.sort(key=lambda u: self._get_distance(u.node, game_state.enemy_castle_node), reverse=True)
        
        nodes_with_orders = self._get_units_with_pending_pigeons(game_state)
        player_castle = game_state.player_castle_node
        ai_castle = game_state.enemy_castle_node

        for unit in ai_units:
            if not self._has_available_pigeon(game_state):
                break
            if unit.node in nodes_with_orders:
                continue

            # If at castle and have enough units, split to diversify pressure
            if unit.node == ai_castle and unit.count >= 10:
                # Try to send a small squad down a non-occupied lane
                targets = list(unit.node.neighbors)
                # Pick neighbor with fewest AI units
                target = min(targets, key=lambda n: sum(u.count for u in game_state.units if u.owner == 1 and u.node == n))
                orders.append((unit.node, "move_attack", target, 5))
                nodes_with_orders.add(unit.node)
                continue

            # Attack player castle or intercept close player units
            target_node = player_castle
            player_units = self._get_player_units(game_state)
            if player_units:
                closest_enemy = min(player_units, key=lambda u: self._get_distance(unit.node, u.node))
                if self._get_distance(unit.node, closest_enemy.node) <= 2:
                    target_node = closest_enemy.node

            next_step = self._find_shortest_path_next_step(
                game_state, unit.node, target_node)
            if next_step:
                orders.append((unit.node, "move_attack", next_step, None))
                nodes_with_orders.add(unit.node)

        return orders


class DefensiveAI(AIController):
    """Hold positions, build up forces, only attack when significantly outnumbering."""

    SCOUTING_DELAY = 4
    DELAY_INTERVAL = 4
    RECRUIT_GOLD_THRESHOLD = 10  # Still recruit, but move less

    def get_orders(self, game_state):
        orders = []
        if not self._has_available_pigeon(game_state):
            return orders

        ai_units = self._get_ai_units(game_state)
        player_units = self._get_player_units(game_state)
        nodes_with_orders = self._get_units_with_pending_pigeons(game_state)
        player_castle = game_state.player_castle_node
        ai_castle = game_state.enemy_castle_node

        total_ai_count = sum(u.count for u in game_state.units if u.owner == 1)
        total_player_count = sum(u.count for u in player_units) if player_units else 0

        # Garrison requirement: keep 20 units at base
        units_at_base = sum(u.count for u in ai_units if u.node == ai_castle)

        for unit in ai_units:
            if not self._has_available_pigeon(game_state):
                break
            if unit.node in nodes_with_orders:
                continue

            # 1. Threat Response: If enemy is very close to base, focus everyone there
            enemies_near_base = [u for u in player_units if self._get_distance(u.node, ai_castle) <= 2]
            if enemies_near_base and unit.node != ai_castle:
                next_step = self._find_shortest_path_next_step(game_state, unit.node, ai_castle)
                if next_step:
                    orders.append((unit.node, "move_attack", next_step, None))
                    nodes_with_orders.add(unit.node)
                continue

            # 2. Garrisoning logic
            if unit.node == ai_castle:
                if units_at_base < 20: # Stay and defend
                    continue
                # If we have excess, send scouts (size 5) to adjacent nodes if empty
                if unit.count > 25:
                    empty_neighbors = [n for n in unit.node.neighbors if not self.get_units_at(game_state, n)]
                    if empty_neighbors:
                        orders.append((unit.node, "move_attack", empty_neighbors[0], 5))
                        nodes_with_orders.add(unit.node)
                        continue

            # 3. Only full attack if ratio is high
            if total_ai_count >= total_player_count * 2.0 or total_ai_count >= 50:
                next_step = self._find_shortest_path_next_step(game_state, unit.node, player_castle)
                if next_step:
                    orders.append((unit.node, "move_attack", next_step, None))
                    nodes_with_orders.add(unit.node)
            else:
                # If away from base and no immediate threat, stay put or fall back if outnumbered locally
                if unit.node != ai_castle:
                    local_enemies = [u for u in player_units if self._get_distance(u.node, unit.node) <= 1]
                    if sum(u.count for u in local_enemies) > unit.count:
                        next_step = self._find_shortest_path_next_step(game_state, unit.node, ai_castle)
                        if next_step:
                            orders.append((unit.node, "move_attack", next_step, None))
                            nodes_with_orders.add(unit.node)

        return orders


class BalancedAI(AIController):
    """Recruit, expand to control tiles, then push when strong enough."""

    SCOUTING_DELAY = 2
    DELAY_INTERVAL = 5
    RECRUIT_GOLD_THRESHOLD = 15

    def get_orders(self, game_state):
        orders = []
        if not self._has_available_pigeon(game_state):
            return orders

        ai_units = self._get_ai_units(game_state)
        player_units = self._get_player_units(game_state)
        nodes_with_orders = self._get_units_with_pending_pigeons(game_state)
        player_castle = game_state.player_castle_node
        ai_castle = game_state.enemy_castle_node

        total_ai_count = sum(u.count for u in game_state.units if u.owner == 1)
        total_player_count = sum(u.count for u in player_units) if player_units else 0

        # Define map "Center" (Node 9 for MOBA, or heuristic)
        center_node = None
        for node in game_state.nodes:
            if node.id == 9: # MOBA specific
                center_node = node
                break
        if not center_node:
            # Grid fallback: find node closest to geometric center
            avg_x = sum(n.x for n in game_state.nodes) / len(game_state.nodes)
            avg_y = sum(n.y for n in game_state.nodes) / len(game_state.nodes)
            center_node = min(game_state.nodes, key=lambda n: (n.x-avg_x)**2 + (n.y-avg_y)**2)

        for unit in ai_units:
            if not self._has_available_pigeon(game_state):
                break
            if unit.node in nodes_with_orders:
                continue

            # Phase 1: Early game Expansion (Control the Center)
            if self.turns_played < 15:
                if unit.node == ai_castle and unit.count >= 10:
                    orders.append((unit.node, "move_attack", center_node, 10))
                    nodes_with_orders.add(unit.node)
                elif unit.node != center_node:
                    next_step = self._find_shortest_path_next_step(game_state, unit.node, center_node)
                    if next_step:
                        orders.append((unit.node, "move_attack", next_step, None))
                        nodes_with_orders.add(unit.node)
                continue

            # Phase 2: Mid game — opportunistic pushes
            if total_ai_count >= total_player_count * 1.5 or total_ai_count >= 40:
                next_step = self._find_shortest_path_next_step(game_state, unit.node, player_castle)
                if next_step:
                    orders.append((unit.node, "move_attack", next_step, None))
                    nodes_with_orders.add(unit.node)
            else:
                # Hold the center or closest strategic node
                if unit.node != center_node:
                    next_step = self._find_shortest_path_next_step(game_state, unit.node, center_node)
                    if next_step:
                        orders.append((unit.node, "move_attack", next_step, None))
                        nodes_with_orders.add(unit.node)

        return orders


# Registry of available AI types
AI_TYPES = {
    "Balanced": BalancedAI,
    "Aggressive": AggressiveAI,
    "Defensive": DefensiveAI,
}

def create_ai(ai_type="Balanced"):
    """Factory function to create an AI controller by type name."""
    cls = AI_TYPES.get(ai_type, BalancedAI)
    return cls()
