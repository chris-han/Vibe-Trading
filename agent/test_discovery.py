from pathlib import Path
import os
import sys

# Import logic from the actual script if possible, or replicate it exactly
def test_bootstrap_path():
    # Mocking __file__ as if we were inside feishu_bot_api.py
    script_path = Path("/home/chris/repo/semantier/agent/src/skills/app-infra/productivity/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py").resolve()
    
    # Logic extracted from feishu_bot_api.py
    agent_home = None
    agent_env_path = None
    for parent in [script_path, *script_path.parents]:
        if parent.name == "agent" and parent.is_dir():
            agent_home = parent
            agent_env_path = parent / ".env"
            break
    
    print(f"Agent home directory found: {agent_home}")
    print(f"Resolved agent_env_path: {agent_env_path}")
    
    if agent_home and agent_home.exists():
        print("Success: Agent home directory exists and was correctly discovered.")
    else:
        print("Failure: Agent home directory not found or does not exist.")

if __name__ == "__main__":
    test_bootstrap_path()
