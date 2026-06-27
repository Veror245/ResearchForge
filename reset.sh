docker exec -it researchforge-db psql -U forge -d researchforge -c "
DROP TABLE  claims, research_findings, research_tasks, research_jobs, research_reports, critiques, skeptical_claims, optimistic_claims CASCADE;"

docker exec -it researchforge-db psql -U forge -d researchforge -c "
TRUNCATE TABLE claims, research_findings, research_tasks CASCADE;
"

# Delete the streams themselves
docker exec researchforge-redis redis-cli DEL research.tasks research.findings research.task_ready research.claims

# Delete the consumer groups (they’ll be recreated on restart)
docker exec researchforge-redis redis-cli FLUSHALL
docker exec researchforge-redis redis-cli DEL research.tasks research.findings research.task_ready research.claims
docker exec researchforge-redis redis-cli XGROUP DESTROY research.tasks research_workers
docker exec researchforge-redis redis-cli XGROUP DESTROY research.task_ready claim_extractors

