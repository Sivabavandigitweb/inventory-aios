"""Isolated mutation router for approved composition; intentionally unregistered."""
from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.authentication import Principal
from app.core.errors import AppError
from app.models import WorkflowApproval
from app.schemas.inventory import (
    AssetRegistrationSubmit,
    ProductCreate,
    QuantityRegistrationSubmit,
    ReceiptCreate,
    RegistrationApprovalRead,
    RegistrationCandidateRead,
    RegistrationFinalizationRead,
    WorkflowApprovalDecision,
    WriteResult,
)
from app.schemas.transactions import (
    AllocationCreate,
    AllocationRead,
    DisposalCreate,
    QuantityDispositionCreate,
    RepairCompletion,
    RepairRequest,
    ReturnCreate,
    ReturnRead,
)
from app.services.inventory_transactions import (
    allocation_history,
    decide_allocation,
    decide_return,
    issue_allocation,
    record_return,
    request_allocation,
    return_history,
)
from app.services.inventory_writes import (
    InventoryWritePolicy,
    _authorize,
    create_product,
    create_receipt,
    decide_registration_approval,
    finalize_asset_registration,
    finalize_quantity_registration,
    list_registration_approvals,
    list_registration_candidates,
    list_registration_finalizations,
    submit_asset_registration,
    submit_quantity_registration,
)
from app.services.quantity_disposition import (
    decide_quantity_disposition,
    finalize_quantity_disposition,
    request_quantity_disposition,
)
from app.services.workflow_operations import (
    cancel_exit_clearance,
    complete_repair,
    decide_disposal,
    decide_exit_clearance,
    decide_repair,
    finalize_disposal,
    list_disposals,
    list_open_clearances,
    list_repairs,
    open_exit_clearance,
    request_disposal,
    request_repair,
    verify_exit_clearance,
)
from app.services.workflows import complete_exit_clearance


