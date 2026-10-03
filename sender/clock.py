import os
import random
from typing import Optional


class SimulationClock:
    """Manages emission rate and sleep intervals between ticket creations."""

    def __init__(
        self,
        tickets_per_day: Optional[int] = None,
        demo_mode: Optional[bool] = None,
        simulated_day_seconds: Optional[float] = None,
    ):
        env_tpd = int(os.getenv("TICKETS_PER_DAY", "12"))
        self.default_tickets_per_day = tickets_per_day or env_tpd
        
        env_demo = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")
        self.demo_mode = demo_mode if demo_mode is not None else env_demo
        
        env_day_sec = float(os.getenv("SIMULATED_DAY_SECONDS", "30"))
        self.simulated_day_seconds = simulated_day_seconds or env_day_sec

    @property
    def day_length_seconds(self) -> float:
        """Returns the length of a single 'day' in seconds."""
        if self.demo_mode:
            return max(1.0, self.simulated_day_seconds)
        return 86400.0  # 24 real hours

    def get_tickets_for_day(self) -> int:
        """10–15 tickets per day, randomized within that range per cycle."""
        return random.randint(10, 15)

    def compute_sleep_interval(self, total_tickets_today: int) -> float:
        """Sleep is computed from tickets_per_day and the day length with jitter."""
        if total_tickets_today <= 0:
            total_tickets_today = 12
        base_interval = self.day_length_seconds / total_tickets_today
        # Add +/- 20% jitter
        jitter = random.uniform(0.8, 1.2)
        return max(0.01, base_interval * jitter)
