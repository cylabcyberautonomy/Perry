from defender.capabilities.Action import Action


class Orchestrator(object):
    def __init__(self, actuators: dict, action_counts: dict):
        self.actuators = actuators
        self.action_counts = action_counts

    # Runs an action on your infrastructure
    def run(self, actions: list):
        # For each action
        for action in actions:
            # Find the correct actuator for the action
            actuator = self.actuators[action.Capability]

            # Run the action
            actuator.run(action)

        return
