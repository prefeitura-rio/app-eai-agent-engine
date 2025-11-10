#!/usr/bin/env python3
"""
Quick test script to see your available MCP tools
Run this to identify which tool to use for user retrieval
"""

import asyncio
from src.tools import mcp_tools

def list_mcp_tools():
    """List all available MCP tools with their details."""
    print("=== AVAILABLE MCP TOOLS ===\n")
    
    if not mcp_tools:
        print("No MCP tools found!")
        return
    
    for i, tool in enumerate(mcp_tools, 1):
        print(f"{i}. Tool Name: {tool.name}")
        print(f"   Description: {tool.description}")
        print(f"   Args Schema: {tool.args}")
        
        # Try to show the function signature if available
        if hasattr(tool, 'func') and tool.func:
            import inspect
            try:
                sig = inspect.signature(tool.func)
                print(f"   Function Signature: {tool.name}{sig}")
            except:
                pass
        
        print("-" * 50)
    
    print(f"\nTotal: {len(mcp_tools)} tools available")

async def test_specific_tool(tool_name: str, test_params: dict = None):
    """Test calling a specific MCP tool."""
    if test_params is None:
        test_params = {"user_id": "test_user_123"}
    
    print(f"\n=== TESTING TOOL: {tool_name} ===")
    
    # Find the tool
    target_tool = None
    for tool in mcp_tools:
        if tool.name == tool_name:
            target_tool = tool
            break
    
    if not target_tool:
        print(f"❌ Tool '{tool_name}' not found!")
        return
    
    try:
        print(f"📞 Calling {tool_name} with params: {test_params}")
        result = await target_tool.ainvoke(test_params)
        print(f"✅ Success! Result:")
        print(f"   Type: {type(result)}")
        print(f"   Value: {result}")
        
        # If it's a dict, show the structure
        if isinstance(result, dict):
            print(f"   Keys: {list(result.keys())}")
            
    except Exception as e:
        print(f"❌ Error calling tool: {str(e)}")
        print(f"   Exception type: {type(e).__name__}")

if __name__ == "__main__":
    # List all tools
    # list_mcp_tools()
    
    # Example: Test a specific tool (replace with your actual tool name)
    # Uncomment and modify the line below to test a specific tool:
    asyncio.run(test_specific_tool("get_user_memory", {"user_id": "testuserid001"}))
    
    print("\n" + "="*60)
    print("NEXT STEPS:")
    print("1. Find the tool name you want to use for user retrieval")
    print("2. Test it by uncommenting the test_specific_tool line above")
    print("3. Use that tool name in your Agent configuration")
    print("="*60)