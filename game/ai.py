"""
Modular AI system for the strategy game.
AI has full map vision but must use the pigeon system for movement.
Includes configurable scouting delays to simulate tempo cost.
"""

from collections import deque
import random


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



        # Get and execute movement orders
        orders = self.get_orders(game_state)
        if orders:
            target_node, command_type, data, count = orders[0]
            game_state.issue_order_to_tile(1, target_node, command_type, data, count=count)

    def _should_delay(self):
        """Check if the AI should skip this turn to simulate scouting delay."""
        return random.random() < 0.20



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

    def _can_issue_order(self, game_state):
        """Check if the AI has a pigeon available to send."""
        return game_state.pending_orders[1] is None

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

    def _get_units_with_pending_orders(self, game_state):
        """Get set of nodes that already have pending orders from AI."""
        nodes_with_orders = set()
        order = game_state.pending_orders[1]
        if order is not None:
            nodes_with_orders.add(order["target_node"])
        return nodes_with_orders

    def get_units_at(self, game_state, node):
        """Helper to get units at a specific node."""
        return [u for u in game_state.units if u.node == node]


class AggressiveAI(AIController):
    """
    Aggressive AI:
    - 3 units guard the castle.
    - 7 units prioritize going for the enemy castle to win or killing enemy units.
    - If roaming army is killed, send out the castle army using the same behavior.
    """
    SCOUTING_DELAY = 1
    DELAY_INTERVAL = 6

    def get_orders(self, game_state):
        orders = []
        if not self._can_issue_order(game_state):
            return orders

        ai_units = self._get_ai_units(game_state)
        # Sort units by distance to enemy castle (furthest first)
        ai_units.sort(key=lambda u: self._get_distance(u.node, game_state.player_castle_node), reverse=True)
        
        nodes_with_orders = self._get_units_with_pending_orders(game_state)
        player_castle = game_state.player_castle_node
        ai_castle = game_state.enemy_castle_node
        player_units = self._get_player_units(game_state)
        
        total_ai_count = sum(u.count for u in game_state.units if u.owner == 1)

        # Roaming army condition: if total units <= 3, the roaming army is dead, so deploy garrison.
        deploy_garrison = total_ai_count <= 3

        for unit in ai_units:
            if not self._can_issue_order(game_state):
                break
            if unit.node in nodes_with_orders:
                continue

            # Garrison logic
            if unit.node == ai_castle and not deploy_garrison:
                # If we have more than 3 units at castle, split the excess to attack
                if unit.count > 3:
                    excess = unit.count - 3
                    # Find a target to move to
                    target_node = player_castle
                    if player_units:
                        closest_enemy = min(player_units, key=lambda u: self._get_distance(unit.node, u.node))
                        if self._get_distance(unit.node, closest_enemy.node) <= 2:
                            target_node = closest_enemy.node
                            
                    if random.random() < 0.25 and unit.node.neighbors:
                        next_step = random.choice(list(unit.node.neighbors))
                    else:
                        next_step = self._find_shortest_path_next_step(game_state, unit.node, target_node)
                    if next_step:
                        count_to_move = excess
                        if excess > 5 and random.random() < 0.5:
                            count_to_move = excess // 2
                        orders.append((unit.node, "move_attack", next_step, count_to_move))
                        nodes_with_orders.add(unit.node)
                continue

            # Roaming / deployed garrison logic
            target_node = player_castle
            if player_units:
                closest_enemy = min(player_units, key=lambda u: self._get_distance(unit.node, u.node))
                if self._get_distance(unit.node, closest_enemy.node) <= 2:
                    target_node = closest_enemy.node

            if random.random() < 0.25 and unit.node.neighbors:
                next_step = random.choice(list(unit.node.neighbors))
            else:
                next_step = self._find_shortest_path_next_step(game_state, unit.node, target_node)
            if next_step:
                count_to_move = None
                if unit.count > 5 and random.random() < 0.5:
                    count_to_move = unit.count // 2
                orders.append((unit.node, "move_attack", next_step, count_to_move))
                nodes_with_orders.add(unit.node)

        return orders


