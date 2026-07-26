# Role and Branch-Isolation Matrix

This records current intended authorization. Endpoint tests remain the enforcement evidence; this document is not itself security control.

| Capability | Customer | Staff | Inventory manager | Branch manager | Super admin | Rider profile |
|---|---:|---:|---:|---:|---:|---:|
| Browse catalog/branches/zones | Yes | Yes | Yes | Yes | Yes | Yes |
| Maintain own account/cart | Yes | No | No | No | No | No |
| Online checkout / own order tracking | Yes | No | No | No | No | No |
| Process walk-in POS sale | No | Own branch | No | Own branch | Selected branch | No |
| Apply/authorize POS discount | No | No | No | Own branch | Any branch | No |
| Void walk-in sale | No | Initiates only | No | Own branch approval | Any branch | No |
| Manual stock operations | No | No | Operational scope | Own branch | Any branch | No |
| Request/accept transfer | No | No | No | Own branch boundary | Any branch | No |
| View branch reports | No | No | No | Own branch | Any branch | No |
| Assign delivery rider | No | No | No | Own branch | Any branch | No |
| Update assigned delivery | No | No | No | Administrative access | Administrative access | Own assignments |
| Confirm pickup code | No | Own branch | Own branch | Own branch | Requires explicit branch context | No |
| Moderate branch returns | No | No | No | Own branch | Any branch | No |

## Known authorization design debt

- Permission classes are duplicated across apps instead of residing in one authorization module.
- `INVENTORY_MANAGER` is branch-bound at both model-validation and database-constraint levels as of Phase 1.5.
- Super-admin flows that act on a branch need an explicit selected-branch context; an unscoped global session must not silently mutate a branch.
- Rider identity is profile-based rather than a user role. This is valid, but all rider endpoints must check assignment ownership as well as profile existence.
