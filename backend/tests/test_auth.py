from fastapi.testclient import TestClient


def test_register_login_and_me(client: TestClient) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"username": "tester", "password": "secret12"},
    )
    assert register_response.status_code == 201
    register_data = register_response.json()
    assert register_data["username"] == "tester"
    assert "id" in register_data
    assert "password" not in register_data
    assert "password_hash" not in register_data

    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "tester", "password": "secret12"},
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    assert login_data["token_type"] == "bearer"
    assert login_data["user"]["username"] == "tester"
    assert isinstance(login_data["access_token"], str)
    assert login_data["access_token"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login_data['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "tester"


def test_register_duplicate_username(client: TestClient) -> None:
    payload = {"username": "duplicate", "password": "secret12"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    duplicate_response = client.post("/api/v1/auth/register", json=payload)
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "Username already exists"


def test_login_invalid_credentials(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"username": "auth_user", "password": "secret12"},
    )

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"username": "auth_user", "password": "wrongpass"},
    )
    assert wrong_password.status_code == 401

    wrong_user = client.post(
        "/api/v1/auth/login",
        json={"username": "missing", "password": "secret12"},
    )
    assert wrong_user.status_code == 401


def test_me_requires_valid_token(client: TestClient) -> None:
    unauthorized = client.get("/api/v1/auth/me")
    assert unauthorized.status_code == 403

    invalid_token = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert invalid_token.status_code == 401


def test_register_validation(client: TestClient) -> None:
    short_username = client.post(
        "/api/v1/auth/register",
        json={"username": "ab", "password": "secret12"},
    )
    assert short_username.status_code == 422

    short_password = client.post(
        "/api/v1/auth/register",
        json={"username": "valid_user", "password": "123"},
    )
    assert short_password.status_code == 422
