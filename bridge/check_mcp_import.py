import sys
sys.path.insert(0, r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\scripts')
import mcp_server
print('mcp_server import OK, tools:', len(mcp_server.mcp._tool_manager._tools) if hasattr(mcp_server.mcp,'_tool_manager') else 'unknown')
