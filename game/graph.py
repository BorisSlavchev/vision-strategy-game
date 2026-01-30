import json
import os


class Node:
    def __init__(self, x, y, id, name=None):
        self.x = x
        self.y = y
        self.id = id
        self.name = name if name else str(id)
        self.neighbors = []
        self.neighbor_travel_times = {}  # {neighbor_node: travel_time}
        self.structure = None  # e.g., "Castle", "Outpost"
        self.structure_owner = None  # 0 or 1

    def add_neighbor(self, node, travel_time=1):
        if node not in self.neighbors:
            self.neighbors.append(node)
            self.neighbor_travel_times[node] = travel_time

    def get_travel_time(self, neighbor):
        """Get travel time to a neighbor node."""
        return self.neighbor_travel_times.get(neighbor, 1)

    def __repr__(self):
        return f"Node({self.x}, {self.y})"


def generate_vertex_name(index):
    """Generates names like A, B, C... Z, AA, AB..."""
    name = ""
    while index >= 0:
        name = chr(ord('A') + (index % 26)) + name
        index = (index // 26) - 1
    return name


def create_grid(width=3, height=3):
    """Legacy function - creates a uniform grid for backwards compatibility."""
    nodes = {}
    # Create nodes
    for y in range(height):
        for x in range(width):
            node_id = y * width + x
            nodes[(x, y)] = Node(x, y, node_id, name=generate_vertex_name(node_id))

    # Connect neighbors
    for y in range(height):
        for x in range(width):
            current = nodes[(x, y)]
            # Check 8 directions
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    current.add_neighbor(nodes[(nx, ny)], travel_time=1)

    return list(nodes.values())


def create_map_from_json(map_path):
    """
    Load a map from a JSON file.
    
    Returns:
        tuple: (nodes_list, player_castle_node, enemy_castle_node)
    """
    with open(map_path, 'r') as f:
        map_data = json.load(f)

    nodes = {}
    
    # Create nodes
    for i, node_def in enumerate(map_data["nodes"]):
        node_id = node_def["id"]
        # Use name from JSON if available, otherwise generate it
        name = node_def.get("name") or generate_vertex_name(i)
        node = Node(node_def["x"], node_def["y"], node_id, name=name)
        node.structure = node_def.get("structure")
        node.structure_owner = node_def.get("structure_owner")
        nodes[node_id] = node

    # Create edges (bidirectional)
    for edge in map_data["edges"]:
        from_node = nodes[edge["from"]]
        to_node = nodes[edge["to"]]
        travel_time = edge.get("travel_time", 1)
        from_node.add_neighbor(to_node, travel_time)
        to_node.add_neighbor(from_node, travel_time)

    player_castle = nodes[map_data["player_castle"]]
    enemy_castle = nodes[map_data["enemy_castle"]]

    return list(nodes.values()), player_castle, enemy_castle


def get_available_maps(maps_dir):
    """
    Scan the maps directory and return a list of available map names.
    
    Returns:
        list: List of map filenames (without .json extension)
    """
    maps = []
    if os.path.exists(maps_dir):
        for filename in os.listdir(maps_dir):
            if filename.endswith('.json'):
                maps.append(filename[:-5])  # Remove .json extension
    return sorted(maps)
