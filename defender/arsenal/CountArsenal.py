from .Arsenal import Arsenal


class CountArsenal(Arsenal):
    def __init__(self, arsenal_data):
        self.storage = arsenal_data
        return

    # Define by subclass
    def get_capabilities(self):
        return self.storage.keys()

    def get_max_capability_count(self, capability):
        if capability not in self.storage:
            return 0

        return self.storage[capability]

    # Define by subclass
    def update_storage(self, action):
        return
