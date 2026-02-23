#!/usr/bin/env python3
"""
Analyze token usage in tool_calls and ToolMessages across all thread_ids.

This script:
1. Gets the last checkpoint for each thread_id
2. Counts tool_calls (in AIMessages) and ToolMessages
3. Calculates tokens in these messages
4. Provides statistics:
   - Mean count of tool_call/tool_response messages per thread
   - Mean token sum for these messages per thread
   - Percentage of total tokens these represent
"""

import asyncio
import json
from typing import List, Dict, Any
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from src.config import env
import tiktoken


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens in a text string."""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception as e:
        # Fallback: approximate 1 token ~= 4 chars
        return len(text) // 4


def count_message_tokens(msg: Any, model: str = "gpt-4") -> int:
    """Count tokens in a single message."""
    total_tokens = 0
    
    # Base overhead per message
    total_tokens += 4  # Every message has overhead
    
    msg_type = msg.__class__.__name__
    
    if msg_type == "AIMessage":
        # Count content tokens
        if isinstance(msg.content, str):
            total_tokens += count_tokens(msg.content, model)
        elif isinstance(msg.content, list):
            for part in msg.content:
                if isinstance(part, dict):
                    if part.get('type') == 'thinking':
                        total_tokens += count_tokens(part.get('thinking', ''), model)
                    elif part.get('type') == 'text':
                        total_tokens += count_tokens(part.get('text', ''), model)
                elif isinstance(part, str):
                    total_tokens += count_tokens(part, model)
                else:
                    total_tokens += count_tokens(str(part), model)
        
        # Count tool_calls tokens
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tc in msg.tool_calls:
                total_tokens += count_tokens(tc.get('name', ''), model)
                total_tokens += count_tokens(json.dumps(tc.get('args', {})), model)
                total_tokens += 3  # Overhead per tool call
    
    elif msg_type == "ToolMessage":
        # Count content
        total_tokens += count_tokens(str(msg.content), model)
        # Count name
        if hasattr(msg, 'name'):
            total_tokens += count_tokens(msg.name, model)
    
    elif msg_type == "HumanMessage":
        if isinstance(msg.content, str):
            total_tokens += count_tokens(msg.content, model)
        else:
            total_tokens += count_tokens(str(msg.content), model)
    
    elif msg_type == "SystemMessage":
        total_tokens += count_tokens(msg.content, model)
    
    return total_tokens


def count_tool_context_tokens(msg: Any, model: str = "gpt-4") -> int:
    """Count tokens ONLY in tool_calls and ToolMessages."""
    total_tokens = 0
    
    msg_type = msg.__class__.__name__
    
    if msg_type == "AIMessage":
        # Only count tool_calls, NOT the content
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tc in msg.tool_calls:
                total_tokens += count_tokens(tc.get('name', ''), model)
                total_tokens += count_tokens(json.dumps(tc.get('args', {})), model)
                total_tokens += 3  # Overhead per tool call
    
    elif msg_type == "ToolMessage":
        # Count everything in ToolMessage
        total_tokens += 4  # Message overhead
        total_tokens += count_tokens(str(msg.content), model)
        if hasattr(msg, 'name'):
            total_tokens += count_tokens(msg.name, model)
    
    return total_tokens


async def analyze_all_threads():
    """Analyze tool context token usage across all threads."""
    
    conn_string = f"postgresql://{env.DATABASE_USER}:{env.DATABASE_PASSWORD}@{env.DATABASE_HOST or 'localhost'}:{env.DATABASE_PORT or '5432'}/{env.DATABASE}"
    
    async with AsyncPostgresSaver.from_conn_string(conn_string) as checkpointer:
        # Get latest checkpoint for each thread using optimized query
        print("🔍 Fetching latest checkpoints from database...")
        print("⚠️  This may take a few minutes with 100K+ threads...")
        print()
        
        # Sample approach: analyze a representative sample if too many threads
        async with checkpointer.conn.cursor() as cur:
            # First, count total threads
            await cur.execute("SELECT COUNT(DISTINCT thread_id) FROM checkpoints")
            total_threads = (await cur.fetchone())['count']
            print(f"📊 Found {total_threads:,} unique threads in database")
            
            # Decide on sampling strategy
            if total_threads > 10000:
                print(f"⚡ Using sampling strategy: analyzing random 5,000 threads")
                sample_size = 5000
                use_sampling = True
            else:
                sample_size = total_threads
                use_sampling = False
            
            # Get thread_ids (sampled or all)
            if use_sampling:
                await cur.execute(f"""
                    SELECT thread_id 
                    FROM (
                        SELECT DISTINCT thread_id 
                        FROM checkpoints
                    ) t
                    ORDER BY RANDOM()
                    LIMIT {sample_size}
                """)
            else:
                await cur.execute("""
                    SELECT DISTINCT thread_id 
                    FROM checkpoints 
                """)
            
            thread_ids = [row['thread_id'] for row in await cur.fetchall()]
        
        print(f"📈 Processing {len(thread_ids):,} threads...")
        print()
        
        # Storage for statistics
        stats_per_thread = []
        
        # Process in batches with progress updates
        batch_size = 100
        for batch_start in range(0, len(thread_ids), batch_size):
            batch_end = min(batch_start + batch_size, len(thread_ids))
            batch_ids = thread_ids[batch_start:batch_end]
            
            for idx_in_batch, thread_id in enumerate(batch_ids):
                idx = batch_start + idx_in_batch + 1
                
                # Progress update every 100 threads
                if idx % 100 == 0:
                    print(f"[{idx:,}/{len(thread_ids):,}] Processing...")
                
                # Get the latest checkpoint for this thread
                config = {"configurable": {"thread_id": thread_id}}
                checkpoint_tuple = await checkpointer.aget_tuple(config)
                
                if not checkpoint_tuple:
                    continue
                
                checkpoint = checkpoint_tuple.checkpoint
                messages = checkpoint.get('channel_values', {}).get('messages', [])
                
                if not messages:
                    continue
                
                # Analyze messages
                tool_message_count = 0
                tool_call_count = 0
                tool_context_tokens = 0
                total_tokens = 0
                
                for msg in messages:
                    msg_type = msg.__class__.__name__
                    
                    # Count total tokens
                    total_tokens += count_message_tokens(msg)
                    
                    # Count tool context
                    if msg_type == "ToolMessage":
                        tool_message_count += 1
                        tool_context_tokens += count_tool_context_tokens(msg)
                    
                    elif msg_type == "AIMessage":
                        if hasattr(msg, 'tool_calls') and msg.tool_calls:
                            tool_call_count += len(msg.tool_calls)
                            tool_context_tokens += count_tool_context_tokens(msg)
                
                # Store stats for this thread
                total_tool_messages = tool_message_count + tool_call_count
                stats_per_thread.append({
                    'thread_id': thread_id,
                    'tool_call_count': tool_call_count,
                    'tool_message_count': tool_message_count,
                    'total_tool_messages': total_tool_messages,
                    'tool_context_tokens': tool_context_tokens,
                    'total_tokens': total_tokens,
                    'total_messages': len(messages)
                })
        
        print()
        print("=" * 100)
        print("📊 ANALYSIS RESULTS")
        print("=" * 100)
        print()
        
        if not stats_per_thread:
            print("❌ No data collected!")
            return
        
        # Calculate statistics
        total_threads = len(stats_per_thread)
        
        # 1. Mean of tool message count (tool_calls + ToolMessages)
        mean_tool_message_count = sum(s['total_tool_messages'] for s in stats_per_thread) / total_threads
        
        # 2. Mean of tool context tokens
        mean_tool_context_tokens = sum(s['tool_context_tokens'] for s in stats_per_thread) / total_threads
        
        # 3. Mean of total tokens
        mean_total_tokens = sum(s['total_tokens'] for s in stats_per_thread) / total_threads
        
        # 4. Percentage of tool context tokens
        percentage_tool_tokens = (mean_tool_context_tokens / mean_total_tokens * 100) if mean_total_tokens > 0 else 0
        
        # Print results
        print(f"📈 NUMBER OF METRICS:")
        print(f"   • Threads analyzed: {total_threads}")
        print(f"   • Mean tool_calls per thread: {sum(s['tool_call_count'] for s in stats_per_thread) / total_threads:.2f}")
        print(f"   • Mean ToolMessages per thread: {sum(s['tool_message_count'] for s in stats_per_thread) / total_threads:.2f}")
        print(f"   • Mean TOTAL tool messages per thread: {mean_tool_message_count:.2f}")
        print()
        
        print(f"🎯 TOKEN METRICS:")
        print(f"   • Mean tool context tokens per thread: {mean_tool_context_tokens:.2f}")
        print(f"   • Mean total tokens per thread: {mean_total_tokens:.2f}")
        print(f"   • Tool context percentage: {percentage_tool_tokens:.2f}%")
        print()
        
        print("=" * 100)
        print("🎯 FINAL ANSWERS:")
        print("=" * 100)
        print(f"1. Mean of tool_call + ToolMessage count: {mean_tool_message_count:.2f} messages/thread")
        print(f"2. Mean of tool context tokens: {mean_tool_context_tokens:.2f} tokens/thread")
        print(f"3. Percentage of total tokens: {percentage_tool_tokens:.2f}%")
        print("=" * 100)
        print()
        
        # Additional insights
        print("📊 DISTRIBUTION:")
        # Sort by tool context tokens
        sorted_stats = sorted(stats_per_thread, key=lambda x: x['tool_context_tokens'], reverse=True)
        
        print("   Top 5 threads by tool context tokens:")
        for i, s in enumerate(sorted_stats[:5], 1):
            pct = (s['tool_context_tokens'] / s['total_tokens'] * 100) if s['total_tokens'] > 0 else 0
            print(f"   {i}. {s['thread_id']}: {s['tool_context_tokens']} tokens ({pct:.1f}% of {s['total_tokens']})")
        
        print()
        print("   Bottom 5 threads by tool context tokens:")
        for i, s in enumerate(sorted_stats[-5:], 1):
            pct = (s['tool_context_tokens'] / s['total_tokens'] * 100) if s['total_tokens'] > 0 else 0
            print(f"   {i}. {s['thread_id']}: {s['tool_context_tokens']} tokens ({pct:.1f}% of {s['total_tokens']})")
        
        print()


if __name__ == "__main__":
    asyncio.run(analyze_all_threads())
