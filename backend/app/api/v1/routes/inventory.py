"""Protected inventory read API. Operational write actions are intentionally absent."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.authorization import Principal, require_permission
from app.core.permission_catalog import Capability
from app.db.session import get_db_session
from app.schemas.inventory import (
    AssetPage,
    AssetRead,
    CategoryRead,
    MasterDataRead,
    PageQuery,
    ProductPage,
    ProductRead,
    QuantityBalanceRead,
    ReceiptPage,
)
from app.services.inventory import (
    get_asset,
    get_product,
    list_assets,
    list_categories,
    list_locations,
    list_products,
    list_quantity_balances,
    list_receipts,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/products", response_model=ProductPage)
def products(query: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
             category_id: UUID | None = None,
             limit: Annotated[int, Query(ge=1, le=100)] = 25, offset: Annotated[int, Query(ge=0, le=10000)] = 0,
             principal: Principal = Depends(require_permission(Capability.PRODUCTS_READ)),
             session: Session = Depends(get_db_session)) -> ProductPage:
    del principal
    return list_products(session, limit=limit, offset=offset, query=query, category_id=category_id)


@router.get("/categories", response_model=list[CategoryRead])
def categories(
    principal: Principal = Depends(require_permission(Capability.PRODUCTS_READ)),
    session: Session = Depends(get_db_session),
) -> list[CategoryRead]:
    del principal
    return [CategoryRead(id=row.id, code=row.code, name=row.name, tracking_mode=row.tracking_mode)
            for row in list_categories(session)]


@router.get("/locations", response_model=list[MasterDataRead])
def locations(
    principal: Principal = Depends(require_permission(Capability.ASSETS_READ)),
    session: Session = Depends(get_db_session),
) -> list[MasterDataRead]:
    del principal
    return [MasterDataRead(id=row.id, code=row.code, name=row.name) for row in list_locations(session)]


@router.get("/products/{product_id}", response_model=ProductRead)
def product_detail(
    product_id: UUID,
    principal: Principal = Depends(require_permission(Capability.PRODUCTS_READ)),
    session: Session = Depends(get_db_session),
) -> ProductRead:
    del principal
    return get_product(session, product_id)


@router.get("/assets", response_model=AssetPage)
def assets(filters: Annotated[PageQuery, Query()],
           principal: Principal = Depends(require_permission(Capability.ASSETS_READ)),
           session: Session = Depends(get_db_session)) -> AssetPage:
    del principal
    return list_assets(session, filters)


@router.get("/quantity-balances", response_model=list[QuantityBalanceRead])
def quantity_balances(location_id: UUID | None = None,
                      principal: Principal = Depends(require_permission(Capability.QUANTITY_INVENTORY_READ)),
                      session: Session = Depends(get_db_session)) -> list[QuantityBalanceRead]:
    del principal
    return list_quantity_balances(session, location_id=location_id)


@router.get("/assets/{asset_id}", response_model=AssetRead)
def asset_detail(asset_id: UUID,
                 principal: Principal = Depends(require_permission(Capability.ASSETS_READ)),
                 session: Session = Depends(get_db_session)) -> AssetRead:
    del principal
    return get_asset(session, asset_id)


@router.get("/receipts", response_model=ReceiptPage)
def receipts(limit: Annotated[int, Query(ge=1, le=100)] = 25,
             offset: Annotated[int, Query(ge=0, le=10000)] = 0,
             location_id: UUID | None = None,
             principal: Principal = Depends(require_permission(Capability.RECEIPTS_READ)),
             session: Session = Depends(get_db_session)) -> ReceiptPage:
    del principal
    return list_receipts(session, limit=limit, offset=offset, location_id=location_id)
