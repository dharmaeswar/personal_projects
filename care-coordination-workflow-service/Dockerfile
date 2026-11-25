# Care Coordination Workflow Service — demo container.
# Standard-library-only service, so the image needs no dependency install.
# Build:  docker build -t care-coordination-workflow-service .
# Run:    docker run --rm -p 8000:8000 care-coordination-workflow-service
FROM python:3.12-slim

WORKDIR /app
COPY care_coord/ care_coord/
COPY run_demo.py .

# Fail the build if the demo workflow does not run end to end.
RUN python run_demo.py > /tmp/demo.log

EXPOSE 8000
CMD ["python", "run_demo.py", "--serve"]
