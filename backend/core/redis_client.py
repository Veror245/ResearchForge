import redis.asyncio as redis
from redis.exceptions import ResponseError
from backend.core.config import settings

# Our stream names (as defined earlier)
STREAM_TASKS = "research.tasks"
STREAM_FINDINGS = "research.findings"
STREAM_TASK_READY = "research.task_ready"
STREAM_CLAIMS = "research.claims"
STREAM_REPORTS = "research.reports"  # New stream for reports,

# We'll add more later (claims, critiques, etc.)

# Consumer group name for research workers
WORKER_GROUP = "research_workers"
CLAIM_GROUP = "claim_extractors"
REPORT_GROUP = "report_writers"

async def get_redis() -> redis.Redis:
    """Return a new Redis connection (use from_url or connection pool)."""
    return await redis.from_url(settings.REDIS_URL, decode_responses=True)

async def ensure_stream(rd: redis.Redis, stream: str):
    """Create stream if it doesn't exist (not strictly needed for XADD)."""
    pass  # XADD creates stream automatically

async def ensure_consumer_group(rd: redis.Redis, stream: str, group: str):
    """Create consumer group if it doesn't exist, ignoring BUSYGROUP.
    Always starts from '$' so only new messages are processed."""
    try:
        await rd.xgroup_create(stream, group, id="$", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

async def publish_message(rd: redis.Redis, stream: str, data: dict) -> str:
    """Publish a message to a Redis stream. Returns the message ID."""
    return await rd.xadd(stream, data, maxlen=10000) # type: ignore