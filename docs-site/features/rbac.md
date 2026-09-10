# Role-based access control (RBAC)

RBAC answers "does your role allow this *action*" (create/list/read/update/delete on an entity),
as distinct from [Row-level security](rls.md), which answers "does this specific *row* belong to
you." The two compose: RBAC gates which callers can hit an endpoint at all; RLS (if also declared
on that entity) then filters which rows they see or can mutate.

For the exact YAML shape — `rbac.enabled`, `rbac.roles`, `rbac.default_permissions`, and the
per-entity `endpoints.rbac` override — see the
[Full field reference → `rbac`](../erd-reference/fields.md#rbac-rbacspec). This page explains the
mechanism at the feature level: how a `List[str]` of roles turns into an enforced dependency in
generated routes.

## The shape, briefly

```yaml
rbac:
  enabled: true
  roles: [admin, author, reader]
  default_permissions:
    read: [admin, author, reader]
    list: [admin, author, reader]
    create: [admin, author]
    update: [admin, author]
    delete: [admin]
```

`rbac.enabled: true` requires `auth.enabled: true` (RBAC needs a way to know who's calling) and
requires `"admin"` to be one of the declared `roles` — the auto-generated admin user-management
endpoints (see [Auth](auth.md#admin-user-management)) are hard-gated to that specific role name,
the same way `"User"` is a reserved entity name. `default_permissions` maps each of the 5 CRUD
actions to the roles allowed to perform it on any entity that doesn't override it; a per-entity
`endpoints.rbac` block overrides one or more actions for just that entity.

## How `require_roles(...)` gates a route

The generated dependency lives in `rbac/dependency.py.jinja` and is short enough to read in full:

```python
def require_roles(*roles: str) -> Callable:
    async def dependency(current_user: User = Depends(_auth_service.get_current_user)) -> User:
        user_roles: List[str] = current_user.roles or []
        if not set(user_roles) & set(roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(roles)}",
            )
        return current_user

    return dependency
```

`require_roles("admin", "author")` builds a FastAPI dependency that first resolves the caller
through `get_current_user` (so an unauthenticated caller gets 401, not 403 — 403 is only reached
once identity is established), then 403s unless the user's `roles` list intersects the required
set. It returns the resolved `User`, so a route can both gate on roles *and* get the caller's
identity in one dependency — used directly by RLS's `auth_user` identity source (see
[RLS → bypass roles](rls.md#bypass-roles)) to avoid a second, redundant auth lookup.

In generated route templates (`service/module_routes.py.jinja`), this shows up per-action as:

```python
dependencies=[Depends(require_roles("admin", "author"))],
```

on the route decorator, wired from either the entity's `endpoints.rbac` override or the global
`rbac.default_permissions` for that action — whichever applies, resolved once at generation time,
not per-request.

## First-user bootstrap

RBAC gates every action behind declared roles, which creates a chicken-and-egg problem: with
every new user getting `roles: []`, nobody could ever access anything, including no way to grant
the first role. The convention, verified directly against the live `register_user` template
(`app/templates/Python/auth/service.py.jinja` lines 85–98), is that the very first user
registered gets **every** declared role, and only subsequent registrations get `roles: []`:

```python
is_first_user = db.query(User).count() == 0  # (or the async equivalent)
roles = {{ project.rbac_roles|tojson }} if is_first_user else []
```

An admin (which the first user now is, since `admin` is always one of `rbac.roles` when RBAC is
on) grants roles to everyone after that via `PUT /auth/users/{id}/roles`.

This same `is_first_user` computation is reused — not re-derived — by the `admin_approval`
registration mode's own bootstrap fix (auto-approving the first user so they aren't locked out
with no admin yet able to approve them); see
[Auth → admin user management](auth.md#admin-user-management) for that interaction in full,
rather than repeating it here.
