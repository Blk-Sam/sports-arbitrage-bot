"""
Scheduling Module - Automated Bot Execution

Intelligent scheduling system with:
- Event-driven execution timing
- Adaptive polling intervals
- Peak/off-peak hour optimization
- API quota management
- Automatic retry and error recovery
"""

from src.scheduling.scheduler import dynamic_scheduler

__all__ = [
    'dynamic_scheduler',
]
