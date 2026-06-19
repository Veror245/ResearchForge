docker exec -it researchforge-db psql -U forge -d researchforge -c "
TRUNCATE TABLE claims, research_findings, research_tasks CASCADE;
"

docker exec researchforge-redis redis-cli DEL research.tasks research.findings research.claims

