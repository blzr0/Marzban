from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app import logger
from app.db import Session, crud, get_db
from app.dependencies import get_validated_user
from app.models.admin import Admin
from app.models.hwid import (
    SubscriptionLogResponse,
    SubscriptionLogsResponse,
    SubscriptionLogStatus,
    UserHWIDsResponse,
)
from app.models.user import UserResponse
from app.utils import responses

router = APIRouter(tags=["HWID"], prefix="/api", responses={401: responses._401})


@router.get("/user/{username}/hwids", response_model=UserHWIDsResponse,
            responses={403: responses._403, 404: responses._404})
def get_user_hwids(
    db: Session = Depends(get_db),
    dbuser: UserResponse = Depends(get_validated_user),
):
    """Devices (x-hwid) bound to the user, most recently seen first."""
    return {"hwids": crud.get_user_hwids(db, dbuser), "hwid_limit": dbuser.hwid_limit}


@router.delete("/user/{username}/hwids/{hwid_id}", responses={403: responses._403, 404: responses._404})
def remove_user_hwid(
    hwid_id: int,
    db: Session = Depends(get_db),
    dbuser: UserResponse = Depends(get_validated_user),
    admin: Admin = Depends(Admin.get_current),
):
    """Unbind one device, freeing a slot under the user's hwid_limit."""
    if not crud.remove_user_hwid(db, dbuser, hwid_id):
        raise HTTPException(status_code=404, detail="Device not found")
    logger.info(f'Device {hwid_id} of user "{dbuser.username}" removed by admin "{admin.username}"')
    return {"detail": "Device removed"}


@router.delete("/user/{username}/hwids", responses={403: responses._403, 404: responses._404})
def reset_user_hwids(
    db: Session = Depends(get_db),
    dbuser: UserResponse = Depends(get_validated_user),
    admin: Admin = Depends(Admin.get_current),
):
    """Unbind all of the user's devices."""
    count = crud.remove_user_hwids(db, dbuser)
    logger.info(f'{count} devices of user "{dbuser.username}" removed by admin "{admin.username}"')
    return {"detail": f"{count} devices removed"}


@router.get("/subscription-logs", response_model=SubscriptionLogsResponse)
def get_subscription_logs(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    username: Optional[str] = None,
    hwid: Optional[str] = None,
    status: Optional[SubscriptionLogStatus] = None,
    db: Session = Depends(get_db),
    admin: Admin = Depends(Admin.get_current),
):
    """Subscription fetches, newest first. `username` and `hwid` match
    substrings. Non-sudo admins only see their own users."""
    rows, total = crud.get_subscription_logs(
        db, offset=offset, limit=limit, username=username, hwid=hwid, status=status,
        admin=None if admin.is_sudo else crud.get_admin(db, admin.username),
    )
    logs = [
        SubscriptionLogResponse(
            id=log.id, username=log_username, status=log.status, hwid=log.hwid,
            device_os=log.device_os, os_version=log.os_version, device_model=log.device_model,
            user_agent=log.user_agent, ip=log.ip, host=log.host, request_path=log.request_path,
            count=log.count, created_at=log.created_at, updated_at=log.updated_at,
        )
        for log, log_username in rows
    ]
    return {"logs": logs, "total": total}
