from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app


def run() -> None:
    client = TestClient(app)

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    admin_email = f"admin_{suffix}@example.com"
    admin_password = "AdminPass123"

    steps: list[tuple] = []

    r = client.post(
        "/api/v1/super-admins",
        json={"name": "Admin Smoke", "email": admin_email, "password": admin_password},
    )
    steps.append(("create_super_admin", r.status_code))
    assert r.status_code == 201, r.text

    r = client.post(
        "/api/v1/auth/super-admin/login",
        json={"email": admin_email, "password": admin_password},
    )
    steps.append(("login_super_admin", r.status_code))
    assert r.status_code == 200, r.text
    super_token = r.json()["access_token"]

    r = client.post(
        "/api/v1/tenants",
        json={"name": "Tenant Smoke", "phone": "3001234567", "slot_duration": 20},
        headers={"Authorization": f"Bearer {super_token}"},
    )
    steps.append(("create_tenant", r.status_code))
    assert r.status_code == 201, r.text
    tenant_id = r.json()["id"]

    r = client.get(
        f"/api/v1/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {super_token}"},
    )
    steps.append(("get_tenant", r.status_code))
    assert r.status_code == 200, r.text

    r = client.patch(
        f"/api/v1/tenants/{tenant_id}",
        json={"name": "Tenant Smoke Updated"},
        headers={"Authorization": f"Bearer {super_token}"},
    )
    steps.append(("patch_tenant", r.status_code))
    assert r.status_code == 200, r.text

    tenant_token = create_access_token({"sub": str(uuid4()), "tenant_id": tenant_id})
    user_email = f"user_{suffix}@example.com"

    r = client.post(
        "/api/v1/users",
        json={"email": user_email, "name": "User Smoke", "password": "UserPass123", "role": "staff"},
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    steps.append(("create_user", r.status_code))
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]

    r = client.get(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    steps.append(("get_user", r.status_code))
    assert r.status_code == 200, r.text

    r = client.patch(
        f"/api/v1/users/{user_id}",
        json={"name": "User Smoke Updated"},
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    steps.append(("patch_user", r.status_code))
    assert r.status_code == 200, r.text

    r = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    steps.append(("list_users", r.status_code, len(r.json())))
    assert r.status_code == 200, r.text

    r = client.delete(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    steps.append(("delete_user", r.status_code))
    assert r.status_code == 204, r.text

    r = client.get(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    steps.append(("get_user_after_delete", r.status_code, r.json().get("is_active")))
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False

    print("SMOKE_OK")
    print("tenant_id=", tenant_id)
    print("user_id=", user_id)
    for step in steps:
        print(step)


if __name__ == "__main__":
    run()
