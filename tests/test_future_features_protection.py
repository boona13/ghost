import json


def test_load_config_forces_enable_future_features_true(tmp_path, monkeypatch):
    import ghost

    cfg_path = tmp_path / "config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps({"model": "x", "enable_future_features": False}),
        encoding="utf-8",
    )

    monkeypatch.setattr(ghost, "CONFIG_FILE", cfg_path)

    loaded = ghost.load_config()

    assert loaded["enable_future_features"] is True


def test_config_patch_rejects_disabling_enable_future_features():
    from ghost_config_tool import build_config_tools

    config_patch = next(t for t in build_config_tools() if t["name"] == "config_patch")

    raw = config_patch["execute"]({"enable_future_features": False})
    payload = json.loads(raw)

    assert payload["ok"] is False
    assert "cannot be false" in payload["error"]


def test_dashboard_config_put_rejects_disabling_enable_future_features():
    import ghost_dashboard

    app = ghost_dashboard.create_app()
    client = app.test_client()

    resp = client.put(
        "/api/config",
        json={"enable_future_features": False},
    )

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["ok"] is False
    assert "cannot be disabled" in body["error"]
