"""Read-only inventory query services. Transactional stock writes stay gated."""
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    AssetCategory,
    InventoryBalance,
    InventoryProduct,
    Location,
    Receipt,
    TrackedAsset,
)
from app.schemas.inventory import (
    AssetPage,
    AssetRead,
    PageQuery,
    ProductPage,
    ProductRead,
    QuantityBalanceRead,
    ReceiptPage,
    ReceiptRead,
)


def _database_failure(session: Session, message: str) -> None:
    try:
        session.rollback()
    except SQLAlchemyError:
        pass
    raise AppError("DATABASE_UNAVAILABLE", message, 503) from None


def list_products(session: Session, *, limit: int = 25, offset: int = 0, query: str | None = None,
                  category_id=None) -> ProductPage:
    clauses = []
    if category_id is not None:
        clauses.append(InventoryProduct.category_id == category_id)
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        clauses.append(or_(InventoryProduct.name.ilike(pattern, escape="\\"),
                           InventoryProduct.sku.ilike(pattern, escape="\\")))
    try:
        total = session.scalar(select(func.count()).select_from(InventoryProduct).where(*clauses)) or 0
        rows = session.execute(select(InventoryProduct, AssetCategory.name).join(
            AssetCategory, AssetCategory.id == InventoryProduct.category_id).where(*clauses)
            .order_by(InventoryProduct.name, InventoryProduct.id).limit(limit).offset(offset)).all()
        items = [ProductRead(id=row.id, category_id=row.category_id, category_name=category_name,
            sku=row.sku, name=row.name, brand=row.brand, model=row.model,
            specifications=row.specifications, active=row.active) for row, category_name in rows]
        return ProductPage(items=items, total=total,
                           limit=limit, offset=offset)
    except SQLAlchemyError:
        _database_failure(session, "Product catalog is unavailable.")


def list_assets(session: Session, filters: PageQuery) -> AssetPage:
    clauses = []
    if filters.category_id:
        clauses.append(InventoryProduct.category_id == filters.category_id)
    if filters.location_id:
        clauses.append(TrackedAsset.location_id == filters.location_id)
    if filters.lifecycle_status:
        clauses.append(TrackedAsset.lifecycle_status == filters.lifecycle_status)
    if filters.q:
        pattern = "%" + filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        clauses.append(or_(TrackedAsset.asset_number.ilike(pattern, escape="\\"),
                           InventoryProduct.name.ilike(pattern, escape="\\"),
                           InventoryProduct.sku.ilike(pattern, escape="\\")))
    query = select(TrackedAsset, InventoryProduct, AssetCategory.name, Location.name).join(
        InventoryProduct, InventoryProduct.id == TrackedAsset.product_id).join(
        AssetCategory, AssetCategory.id == InventoryProduct.category_id).join(
        Location, Location.id == TrackedAsset.location_id)
    try:
        count_query = select(func.count(TrackedAsset.id)).join(
            InventoryProduct, InventoryProduct.id == TrackedAsset.product_id).join(
            AssetCategory, AssetCategory.id == InventoryProduct.category_id).join(
            Location, Location.id == TrackedAsset.location_id).where(*clauses)
        total = session.scalar(count_query) or 0
        rows = session.execute(query.where(*clauses).order_by(TrackedAsset.created_at.desc(), TrackedAsset.id)
            .limit(filters.limit).offset(filters.offset)).all()
        items = [AssetRead(id=asset.id, asset_number=asset.asset_number, product_id=asset.product_id,
            category_id=product.category_id, category_name=category_name, product_name=product.name,
            brand=product.brand, model=product.model, location_id=asset.location_id, location_name=location_name,
            lifecycle_status=asset.lifecycle_status, condition=asset.condition)
            for asset, product, category_name, location_name in rows]
        return AssetPage(items=items, total=total, limit=filters.limit, offset=filters.offset)
    except SQLAlchemyError:
        _database_failure(session, "Asset directory is unavailable.")


