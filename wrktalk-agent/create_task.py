import asyncio
import asyncpg
from datetime import datetime, timezone

async def create_deploy_task(artifact_id: str):
    """Create a deployment task in the database."""
    
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        database='wrktalk',
        user='wrktalk_user',
        password='wrktalk_password'
    )
    
    # Create task
    task_id = await conn.fetchval("""
        INSERT INTO agent_task (
            type, status, release_artifact_id, execute_after
        ) VALUES ($1, $2, $3, $4)
        RETURNING id
    """, 'deploy', 'pending', artifact_id, datetime.now(timezone.utc))
    
    print(f"✅ Deployment task created!")
    print(f"   Task ID: {task_id}")
    print(f"   Artifact ID: {artifact_id}")
    print(f"   Status: pending")
    
    await conn.close()
    return task_id

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python create_task.py <artifact_id>")
        sys.exit(1)
    
    artifact_id = sys.argv[1]
    task_id = asyncio.run(create_deploy_task(artifact_id))
    
    print(f"\n🚀 Task is ready for agent to pick up!")
