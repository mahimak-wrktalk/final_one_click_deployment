import asyncio
import asyncpg
import hashlib
from pathlib import Path

async def upload_chart(chart_path: str, release_version: str):
    """Upload Helm chart tarball to PostgreSQL."""
    
    # Read tarball bytes
    chart_data = Path(chart_path).read_bytes()
    
    # Calculate SHA256
    sha256 = hashlib.sha256(chart_data).hexdigest()
    
    print(f"�� Chart: {chart_path}")
    print(f"📏 Size: {len(chart_data)} bytes")
    print(f"🔐 SHA256: {sha256}")
    
    # Connect to database
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        database='wrktalk',
        user='wrktalk_user',
        password='wrktalk_password'
    )
    
    # Read values.yaml content
    values_data = None
    if Path('test-chart-simple/values.yaml').exists():
        values_data = Path('test-chart-simple/values.yaml').read_text()
    
    # Insert artifact
    artifact_id = await conn.fetchval("""
        INSERT INTO release_artifact (
            release_version, chart_type, artifact_data, 
            values_data, sha256, is_current, is_previous
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
    """, release_version, 'helm', chart_data, values_data, sha256, False, False)
    
    print(f"✅ Artifact uploaded! ID: {artifact_id}")
    
    await conn.close()
    return artifact_id

if __name__ == '__main__':
    chart_path = 'wrktalk-test-broken-3.0.0.tgz'
    release_version = 'wrktalk-test-broken-3.0.0'
    
    artifact_id = asyncio.run(upload_chart(chart_path, release_version))
    print(f"\n🎉 Chart uploaded successfully!")
    print(f"   Artifact ID: {artifact_id}")
