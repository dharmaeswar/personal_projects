# Deployment — AWS EKS

How this app ships to a Kubernetes cluster (Amazon EKS), matching the
deploy-and-support flow of a servicing full-stack role: container images
built in CI, applied with `kubectl`, health-checked by the Service probes.

No live cluster was used to write these files. The manifests are valid YAML
(checked with a parser) and the Dockerfiles follow the same build commands
the project already runs locally (`mvn test package`, `npm run build`).
Swap the placeholder ECR image names for a real registry before applying.

## Build the images

```bash
# From the project root. -f points at the Dockerfile; the trailing directory
# is the build context, so the Dockerfiles' COPY lines resolve inside it:
docker build -f deploy/docker/backend.Dockerfile -t mortgage-servicing-backend:1.0.0 backend
docker build -f deploy/docker/frontend.Dockerfile -t mortgage-servicing-frontend:1.0.0 frontend
```

## Push to ECR and deploy

```bash
aws ecr get-login-password --region <region> \
  | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker tag mortgage-servicing-backend:1.0.0 <account>.dkr.ecr.<region>.amazonaws.com/mortgage-servicing-backend:1.0.0
docker tag mortgage-servicing-frontend:1.0.0 <account>.dkr.ecr.<region>.amazonaws.com/mortgage-servicing-frontend:1.0.0
docker push <account>.dkr.ecr.<region>.amazonaws.com/mortgage-servicing-backend:1.0.0
docker push <account>.dkr.ecr.<region>.amazonaws.com/mortgage-servicing-frontend:1.0.0

# Update the `image:` lines in deploy/k8s/*.yaml to the ECR tags, then:
kubectl apply -f deploy/k8s/backend.yaml
kubectl apply -f deploy/k8s/frontend.yaml
kubectl get pods -l app=mortgage-servicing-backend
kubectl get pods -l app=mortgage-servicing-frontend
```

## What the manifests do

- `deploy/k8s/backend.yaml` — 2-replica Deployment of the Spring Boot API
  (CPU/memory requests and limits) + a ClusterIP Service on port 8080.
  Readiness/liveness probes hit `GET /api/loans`, which returns 200 with an
  empty list on a healthy instance; the app has no actuator endpoint, so no
  actuator path is probed.
- `deploy/k8s/frontend.yaml` — 2-replica Deployment of the nginx-served React
  bundle + a ClusterIP Service on port 80. nginx proxies `/api/` to the
  backend Service (`frontend/nginx.conf`), so the browser talks to one host.
- Rolling updates are the Deployment default (`maxUnavailable: 25%`), so a
  new image rolls out without dropping the Service.
