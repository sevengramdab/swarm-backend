"""
SimpleSwarm -- Autonomous Computer Control + Test Orchestration
===============================================================
Gives MassAgentOrchestrator full mouse, keyboard, screenshot, and shell control.
Can autonomously test OrbStudio Swarm end-to-end across 7 phases.

Usage:
    from core.simpleswarm.computer_controller import ComputerController
    from core.simpleswarm.test_runner import TestRunner
    from core.simpleswarm.simple_swarm_orchestrator import SimpleSwarmOrchestrator

    cc = ComputerController()
    cc.screenshot()           # PIL Image of desktop
    cc.click(960, 540)        # Click screen center
    cc.type_text("hello")     # Type text
    cc.hotkey("ctrl", "c")    # Send key combo

    runner = TestRunner(cc)
    results = runner.run_all_phases()
"""

__version__ = "1.0.0"
