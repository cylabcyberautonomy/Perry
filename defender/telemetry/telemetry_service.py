from typing import Dict, List, Callable, Type, TypeVar
from defender.telemetry.events.event import Event
from .TelemetryAnalysis import TelemetryAnalysis


E = TypeVar("E", bound=Event)


class TelemetryService:
    def __init__(self, telemetry_analysis: TelemetryAnalysis):
        self.subscribers: Dict[Type[Event], List[Callable[[Event], None]]] = {}
        self.telemetry_analysis = telemetry_analysis

    def process_telemetry(self):
        new_telemetry = self.telemetry_analysis.get_new_telemetry()
        high_level_events = self.telemetry_analysis.process_low_level_events(
            new_telemetry
        )
        for event in high_level_events:
            self.emit(event)

    def subscribe(self, event_type: Type[E], handler: Callable[[E], None]):
        """Subscribe a handler to a specific event type."""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(handler)  # type: ignore

    def emit(self, event: Event):
        """Emit an event to all subscribers of the event's type."""
        event_type = type(event)
        if event_type in self.subscribers:
            for handler in self.subscribers[event_type]:
                handler(event)
