import re
from datetime import date
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, validator

app = FastAPI(title="API Quản lý Tài sản Thiết bị Công nghệ (IT Asset Management)")

assets = [
    {"id": 1, "serial_number": "SN-MAC-01", "model": "MacBook Pro M3", "stock_available": 5, "status": "READY"},
    {"id": 2, "serial_number": "SN-DELL-02", "model": "Dell UltraSharp 27", "stock_available": 10, "status": "READY"},
    {"id": 3, "serial_number": "SN-THINK-03", "model": "ThinkPad X1 Carbon", "stock_available": 0, "status": "REPAIRING"}
]

allocations = [
    {
        "id": 1,
        "asset_id": 1,
        "employee_email": "dev.nguyen@company.com",
        "allocated_quantity": 1,
        "start_date": "2026-07-01",
        "duration_months": 12
    }
]

AssetStatus = Literal["READY", "ALLOCATED", "REPAIRING", "SCRAPPED"]

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def get_next_asset_id() -> int:
    if not assets:
        return 1
    return max(asset["id"] for asset in assets) + 1


def get_next_allocation_id() -> int:
    if not allocations:
        return 1
    return max(allocation["id"] for allocation in allocations) + 1


def find_asset(asset_id: int) -> Optional[dict]:
    for asset in assets:
        if asset["id"] == asset_id:
            return asset
    return None


def is_serial_unique(serial_number: str, exclude_id: Optional[int] = None) -> bool:
    normalized = serial_number.strip().upper()
    for asset in assets:
        if asset["serial_number"].upper() == normalized and asset["id"] != exclude_id:
            return False
    return True


class AssetBase(BaseModel):
    serial_number: str = Field(..., min_length=1)
    model: str = Field(..., min_length=2, max_length=255)
    stock_available: int = Field(..., ge=0)
    status: AssetStatus

    @validator("serial_number")
    def normalize_serial(cls, value: str) -> str:
        return value.strip().upper()

    @validator("model")
    def normalize_model(cls, value: str) -> str:
        return value.strip()


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    serial_number: Optional[str] = Field(None, min_length=1)
    model: Optional[str] = Field(None, min_length=2, max_length=255)
    stock_available: Optional[int] = Field(None, ge=0)
    status: Optional[AssetStatus] = None

    @validator("serial_number")
    def normalize_serial(cls, value: str) -> str:
        return value.strip().upper()

    @validator("model")
    def normalize_model(cls, value: str) -> str:
        return value.strip()


class Asset(AssetBase):
    id: int


class AllocationBase(BaseModel):
    asset_id: int
    employee_email: str = Field(..., min_length=1)
    allocated_quantity: int = Field(..., gt=0)
    start_date: str = Field(..., min_length=10, max_length=10)
    duration_months: int = Field(..., ge=1, le=12)

    @validator("employee_email")
    def validate_email(cls, value: str) -> str:
        if not EMAIL_REGEX.match(value.strip()):
            raise ValueError("employee_email must be a valid email address")
        return value.strip().lower()

    @validator("start_date")
    def validate_start_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("start_date must be in YYYY-MM-DD format")
        return value


class AllocationCreate(AllocationBase):
    pass


class Allocation(AllocationBase):
    id: int


@app.post("/assets", response_model=Asset)
def create_asset(asset: AssetCreate):
    if not is_serial_unique(asset.serial_number):
        raise HTTPException(status_code=400, detail="serial_number must be unique")

    new_asset = asset.dict()
    new_asset["id"] = get_next_asset_id()
    assets.append(new_asset)
    return new_asset


@app.get("/assets", response_model=List[Asset])
def list_assets(
    keyword: Optional[str] = Query(None, description="Search by serial_number or model, case insensitive"),
    status: Optional[AssetStatus] = Query(None, description="Filter by asset status"),
    min_stock: Optional[int] = Query(None, ge=0, description="Filter assets with stock_available >= min_stock"),
):
    results = assets

    if keyword:
        lowered = keyword.strip().lower()
        results = [
            asset for asset in results
            if lowered in asset["serial_number"].lower() or lowered in asset["model"].lower()
        ]

    if status:
        results = [asset for asset in results if asset["status"] == status]

    if min_stock is not None:
        results = [asset for asset in results if asset["stock_available"] >= min_stock]

    return results


@app.get("/assets/{asset_id}", response_model=Asset)
def get_asset(asset_id: int):
    asset = find_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@app.put("/assets/{asset_id}", response_model=Asset)
def update_asset(asset_id: int, asset_update: AssetUpdate):
    asset = find_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    update_data = asset_update.dict(exclude_unset=True)
    if "serial_number" in update_data and not is_serial_unique(update_data["serial_number"], exclude_id=asset_id):
        raise HTTPException(status_code=400, detail="serial_number must be unique")

    asset.update(update_data)
    return asset


@app.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: int):
    asset = find_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    assets.remove(asset)


@app.post("/allocations", response_model=Allocation)
def create_allocation(allocation: AllocationCreate):
    asset = find_asset(allocation.asset_id)
    if asset is None:
        raise HTTPException(status_code=400, detail="Asset does not exist")

    if asset["status"] != "READY":
        raise HTTPException(status_code=400, detail="Asset is not ready for allocation")

    if allocation.allocated_quantity > asset["stock_available"]:
        raise HTTPException(status_code=400, detail="allocated_quantity exceeds stock_available")

    new_allocation = allocation.dict()
    new_allocation["id"] = get_next_allocation_id()
    allocations.append(new_allocation)

    asset["stock_available"] -= allocation.allocated_quantity
    return new_allocation


@app.get("/allocations", response_model=List[Allocation])
def list_allocations():
    return allocations
