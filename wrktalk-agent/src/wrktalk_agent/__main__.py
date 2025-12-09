"""Main entry point for WrkTalk Agent."""

import asyncio
import sys

from .agent import Agent
from .config import AgentConfig
from .utils.logging import setup_logging


def main():
    """Main entry point."""
    # Load configuration
    config = AgentConfig()

    # Setup logging
    setup_logging(config.log_level)

    # Create and start agent
    agent = Agent(config)

    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        print("\nAgent stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Agent failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