def build_inventory_write_router(
    *,
    principal_dependency: Callable[..., Principal],
    session_dependency: Callable[..., Session],
    write_policy_dependency: Callable[..., InventoryWritePolicy],
    csrf_dependency: Callable[..., object],
) -> APIRouter:
    """Create a protected router only for a separately approved application composition."""
    router = APIRouter(prefix="/inventory", tags=["inventory-writes"])

    def commit(session: Session) -> None:
        try:
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise AppError("DATABASE_UNAVAILABLE", "The inventory write could not be committed.", 503) from None

    @router.post("/assets/{asset_id}/repairs", response_model=WriteResult, status_code=201)
    def repair_request(asset_id: UUID, command: RepairRequest,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        principal: Principal = Depends(principal_dependency), session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> WriteResult:
        repair_id = request_repair(session, asset_id=asset_id, actor_user_id=principal.user_id,
            issue_details=command.issue_details, provider=command.repair_provider,
            idempotency_key=idempotency_key, policy=policy)
        commit(session)
        return WriteResult(id=repair_id, status="pending_approval")

    @router.get("/repairs")
    def repairs_list(principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency), policy: InventoryWritePolicy = Depends(write_policy_dependency)):
        return list_repairs(session, actor_user_id=principal.user_id, policy=policy)

    @router.post("/repairs/{repair_id}/decision", status_code=204)
    def repair_decide(repair_id: UUID, command: WorkflowApprovalDecision,
        principal: Principal = Depends(principal_dependency), session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> None:
        decide_repair(session, repair_id=repair_id, actor_user_id=principal.user_id,
            decision=command.decision, reason_code=command.reason_code, policy=policy)
        commit(session)

    @router.post("/repairs/{repair_id}/complete", status_code=204)
    def repair_complete(repair_id: UUID, command: RepairCompletion,
        principal: Principal = Depends(principal_dependency), session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> None:
        complete_repair(session, repair_id=repair_id, actor_user_id=principal.user_id,
            condition=command.condition, notes=command.notes,
            cost_amount=float(command.cost_amount) if command.cost_amount is not None else None,
            cost_currency=command.cost_currency, policy=policy)
        commit(session)

    @router.post("/assets/{asset_id}/disposals", response_model=WriteResult, status_code=201)
    def disposal_request(asset_id: UUID, command: DisposalCreate,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        principal: Principal = Depends(principal_dependency), session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> WriteResult:
        request_id = request_disposal(session, asset_id=asset_id, actor_user_id=principal.user_id,
            reason_code=command.reason_code, condition=command.condition,
            idempotency_key=idempotency_key, policy=policy)
        commit(session)
        return WriteResult(id=request_id, status="pending_approval")

    @router.get("/disposals")
    def disposals_list(principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency), policy: InventoryWritePolicy = Depends(write_policy_dependency)):
        return list_disposals(session, actor_user_id=principal.user_id, policy=policy)

    @router.post("/disposals/{request_id}/decision", status_code=204)
    def disposal_decide(request_id: UUID, command: WorkflowApprovalDecision,
        principal: Principal = Depends(principal_dependency), session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> None:
        decide_disposal(session, request_id=request_id, actor_user_id=principal.user_id,
            decision=command.decision, reason_code=command.reason_code, policy=policy)
        commit(session)

    @router.post("/disposals/{request_id}/finalize", status_code=204)
    def disposal_finalize(request_id: UUID,
        principal: Principal = Depends(principal_dependency), session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> None:
        finalize_disposal(session, request_id=request_id, actor_user_id=principal.user_id, policy=policy)
        commit(session)

    @router.get("/exit-clearances")
    def exit_clearance_list(principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency), policy: InventoryWritePolicy = Depends(write_policy_dependency)):
        return list_open_clearances(session, policy=policy, actor_user_id=principal.user_id)

    @router.post("/employees/{employee_id}/exit-clearances", response_model=WriteResult, status_code=201)
    def exit_clearance_open(employee_id: UUID, principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency), policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> WriteResult:
        clearance_id = open_exit_clearance(session, employee_id=employee_id,
            actor_user_id=principal.user_id, policy=policy)
        commit(session)
        return WriteResult(id=clearance_id, status="in_progress")

    @router.post("/exit-clearances/{clearance_id}/verify", status_code=204)
    def exit_clearance_verify(clearance_id: UUID, principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency), policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> None:
        verify_exit_clearance(session, clearance_id=clearance_id, actor_user_id=principal.user_id, policy=policy)
        commit(session)

    @router.post("/exit-clearances/{clearance_id}/cancel", status_code=204)
    def exit_clearance_cancel(clearance_id: UUID, principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency), policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> None:
        cancel_exit_clearance(session, clearance_id=clearance_id, actor_user_id=principal.user_id, policy=policy)
        commit(session)

    @router.post("/exit-clearances/{clearance_id}/complete", status_code=204)
    def exit_clearance_complete(clearance_id: UUID, principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency), policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> None:
        complete_exit_clearance(session, clearance_id=clearance_id, actor_user_id=principal.user_id,
            policy=policy)
        commit(session)

    @router.post("/returns/{return_id}/quantity-dispositions", response_model=WriteResult, status_code=201)
    def quantity_disposition_request(return_id: UUID, command: QuantityDispositionCreate,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        principal: Principal = Depends(principal_dependency), session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> WriteResult:
        request_id = request_quantity_disposition(session, return_id=return_id,
            actor_user_id=principal.user_id, quantity=command.quantity, disposition=command.disposition,
            idempotency_key=idempotency_key, policy=policy)
        commit(session)
        return WriteResult(id=request_id, status="pending_approval")

    @router.post("/quantity-dispositions/{request_id}/decision", status_code=204)
    def quantity_disposition_decide(request_id: UUID, command: WorkflowApprovalDecision,
        principal: Principal = Depends(principal_dependency), session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> None:
        decide_quantity_disposition(session, request_id=request_id, actor_user_id=principal.user_id,
            decision=command.decision, reason_code=command.reason_code, policy=policy)
        commit(session)

    @router.post("/quantity-dispositions/{request_id}/finalize", status_code=204)
    def quantity_disposition_finalize(request_id: UUID,
        principal: Principal = Depends(principal_dependency), session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> None:
        finalize_quantity_disposition(session, request_id=request_id, actor_user_id=principal.user_id, policy=policy)
        commit(session)

    @router.get("/registration-candidates", response_model=list[RegistrationCandidateRead])
    def registration_candidates(
        tracking_mode: str = Query(pattern="^(individual|quantity)$"),
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
    ) -> list[RegistrationCandidateRead]:
        _authorize(policy, actor=principal.user_id, capability="receipts:read",
                   entity_type="registration_candidates")
        return list_registration_candidates(session, tracking_mode=tracking_mode)

    @router.get("/registration-approvals", response_model=list[RegistrationApprovalRead])
    def registration_approvals(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=10000),
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
    ) -> list[RegistrationApprovalRead]:
        _authorize(policy, actor=principal.user_id, capability="approvals:read",
                   entity_type="workflow_approval")
        return list_registration_approvals(session, limit=limit, offset=offset)

    @router.get("/workflow-approvals")
    def workflow_approvals(principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency), policy: InventoryWritePolicy = Depends(write_policy_dependency)):
        _authorize(policy, actor=principal.user_id, capability="approvals:read", entity_type="workflow_approval")
        rows = session.execute(select(WorkflowApproval).where(WorkflowApproval.status == "pending")
            .order_by(WorkflowApproval.created_at, WorkflowApproval.id)).scalars().all()
        return [{"id": row.id, "entity_type": row.entity_type, "entity_id": row.entity_id,
                 "required_capability": row.required_capability, "requested_by_id": row.requested_by_id,
                 "created_at": row.created_at} for row in rows]

    @router.post("/workflow-approvals/{approval_id}/decision", status_code=204)
    def workflow_approval_decide(approval_id: UUID, command: WorkflowApprovalDecision,
        principal: Principal = Depends(principal_dependency), session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency)) -> None:
        approval = session.execute(select(WorkflowApproval).where(
            WorkflowApproval.id == approval_id).with_for_update()).scalar_one_or_none()
        if approval is None or approval.status != "pending":
            raise AppError("APPROVAL_UNAVAILABLE", "A pending approval was not found.", 409)
        if approval.entity_type in {"asset_registration", "quantity_registration", "product", "receiving"}:
            decide_registration_approval(session, approval_id=approval_id, actor_user_id=principal.user_id,
                decision=command.decision, reason_code=command.reason_code, policy=policy)
        elif approval.entity_type == "allocation":
            decide_allocation(session, allocation_id=approval.entity_id, actor_user_id=principal.user_id,
                decision=command.decision, reason_code=command.reason_code, policy=policy)
        elif approval.entity_type == "return":
            decide_return(session, return_id=approval.entity_id, actor_user_id=principal.user_id,
                decision=command.decision, reason_code=command.reason_code, policy=policy)
        elif approval.entity_type == "repair":
            decide_repair(session, repair_id=approval.entity_id, actor_user_id=principal.user_id,
                decision=command.decision, reason_code=command.reason_code, policy=policy)
        elif approval.entity_type == "disposal":
            decide_disposal(session, request_id=approval.entity_id, actor_user_id=principal.user_id,
                decision=command.decision, reason_code=command.reason_code, policy=policy)
        elif approval.entity_type == "exit_clearance":
            decide_exit_clearance(session, clearance_id=approval.entity_id, actor_user_id=principal.user_id,
                decision=command.decision, policy=policy)
        elif approval.entity_type == "quantity_disposition":
            decide_quantity_disposition(session, request_id=approval.entity_id, actor_user_id=principal.user_id,
                decision=command.decision, reason_code=command.reason_code, policy=policy)
        else:
            raise AppError("APPROVAL_UNAVAILABLE", "This approval type is not actionable.", 409)
        commit(session)

    @router.get("/registration-finalizations", response_model=list[RegistrationFinalizationRead])
    def registration_finalizations(
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
    ) -> list[RegistrationFinalizationRead]:
        _authorize(policy, actor=principal.user_id, capability="approvals:read",
                   entity_type="registration_finalizations")
        return list_registration_finalizations(session)

    @router.post("/products", response_model=WriteResult, status_code=201)
    def product_create(
        command: ProductCreate,
        response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency),
    ) -> WriteResult:
        result = create_product(session, actor_user_id=principal.user_id,
                                idempotency_key=idempotency_key, command=command, policy=policy)
        commit(session)
        response.status_code = 200 if result.replayed else 201
        return result

    @router.post("/receipts", response_model=WriteResult, status_code=201)
    def receipt_create(
        command: ReceiptCreate,
        response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency),
    ) -> WriteResult:
        result = create_receipt(session, actor_user_id=principal.user_id,
                                idempotency_key=idempotency_key, command=command, policy=policy)
        commit(session)
        response.status_code = 200 if result.replayed else 201
        return result

    @router.post("/receipt-lines/{receipt_line_id}/asset-registration", response_model=WriteResult, status_code=201)
    def asset_registration_submit(
        receipt_line_id: UUID, command: AssetRegistrationSubmit,
        response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency),
    ) -> WriteResult:
        if command.receipt_line_id != receipt_line_id:
            raise AppError("INVALID_REQUEST", "Receipt line identifiers do not match.", 422)
        result = submit_asset_registration(
            session, actor_user_id=principal.user_id, idempotency_key=idempotency_key,
            receipt_line_id=receipt_line_id, asset_number=command.asset_number,
            serial_number=command.serial_number, condition=command.condition, policy=policy,
        )
        commit(session)
        response.status_code = 200 if result.replayed else 201
        return result

    @router.post("/receipt-lines/{receipt_line_id}/quantity-registration", response_model=WriteResult, status_code=201)
    def quantity_registration_submit(
        receipt_line_id: UUID, command: QuantityRegistrationSubmit,
        response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency),
    ) -> WriteResult:
        if command.receipt_line_id != receipt_line_id:
            raise AppError("INVALID_REQUEST", "Receipt line identifiers do not match.", 422)
        result = submit_quantity_registration(
            session, actor_user_id=principal.user_id, idempotency_key=idempotency_key,
            receipt_line_id=receipt_line_id, quantity=command.quantity, unit=command.unit, policy=policy,
        )
        commit(session)
        response.status_code = 200 if result.replayed else 201
        return result

    @router.post("/registration-approvals/{approval_id}/decision", status_code=204)
    def registration_approval_decide(
        approval_id: UUID, command: WorkflowApprovalDecision,
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency),
    ) -> None:
        decide_registration_approval(
            session, approval_id=approval_id, actor_user_id=principal.user_id,
            decision=command.decision, reason_code=command.reason_code, policy=policy,
        )
        commit(session)

    @router.post("/asset-registration-requests/{request_id}/finalize", response_model=WriteResult)
    def asset_registration_finalize(
        request_id: UUID, response: Response,
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency),
    ) -> WriteResult:
        result = finalize_asset_registration(session, request_id=request_id,
            actor_user_id=principal.user_id, policy=policy)
        commit(session)
        response.status_code = 200
        return result

    @router.post("/quantity-registration-requests/{request_id}/finalize", response_model=WriteResult)
    def quantity_registration_finalize(
        request_id: UUID, response: Response,
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency),
    ) -> WriteResult:
        result = finalize_quantity_registration(session, request_id=request_id,
            actor_user_id=principal.user_id, policy=policy)
        commit(session)
        response.status_code = 200
        return result

    @router.get("/allocations", response_model=list[AllocationRead])
    def allocations_list(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=10000),
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
    ) -> list[AllocationRead]:
        return allocation_history(session, actor_user_id=principal.user_id,
                                  policy=policy, limit=limit, offset=offset)

    @router.post("/allocations", response_model=WriteResult, status_code=201)
    def allocation_create(
        command: AllocationCreate, response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency),
    ) -> WriteResult:
        result = request_allocation(session, actor_user_id=principal.user_id,
                                    idempotency_key=idempotency_key, command=command, policy=policy)
        commit(session)
        response.status_code = 200 if result.replayed else 201
        return WriteResult(id=result.id, status=result.status, replayed=result.replayed)

    @router.post("/allocations/{allocation_id}/decision", status_code=204)
    def allocation_decide(
        allocation_id: UUID, command: WorkflowApprovalDecision,
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency),
    ) -> None:
        decide_allocation(session, allocation_id=allocation_id, actor_user_id=principal.user_id,
                          decision=command.decision, reason_code=command.reason_code, policy=policy)
        commit(session)

    @router.post("/allocations/{allocation_id}/issue", status_code=204)
    def allocation_issue(
        allocation_id: UUID,
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency),
    ) -> None:
        issue_allocation(session, allocation_id=allocation_id, actor_user_id=principal.user_id,
                         policy=policy)
        commit(session)

    @router.get("/returns", response_model=list[ReturnRead])
    def returns_list(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=10000),
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
    ) -> list[ReturnRead]:
        return return_history(session, actor_user_id=principal.user_id,
                              policy=policy, limit=limit, offset=offset)

    @router.post("/returns", response_model=WriteResult, status_code=201)
    def returns_record(
        command: ReturnCreate, response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency),
    ) -> WriteResult:
        result = record_return(session, actor_user_id=principal.user_id,
                               idempotency_key=idempotency_key, command=command, policy=policy)
        commit(session)
        response.status_code = 200 if result.replayed else 201
        return WriteResult(id=result.id, status=result.status, replayed=result.replayed)

    @router.post("/returns/{return_id}/decision", status_code=204)
    def returns_decide(
        return_id: UUID, command: WorkflowApprovalDecision,
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(session_dependency),
        policy: InventoryWritePolicy = Depends(write_policy_dependency),
        _csrf: object = Depends(csrf_dependency),
    ) -> None:
        decide_return(session, return_id=return_id, actor_user_id=principal.user_id,
                      decision=command.decision, reason_code=command.reason_code, policy=policy)
        commit(session)

    return router
