"""
Script to delete the latest N reasoning engines from Vertex AI.
Useful for cleaning up development/test deployments.

Usage:
    uv run src/cleanup_reasoning_engines.py [--count N]

Examples:
    uv run src/cleanup_reasoning_engines.py           # Delete latest 10
    uv run src/cleanup_reasoning_engines.py --count 5 # Delete latest 5

    # Delete latest 10 (default)
    uv run src/cleanup_reasoning_engines.py

    # Delete latest 5
    uv run src/cleanup_reasoning_engines.py --count 5

    # Dry run (see what would be deleted without actually deleting)
    uv run src/cleanup_reasoning_engines.py --dry-run

    # Just list all reasoning engines
    uv run src/cleanup_reasoning_engines.py --list-all
"""

import argparse
from datetime import datetime

import vertexai
from vertexai import agent_engines

from src.config import env


def list_reasoning_engines():
    """List all reasoning engines sorted by creation time (oldest first)."""
    vertexai.init(project=env.PROJECT_ID, location=env.LOCATION)
    
    print(f"Listing reasoning engines in project {env.PROJECT_ID}, location {env.LOCATION}...")
    
    # List all reasoning engines
    engines = list(agent_engines.list())
    
    # Sort by creation time (oldest first)
    engines_sorted = sorted(
        engines,
        key=lambda x: x.create_time if hasattr(x, 'create_time') else datetime.min,
    )
    
    return engines_sorted


def delete_reasoning_engines(count=10, dry_run=False, allow_cross_project=False):
    """Delete the latest N reasoning engines.
    
    Args:
        count: Number of engines to delete
        dry_run: If True, only list what would be deleted without actually deleting
        allow_cross_project: If True, attempt to delete cross-project resources (may fail)
    """
    engines = list_reasoning_engines()
    
    if not engines:
        print("No reasoning engines found.")
        return
    
    print(f"\nTotal reasoning engines: {len(engines)}")
    print(f"{'DRY RUN - ' if dry_run else ''}Will delete the oldest {count} engine(s):\n")
    
    engines_to_delete = engines[:count]
    
    for i, engine in enumerate(engines_to_delete, 1):
        engine_id = engine.name.split('/')[-1]
        create_time = engine.create_time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(engine, 'create_time') else "Unknown"
        display_name = engine.display_name if hasattr(engine, 'display_name') else "Unknown"
        
        # Extract project info from resource name
        resource_project = engine.name.split('/')[1] if '/' in engine.name else "Unknown"
        
        print(f"{i}. ID: {engine_id}")
        print(f"   Name: {display_name}")
        print(f"   Created: {create_time}")
        print(f"   Project: {resource_project}")
        print()
    
    # Confirmation prompt for non-dry-run mode
    if not dry_run:
        print(f"\n⚠️  You are about to delete {len(engines_to_delete)} reasoning engine(s)!")
        confirmation = input("Type 'DELETE' to confirm: ").strip()
        
        if confirmation != "DELETE":
            print("\nDeletion cancelled.")
            return
        
        print("\nProceeding with deletion...\n")
        
        # Now actually delete
        for i, engine in enumerate(engines_to_delete, 1):
            engine_id = engine.name.split('/')[-1]
            display_name = engine.display_name if hasattr(engine, 'display_name') else "Unknown"
            
            print(f"{i}. {display_name} (ID: {engine_id})")
            print(f"   Resource name: {engine.name}")
            
            # Extract project from resource name
            resource_project = engine.name.split('/')[1] if '/' in engine.name else "Unknown"
            current_project = env.PROJECT_ID
            
            # Check if this is a cross-project resource
            if resource_project != current_project and resource_project != "Unknown":
                print(f"   ⚠️  Cross-project resource detected!")
                print(f"   Resource project: {resource_project}")
                print(f"   Current project: {current_project}")
                
                if not allow_cross_project:
                    print(f"   Skipping deletion - would require project switch")
                    print(f"   💡 To delete this resource, either:")
                    print(f"      1. Switch to project '{resource_project}' and run the script")
                    print(f"      2. Use: gcloud config set project {resource_project}")
                    print(f"      3. Run with --allow-cross-project (may fail with permission errors)")
                    print()
                    continue
                else:
                    print(f"   ⚠️  Attempting cross-project deletion (may fail)...")
            
            print(f"   Deleting...", end=" ")
            try:
                # Use the resource name directly from the engine object
                agent_engines.delete(engine.name)
                print("✓ Deleted")
            except Exception as e:
                error_msg = str(e)
                print(f"✗ Failed: {error_msg}")
                # If permission error, provide more context
                if "403" in error_msg or "Permission denied" in error_msg:
                    print(f"   ℹ️  This may be a cross-project resource. Check if the engine was created in a different project.")
                    print(f"   ℹ️  Current project: {env.PROJECT_ID}")
                    if resource_project != "Unknown":
                        print(f"   ℹ️  Resource project: {resource_project}")
            print()
        
        print(f"\nDeleted {len(engines_to_delete)} reasoning engine(s).")
    else:
        print(f"\nDRY RUN completed. Run without --dry-run to actually delete.")


def main():
    parser = argparse.ArgumentParser(
        description="Delete the oldest N reasoning engines from Vertex AI"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of oldest engines to delete (default: 10)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be deleted without actually deleting"
    )
    parser.add_argument(
        "--allow-cross-project",
        action="store_true",
        help="Attempt to delete cross-project resources (may fail with permission errors)"
    )
    parser.add_argument(
        "--list-all",
        action="store_true",
        help="Just list all reasoning engines without deleting"
    )
    
    args = parser.parse_args()
    
    if args.list_all:
        engines = list_reasoning_engines()
        current_project = env.PROJECT_ID
        cross_project_engines = []
        same_project_engines = []
        
        for engine in engines:
            resource_project = engine.name.split('/')[1] if '/' in engine.name else "Unknown"
            if resource_project != current_project and resource_project != "Unknown":
                cross_project_engines.append(engine)
            else:
                same_project_engines.append(engine)
        
        print(f"\nTotal reasoning engines: {len(engines)}")
        print(f"Same project ({current_project}): {len(same_project_engines)}")
        print(f"Cross-project: {len(cross_project_engines)}\n")
        
        if same_project_engines:
            print(f"=== Engines in current project ({current_project}) ===")
            for i, engine in enumerate(same_project_engines, 1):
                engine_id = engine.name.split('/')[-1]
                create_time = engine.create_time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(engine, 'create_time') else "Unknown"
                display_name = engine.display_name if hasattr(engine, 'display_name') else "Unknown"
                print(f"{i}. {display_name}")
                print(f"   ID: {engine_id}")
                print(f"   Created: {create_time}")
                print()
        
        if cross_project_engines:
            print("=== Cross-project engines (cannot delete directly) ===")
            for i, engine in enumerate(cross_project_engines, 1):
                engine_id = engine.name.split('/')[-1]
                create_time = engine.create_time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(engine, 'create_time') else "Unknown"
                display_name = engine.display_name if hasattr(engine, 'display_name') else "Unknown"
                resource_project = engine.name.split('/')[1] if '/' in engine.name else "Unknown"
                print(f"{i}. {display_name}")
                print(f"   ID: {engine_id}")
                print(f"   Project: {resource_project}")
                print(f"   Created: {create_time}")
                print()
    else:
        delete_reasoning_engines(count=args.count, dry_run=args.dry_run, allow_cross_project=args.allow_cross_project)


if __name__ == "__main__":
    main()
