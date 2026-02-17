# Backend Modules

This folder contains Python runtime modules split by architectural boundary.

- `control_plane`: API and orchestration control paths.
- `gateway`: query gateway enforcement path.
- `workers`: discovery/profiling/build worker paths.
- `shared_domain`: shared domain models and boundary-safe primitives.

Boundary enforcement is checked by `tools/check_boundary_fitness.py`.
