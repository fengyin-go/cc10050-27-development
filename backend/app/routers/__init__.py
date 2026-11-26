"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。"""
from __future__ import annotations

from app.routers import resource, spec_sync

# spec_sync 含 /api/spec-sync/... 固定前缀，必须先于通用 /api/{module} 注册，
# 否则两段路径会被 /api/{module}/{entry_id} 抢先匹配。
ROUTERS = [spec_sync, resource]
