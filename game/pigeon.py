class Pigeon:
    def __init__(self, owner, source_node, target_node, command, units=None):
        self.owner = owner
        self.source_node = source_node # Castle where pigeon started
        self.target_node = target_node
        self.command = command # {"type": "move", "destination": node} etc.
        self.units = units # The units this pigeon is for
        self.turns_to_reach = 2 # Default travel time
        self.total_turns = 2 # For calculating position
        self.returning = False
        self.arrived = False
        self.payload = None # Data collected (e.g. report)
        self.dispatched = False # Whether the pigeon has been sent out with a command

    def update(self):
        if self.turns_to_reach > 0:
            self.turns_to_reach -= 1
        
        if self.turns_to_reach == 0:
            self.arrived = True

    def get_progress(self):
        """Returns a value from 0.0 to 1.0 indicating travel progress"""
        if self.total_turns == 0:
            return 1.0
        return 1.0 - (self.turns_to_reach / self.total_turns)
