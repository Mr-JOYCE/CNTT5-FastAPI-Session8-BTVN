from datetime import date
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, validator

app = FastAPI(title="API Quản lý Tiến độ Giao hàng của Đối tác (Logistics)")

carriers = [
    {"id": 1, "code": "GHN", "name": "Giao Hang Nhanh", "max_weight_capacity": 5000, "status": "ACTIVE"},
    {"id": 2, "code": "GHTK", "name": "Giao Hang Tiet Kiem", "max_weight_capacity": 3000, "status": "ACTIVE"},
    {"id": 3, "code": "VTP", "name": "Viettel Post", "max_weight_capacity": 10000, "status": "SUSPENDED"}
]

shipments = [
    {
        "id": 1,
        "carrier_id": 1,
        "order_reference": "ORD-2026-001",
        "total_weight": 4200,
        "dispatch_date": "2026-07-01",
        "shift": "MORNING"
    }
]

CarrierStatus = Literal["ACTIVE", "INACTIVE", "SUSPENDED"]
ShipmentShift = Literal["MORNING", "AFTERNOON", "NIGHT"]

def get_next_carrier_id() -> int:
    if not carriers:
        return 1
    return max(carrier["id"] for carrier in carriers) + 1


def get_next_shipment_id() -> int:
    if not shipments:
        return 1
    return max(shipment["id"] for shipment in shipments) + 1


def find_carrier(carrier_id: int) -> Optional[dict]:
    for carrier in carriers:
        if carrier["id"] == carrier_id:
            return carrier
    return None


def is_code_unique(code: str, exclude_id: Optional[int] = None) -> bool:
    normalized = code.strip().upper()
    for carrier in carriers:
        if carrier["code"].upper() == normalized and carrier["id"] != exclude_id:
            return False
    return True


class CarrierBase(BaseModel):
    code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=3)
    max_weight_capacity: int = Field(..., gt=0)
    status: CarrierStatus

    @validator("code")
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @validator("name")
    def clean_name(cls, value: str) -> str:
        return value.strip()


class CarrierCreate(CarrierBase):
    pass


class CarrierUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1)
    name: Optional[str] = Field(None, min_length=3)
    max_weight_capacity: Optional[int] = Field(None, gt=0)
    status: Optional[CarrierStatus] = None

    @validator("code")
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @validator("name")
    def clean_name(cls, value: str) -> str:
        return value.strip()


class Carrier(CarrierBase):
    id: int


class ShipmentBase(BaseModel):
    carrier_id: int
    order_reference: str = Field(..., min_length=1)
    total_weight: int = Field(..., gt=0)
    dispatch_date: str = Field(..., min_length=10, max_length=10)
    shift: ShipmentShift

    @validator("dispatch_date")
    def validate_dispatch_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("dispatch_date must be in YYYY-MM-DD format")
        return value


class ShipmentCreate(ShipmentBase):
    pass


class Shipment(ShipmentBase):
    id: int


@app.post("/carriers", response_model=Carrier)
def create_carrier(carrier: CarrierCreate):
    if not is_code_unique(carrier.code):
        raise HTTPException(status_code=400, detail="Carrier code must be unique")

    new_carrier = carrier.dict()
    new_carrier["id"] = get_next_carrier_id()
    carriers.append(new_carrier)
    return new_carrier


@app.get("/carriers", response_model=List[Carrier])
def list_carriers(
    keyword: Optional[str] = Query(None, description="Search by code or name, case insensitive"),
    status: Optional[CarrierStatus] = Query(None, description="Filter by carrier status"),
    min_weight: Optional[int] = Query(None, ge=0, description="Filter carriers with max_weight_capacity >= min_weight"),
):
    results = carriers

    if keyword:
        lowered = keyword.strip().lower()
        results = [
            carrier for carrier in results
            if lowered in carrier["code"].lower() or lowered in carrier["name"].lower()
        ]

    if status:
        results = [carrier for carrier in results if carrier["status"] == status]

    if min_weight is not None:
        results = [carrier for carrier in results if carrier["max_weight_capacity"] >= min_weight]

    return results


@app.get("/carriers/{carrier_id}", response_model=Carrier)
def get_carrier(carrier_id: int):
    carrier = find_carrier(carrier_id)
    if carrier is None:
        raise HTTPException(status_code=404, detail="Carrier not found")
    return carrier


@app.put("/carriers/{carrier_id}", response_model=Carrier)
def update_carrier(carrier_id: int, carrier_update: CarrierUpdate):
    carrier = find_carrier(carrier_id)
    if carrier is None:
        raise HTTPException(status_code=404, detail="Carrier not found")

    update_data = carrier_update.dict(exclude_unset=True)
    if "code" in update_data and not is_code_unique(update_data["code"], exclude_id=carrier_id):
        raise HTTPException(status_code=400, detail="Carrier code must be unique")

    carrier.update(update_data)
    return carrier


@app.delete("/carriers/{carrier_id}", status_code=204)
def delete_carrier(carrier_id: int):
    carrier = find_carrier(carrier_id)
    if carrier is None:
        raise HTTPException(status_code=404, detail="Carrier not found")

    carriers.remove(carrier)


@app.post("/shipments", response_model=Shipment)
def create_shipment(shipment: ShipmentCreate):
    carrier = find_carrier(shipment.carrier_id)
    if carrier is None:
        raise HTTPException(status_code=400, detail="Carrier does not exist")

    if carrier["status"] != "ACTIVE":
        raise HTTPException(status_code=400, detail="Carrier is not active")

    if shipment.total_weight > carrier["max_weight_capacity"]:
        raise HTTPException(
            status_code=400,
            detail="Shipment weight exceeds carrier max_weight_capacity"
        )

    for existing in shipments:
        if (
            existing["carrier_id"] == shipment.carrier_id
            and existing["dispatch_date"] == shipment.dispatch_date
            and existing["shift"] == shipment.shift
        ):
            raise HTTPException(
                status_code=400,
                detail="Carrier already has a shipment scheduled for this date and shift"
            )

    new_shipment = shipment.dict()
    new_shipment["id"] = get_next_shipment_id()
    shipments.append(new_shipment)
    return new_shipment


@app.get("/shipments", response_model=List[Shipment])
def list_shipments():
    return shipments
