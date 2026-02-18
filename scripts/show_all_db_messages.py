#!/usr/bin/env python3
"""
Show ALL messages saved in the database for a thread.
This displays the complete accumulated state from the latest checkpoint,
showing exactly what's stored in the database (before any filtering).
"""

import asyncio
import sys
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from src.config import env


async def show_all_db_messages(thread_id: str):
    """Show all messages stored in database for a thread."""
    
    conn_string = f"postgresql://{env.DATABASE_USER}:{env.DATABASE_PASSWORD}@{env.DATABASE_HOST or 'localhost'}:{env.DATABASE_PORT or '5432'}/{env.DATABASE}"
    
    async with AsyncPostgresSaver.from_conn_string(conn_string) as checkpointer:
        # Get the latest checkpoint for this thread
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        
        if not checkpoint_tuple:
            print(f"❌ No checkpoint found for thread: {thread_id}")
            return
        
        checkpoint = checkpoint_tuple.checkpoint
        metadata = checkpoint_tuple.metadata
        
        print("=" * 100)
        print(f"📦 DATABASE MESSAGES FOR THREAD: {thread_id}")
        print("=" * 100)
        print(f"📍 Checkpoint ID: {checkpoint['id']}")
        print(f"📊 Step: {metadata.get('step', 'N/A')}")
        print("=" * 100)
        print()
        
        # Get messages from the checkpoint state
        messages = checkpoint.get('channel_values', {}).get('messages', [])
        
        if not messages:
            print("📭 No messages in this checkpoint")
            return
        
        print(f"📬 TOTAL MESSAGES IN DATABASE: {len(messages)}")
        print()
        
        # Count message types
        human_count = 0
        ai_count = 0
        ai_with_tools_count = 0
        tool_count = 0
        system_count = 0
        total_tool_calls = 0
        
        for i, msg in enumerate(messages, 1):
            msg_type = msg.__class__.__name__
            
            print(f"\n{'─' * 100}")
            print(f"#{i:03d} | {msg_type}")
            print(f"{'─' * 100}")
            
            if msg_type == "HumanMessage":
                human_count += 1
                print(f"👤 USER: {msg.content}")
                
            elif msg_type == "AIMessage":
                ai_count += 1
                
                # Check for tool calls
                has_tools = hasattr(msg, 'tool_calls') and msg.tool_calls
                if has_tools:
                    ai_with_tools_count += 1
                    total_tool_calls += len(msg.tool_calls)
                    print(f"🤖 AI (with {len(msg.tool_calls)} tool calls):")
                    
                    # Show tool calls
                    for tc_idx, tc in enumerate(msg.tool_calls, 1):
                        print(f"   🔧 Tool Call #{tc_idx}:")
                        print(f"      • Name: {tc.get('name', 'unknown')}")
                        print(f"      • ID: {tc.get('id', 'unknown')}")
                        print(f"      • Args: {tc.get('args', {})}")
                else:
                    print(f"🤖 AI:")
                
                # Parse content (ALWAYS show content, even if there are tool calls)
                if isinstance(msg.content, list):
                    for part in msg.content:
                        if isinstance(part, dict):
                            if part.get('type') == 'thinking':
                                thinking = part.get('thinking', '')
                                if len(thinking) > 500:
                                    print(f"   💭 Thinking: {thinking[:500]}...")
                                    print(f"      (Total length: {len(thinking)} chars)")
                                else:
                                    print(f"   💭 Thinking: {thinking}")
                            elif part.get('type') == 'text':
                                text = part.get('text', '')
                                print(f"   💬 Response: {text}")
                        elif isinstance(part, str):
                            # String in content list - treat as text response
                            print(f"   💬 Response: {part}")
                        else:
                            # Other types - try to display as string
                            part_str = str(part)
                            if len(part_str) > 200:
                                print(f"   💬 Response: {part_str[:200]}...")
                            else:
                                print(f"   💬 Response: {part_str}")
                elif isinstance(msg.content, str):
                    print(f"   💬 Response: {msg.content}")
                    
            elif msg_type == "ToolMessage":
                tool_count += 1
                tool_name = getattr(msg, 'name', 'unknown')
                tool_call_id = getattr(msg, 'tool_call_id', 'unknown')
                content = str(msg.content)
                
                print(f"🔧 TOOL RESULT:")
                print(f"   • Tool: {tool_name}")
                print(f"   • Call ID: {tool_call_id}")
                
                if len(content) > 300:
                    print(f"   • Result: {content[:300]}...")
                    print(f"   • (Total length: {len(content)} chars)")
                else:
                    print(f"   • Result: {content}")
                
            elif msg_type == "SystemMessage":
                system_count += 1
                content = msg.content[:200]
                print(f"⚙️  SYSTEM: {content}{'...' if len(msg.content) > 200 else ''}")
                
            else:
                print(f"❓ {msg_type}")
        
        # Summary
        print()
        print("=" * 100)
        print("📊 DATABASE SUMMARY:")
        print("=" * 100)
        print(f"   👤 HumanMessages: {human_count}")
        print(f"   🤖 AIMessages: {ai_count}")
        print(f"      └─ With tool_calls: {ai_with_tools_count} (total {total_tool_calls} tool calls)")
        print(f"   🔧 ToolMessages: {tool_count}")
        print(f"   ⚙️  SystemMessages: {system_count}")
        print(f"   📦 TOTAL: {len(messages)} messages")
        print("=" * 100)
        
        if tool_count > 0 or total_tool_calls > 0:
            print()
            print("✅ Tool context IS being saved to database!")
            print(f"   • {total_tool_calls} tool_calls in AIMessages")
            print(f"   • {tool_count} ToolMessages")
            print()
            print("💡 Note: LLM sees filtered version (old tools removed),")
            print("   but database keeps everything for debugging/audit.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python show_all_db_messages.py <thread_id>")
        print()
        print("Example:")
        print("  python show_all_db_messages.py 553499928911902")
        sys.exit(1)
    
    thread_id = sys.argv[1]
    asyncio.run(show_all_db_messages(thread_id))
