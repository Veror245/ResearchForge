import asyncio
from unittest import result
from sqlalchemy import text
from backend.core.database import engine, async_session
from backend.models.base import Base

# Import all models so Base.metadata knows about them
from backend.models.research_task import ResearchTask      # noqa: F401
from backend.models.research_finding import ResearchFinding  # noqa: F401

async def init_db():
    async with engine.begin() as conn:
        # Enable pgvector extension if not already
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Database tables created successfully.")
        result = await conn.execute(text("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'research_findings'
    ORDER BY ordinal_position
"""))

    print([r[0] for r in result.fetchall()])
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_db())
    print(ResearchFinding.__table__.columns.keys())