def get_asset(session: Session, asset_id) -> AssetRead:
    query = (select(TrackedAsset, InventoryProduct, AssetCategory.name, Location.name)
        .join(InventoryProduct, InventoryProduct.id == TrackedAsset.product_id)
        .join(AssetCategory, AssetCategory.id == InventoryProduct.category_id)
        .join(Location, Location.id == TrackedAsset.location_id)
        .where(TrackedAsset.id == asset_id))
    try:
        row = session.execute(query).one_or_none()
        if row is None:
            raise AppError("ASSET_NOT_FOUND", "Asset not found.", 404)
        asset, product, category_name, location_name = row
        return AssetRead(id=asset.id, asset_number=asset.asset_number, product_id=asset.product_id,
            category_id=product.category_id, category_name=category_name, product_name=product.name,
            brand=product.brand, model=product.model, location_id=asset.location_id,
            location_name=location_name, lifecycle_status=asset.lifecycle_status, condition=asset.condition)
    except SQLAlchemyError:
        _database_failure(session, "Asset detail is unavailable.")


def list_quantity_balances(session: Session, *, location_id=None) -> list[QuantityBalanceRead]:
    try:
        query = (select(InventoryBalance, InventoryProduct.name, Location.name)
            .join(InventoryProduct, InventoryProduct.id == InventoryBalance.product_id)
            .join(Location, Location.id == InventoryBalance.location_id))
        if location_id is not None:
            query = query.where(InventoryBalance.location_id == location_id)
        rows = session.execute(query.order_by(InventoryBalance.product_id, InventoryBalance.location_id,
                                                InventoryBalance.unit)).all()
        return [QuantityBalanceRead(product_id=row.product_id, product_name=product_name,
            location_id=row.location_id, location_name=location_name, unit=row.unit,
            on_hand=row.on_hand, reserved=row.reserved,
            quarantined=row.quarantined,
            available=row.on_hand - row.reserved - row.quarantined,
            updated_at=row.updated_at) for row, product_name, location_name in rows]
    except SQLAlchemyError:
        _database_failure(session, "Quantity inventory is unavailable.")


def list_receipts(session: Session, *, limit: int = 25, offset: int = 0, location_id=None) -> ReceiptPage:
    clauses = [Receipt.location_id == location_id] if location_id is not None else []
    try:
        total = session.scalar(select(func.count()).select_from(Receipt).where(*clauses)) or 0
        rows = session.execute(select(Receipt, Location.name).join(Location, Location.id == Receipt.location_id)
            .where(*clauses).order_by(Receipt.received_at.desc(), Receipt.id).limit(limit).offset(offset)).all()
        items = [ReceiptRead(id=row.id, received_at=row.received_at, received_by_id=row.received_by_id,
            location_id=row.location_id, location_name=location_name, supplier_id=row.supplier_id,
            external_reference=row.external_reference) for row, location_name in rows]
        return ReceiptPage(items=items, total=total,
                           limit=limit, offset=offset)
    except SQLAlchemyError:
        _database_failure(session, "Receiving history is unavailable.")


def get_product(session: Session, product_id) -> ProductRead:
    try:
        row = session.execute(select(InventoryProduct, AssetCategory.name).join(
            AssetCategory, AssetCategory.id == InventoryProduct.category_id)
            .where(InventoryProduct.id == product_id)).one_or_none()
        if row is None:
            raise AppError("PRODUCT_NOT_FOUND", "Product not found.", 404)
        product, category_name = row
        return ProductRead(id=product.id, category_id=product.category_id, category_name=category_name,
            sku=product.sku, name=product.name, brand=product.brand, model=product.model,
            specifications=product.specifications, active=product.active)
    except SQLAlchemyError:
        _database_failure(session, "Product detail is unavailable.")


def list_categories(session: Session):
    try:
        return session.execute(select(AssetCategory.id, AssetCategory.code, AssetCategory.name,
                                    AssetCategory.tracking_mode)
            .where(AssetCategory.active.is_(True)).order_by(AssetCategory.name, AssetCategory.id)).all()
    except SQLAlchemyError:
        _database_failure(session, "Asset categories are unavailable.")


def list_locations(session: Session):
    try:
        return session.execute(select(Location.id, Location.code, Location.name)
            .where(Location.active.is_(True)).order_by(Location.name, Location.id)).all()
    except SQLAlchemyError:
        _database_failure(session, "Locations are unavailable.")