class ConservativeAI(AIController):
    """
    Conservative AI:
    - 7 units on its castle.
    - 3 units closely wander around castle and guard against enemies.
    - If roaming army is killed, send out the castle army following the same behavior.
    """
    SCOUTING_DELAY = 4
    DELAY_INTERVAL = 4

    def get_orders(self, game_state):
        orders = []
        if not self._can_issue_order(game_state):
            return orders

        ai_units = self._get_ai_units(game_state)
        nodes_with_orders = self._get_units_with_pending_orders(game_state)
        
        ai_castle = game_state.enemy_castle_node
        player_units = self._get_player_units(game_state)
        
        total_ai_count = sum(u.count for u in game_state.units if u.owner == 1)

        # Roaming army condition: if total units <= 7, roaming is dead, deploy garrison.
        deploy_garrison = total_ai_count <= 7
        garrison_size = 7

        for unit in ai_units:
            if not self._can_issue_order(game_state):
                break
            if unit.node in nodes_with_orders:
                continue

            # Garrison logic
            if unit.node == ai_castle and not deploy_garrison:
                if unit.count > garrison_size:
                    excess = unit.count - garrison_size
                    # Send excess to wander closely around castle
                    neighbors = list(ai_castle.neighbors)
                    if neighbors:
                        if random.random() < 0.25:
                            target_neighbor = random.choice(neighbors)
                        else:
                            # Pick a random neighbor or one with enemies
                            target_neighbor = neighbors[0]
                            for n in neighbors:
                                if self.get_units_at(game_state, n):
                                    target_neighbor = n
                                    break
                                    
                        count_to_move = excess
                        if excess > 5 and random.random() < 0.5:
                            count_to_move = excess // 2
                        orders.append((unit.node, "move_attack", target_neighbor, count_to_move))
                        nodes_with_orders.add(unit.node)
                continue

            # Roaming logic (closely wandering around castle and guarding)
            target_node = None
            
            # 1. Guard against nearby enemies
            enemies_near_base = [u for u in player_units if self._get_distance(u.node, ai_castle) <= 2]
            if enemies_near_base:
                closest_enemy = min(enemies_near_base, key=lambda u: self._get_distance(unit.node, u.node))
                target_node = closest_enemy.node
            else:
                # 2. Wander closely around castle
                if self._get_distance(unit.node, ai_castle) > 1:
                    # Too far, return to adjacent
                    if random.random() < 0.25 and unit.node.neighbors:
                        next_step = random.choice(list(unit.node.neighbors))
                    else:
                        next_step = self._find_shortest_path_next_step(game_state, unit.node, ai_castle)
                    if next_step:
                        # If wandering back to castle but not deploying garrison, don't enter if garrison is full
                        if next_step == ai_castle and not deploy_garrison:
                            units_at_base = sum(u.count for u in ai_units if u.node == ai_castle)
                            if units_at_base >= garrison_size:
                                continue # stay outside
                        
                        count_to_move = None
                        if unit.count > 5 and random.random() < 0.5:
                            count_to_move = unit.count // 2
                        orders.append((unit.node, "move_attack", next_step, count_to_move))
                        nodes_with_orders.add(unit.node)
                    continue
                else:
                    # Patrol to another adjacent node
                    neighbors = list(ai_castle.neighbors)
                    if neighbors:
                        # rotate to a neighbor
                        if unit.node in neighbors:
                            idx = neighbors.index(unit.node)
                            target_node = neighbors[(idx + 1) % len(neighbors)]
                        else:
                            target_node = neighbors[0]

            if target_node:
                if random.random() < 0.25 and unit.node.neighbors:
                    next_step = random.choice(list(unit.node.neighbors))
                else:
                    next_step = self._find_shortest_path_next_step(game_state, unit.node, target_node)
                if next_step:
                    if next_step == ai_castle and not deploy_garrison:
                        units_at_base = sum(u.count for u in ai_units if u.node == ai_castle)
                        if units_at_base >= garrison_size:
                            continue # stay outside
                            
                    count_to_move = None
                    if unit.count > 5 and random.random() < 0.5:
                        count_to_move = unit.count // 2
                    orders.append((unit.node, "move_attack", next_step, count_to_move))
                    nodes_with_orders.add(unit.node)

        return orders




# Registry of available AI types
AI_TYPES = {
    "Aggressive": AggressiveAI,
    "Conservative": ConservativeAI,
}

def create_ai(ai_type="Aggressive"):
    """Factory function to create an AI controller by type name."""
    cls = AI_TYPES.get(ai_type, AggressiveAI)
    return cls()
