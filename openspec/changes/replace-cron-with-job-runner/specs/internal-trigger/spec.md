## REMOVED Requirements

### Requirement: Trigger Secret Is Required
**Reason**: The capability's only consumers were `product-monitoring`'s five cadence endpoints, which this change retires in favour of scheduled jobs running inside the deployment. With no endpoint invoked by internal automation, there is no request for a shared secret to guard.

**Migration**: `shared/infrastructure/driving/trigger_guard.py` and its tests are deleted. `TRIGGER_SECRET` is removed from the settings model and from `deploy.yml`'s `.env` render step, and may then be deleted as a GitHub Actions `production` secret. No external caller is affected: the only client was the `cron` container, removed by the same change.

### Requirement: Correct Secret Is Accepted
**Reason**: Part of the same guard; removed with it.

**Migration**: See above.

### Requirement: Secret Comparison Is Constant-Time
**Reason**: Part of the same guard; removed with it. The property was correct and remains the right approach should a shared-secret guard ever be needed again — it is recorded here and in the archived change rather than kept alive as unused code.

**Migration**: See above.

### Requirement: Guard Fails Closed When Unconfigured
**Reason**: Part of the same guard; removed with it. Note this requirement is cited by `runtime-configuration`'s "Every Variable The Runtime Requires Is Declared In One Place", as the example justifying a direct `os.environ` read where per-request tolerance of absence is required behavior. That citation becomes stale; the permission it illustrates does not, and other readers rely on it — `LOG_LEVEL` and `DATABASE_URL` both read directly for reasons of their own.

**Migration**: this change carries a `MODIFIED` delta for that `runtime-configuration` requirement, restating the illustrative example in terms of the variables that actually rely on the permission today — the logging threshold and the database connection setting. The permission's condition is generalised along with it: from "where per-request tolerance of absence is itself required behavior", which was written for this guard and covers neither remaining reader once it is gone, to "where routing it through the declaration would defeat required behavior". A wider class of direct reads, deliberately.
