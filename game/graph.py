class Node:
    def __init__(self, x, y, id):
        self.x = x
        self.y = y
        self.id = id
        self.neighbors = []
        self.resources = {"gold": 0, "food": 0, "stone": 0, "wood": 0}
        self.structure = None # e.g., "Castle", "Outpost"
        self.structure_owner = None # 0 or 1

    def add_neighbor(self, node):
        if node not in self.neighbors:
            self.neighbors.append(node)

    def __repr__(self):
        return f"Node({self.x}, {self.y})"

def create_grid(width=3, height=3):
    nodes = {}
    # Create nodes
    for y in range(height):
        for x in range(width):
            node_id = y * width + x
            nodes[(x, y)] = Node(x, y, node_id)

    # Connect neighbors
    for y in range(height):
        for x in range(width):
            current = nodes[(x, y)]
            # Check 8 directions
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    current.add_neighbor(nodes[(nx, ny)])
    
    return list(nodes.values())
