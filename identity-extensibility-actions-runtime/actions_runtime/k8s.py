"""Kubernetes manifests for the runtime (generated as data).

The Actions runtime runs as a containerised service: one Deployment per
region, a ClusterIP Service in front of it, and a HorizontalPodAutoscaler
on CPU and on custom `actions_invocations_per_second`. Resource requests
and limits are set so a burst of tenant actions cannot starve the
control plane, and pods spread across zones with anti-affinity.
"""

DEPLOYMENT_YAML = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: actions-runtime
  namespace: {namespace}
spec:
  replicas: 3
  selector:
    matchLabels:
      app: actions-runtime
  template:
    metadata:
      labels:
        app: actions-runtime
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: actions-runtime
              topologyKey: topology.kubernetes.io/zone
      containers:
      - name: actions-runtime
        image: actions-runtime:{image_tag}
        ports:
        - containerPort: 8080
        resources:
          requests:
            cpu: "500m"
            memory: "512Mi"
          limits:
            cpu: "2000m"
            memory: "2Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          periodSeconds: 5
"""

SERVICE_YAML = """apiVersion: v1
kind: Service
metadata:
  name: actions-runtime
  namespace: {namespace}
spec:
  type: ClusterIP
  selector:
    app: actions-runtime
  ports:
  - port: 80
    targetPort: 8080
"""

HPA_YAML = """apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: actions-runtime
  namespace: {namespace}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: actions-runtime
  minReplicas: 3
  maxReplicas: 30
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
"""


def render_manifests(namespace: str = "actions", image_tag: str = "latest") -> dict[str, str]:
    return {
        "deployment.yaml": DEPLOYMENT_YAML.format(namespace=namespace, image_tag=image_tag),
        "service.yaml": SERVICE_YAML.format(namespace=namespace),
        "hpa.yaml": HPA_YAML.format(namespace=namespace),
    }
