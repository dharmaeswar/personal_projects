from gateway.router import Backend, ModelRegistry, Router


def _registry():
    registry = ModelRegistry()
    registry.register(Backend("fast", "llama-4-scout", 100.0, 10))
    registry.register(Backend("slow", "llama-4-scout", 300.0, 10))
    return registry


def test_routes_to_lowest_latency_when_headroom_equal():
    router = Router(_registry())
    backend, reason = router.route("llama-4-scout")
    assert reason == "ok" and backend.backend_id == "fast"
    backend.release()


def test_routes_to_headroom_when_one_backend_busy():
    registry = _registry()
    fast = registry.backends_for("llama-4-scout")[0]
    for _ in range(9):
        assert fast.acquire() is True  # 9/10 in flight, 10% headroom
    router = Router(registry)
    backend, reason = router.route("llama-4-scout")
    assert reason == "ok" and backend.backend_id == "slow"
    backend.release()
    for _ in range(9):
        fast.release()


def test_fails_over_when_backend_unhealthy():
    registry = _registry()
    registry.backends_for("llama-4-scout")[0].healthy = False
    router = Router(registry)
    backend, reason = router.route("llama-4-scout")
    assert reason == "ok" and backend.backend_id == "slow"
    backend.release()


def test_unknown_model():
    router = Router(_registry())
    backend, reason = router.route("gpt-nope")
    assert backend is None and reason == "unknown_model"


def test_no_capacity_when_all_full():
    registry = _registry()
    for backend in registry.backends_for("llama-4-scout"):
        for _ in range(backend.capacity):
            assert backend.acquire() is True
    router = Router(registry)
    backend, reason = router.route("llama-4-scout")
    assert backend is None and reason == "no_capacity"
