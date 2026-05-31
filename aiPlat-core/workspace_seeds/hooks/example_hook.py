# Example workspace hook — on_pipeline_complete
#
# Hooks are Python scripts that run in response to system events.
# Place this file in ~/.aiplat/hooks/ and the system will load it at startup.
#
# Available events (subject to your HookManager config):
#   - pipeline_complete: fired when a pipeline run finishes
#   - agent_start: fired when an agent begins execution
#   - tool_call: fired before a tool invocation
#
# To use: copy this file, rename it, and customize the handle_event() function.

def handle_event(event: dict) -> dict:
    """Process a system event and optionally return a modified result.
    
    Args:
        event: dict with keys: type, data, timestamp, run_id
        
    Returns:
        dict with optional: modified, continue, message
    """
    event_type = event.get("type", "")
    
    if event_type == "pipeline_complete":
        print(f"[hook] Pipeline {event.get('run_id', '?')} completed")
        return {"continue": True}
    
    if event_type == "agent_start":
        print(f"[hook] Agent started: {event.get('data', {}).get('agent_id', '?')}")
        return {"continue": True}
    
    if event_type == "tool_call":
        tool_name = event.get('data', {}).get('tool_name', '?')
        print(f"[hook] Tool called: {tool_name}")
        return {"continue": True}
    
    return {"continue": True}
