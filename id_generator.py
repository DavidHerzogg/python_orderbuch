class IDGenerator:
    def __init__(self):
        self.next_id = 1
        
    def generate(self):
        id = self.next_id
        self.next_id += 1
        return id