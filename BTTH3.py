from datetime import date
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field, validator

app = FastAPI(title="API Hệ thống Đặt Chỗ Không Gian Làm Việc (Co-working Space)")


desks = [
    {"id": 1, "desk_number": "DSK-A-01", "zone": "Zone A - Quiet Space", "price_per_day": 150000.0, "status": "AVAILABLE"},
    {"id": 2, "desk_number": "DSK-B-02", "zone": "Zone B - Creative", "price_per_day": 200000.0, "status": "AVAILABLE"},
    {"id": 3, "desk_number": "DSK-C-03", "zone": "Zone C - Panoramic", "price_per_day": 250000.0, "status": "MAINTENANCE"}
]

bookings = [
    {
        "id": 1,
        "desk_id": 1,
        "customer_name": "Nguyen Van A",
        "booking_date": "2026-07-01",
        "payment_status": "PAID"
    }
]

DeskStatus = Literal["AVAILABLE", "UNAVAILABLE", "MAINTENANCE"]
PaymentStatus = Literal["PENDING", "PAID", "CANCELLED"]


def get_next_desk_id() -> int:
    if not desks:
        return 1
    return max(desk["id"] for desk in desks) + 1


def get_next_booking_id() -> int:
    if not bookings:
        return 1
    return max(booking["id"] for booking in bookings) + 1


def find_desk(desk_id: int) -> Optional[dict]:
    for desk in desks:
        if desk["id"] == desk_id:
            return desk
    return None


def is_desk_number_unique(desk_number: str, exclude_id: Optional[int] = None) -> bool:
    normalized = desk_number.strip().upper()
    for desk in desks:
        if desk["desk_number"].upper() == normalized and desk["id"] != exclude_id:
            return False
    return True


class DeskBase(BaseModel):
    desk_number: str = Field(..., min_length=1)
    zone: str = Field(..., min_length=1)
    price_per_day: float = Field(..., gt=0)
    status: DeskStatus

    @validator("desk_number")
    def normalize_desk_number(cls, value: str) -> str:
        return value.strip().upper()

    @validator("zone")
    def normalize_zone(cls, value: str) -> str:
        return value.strip()


class DeskCreate(DeskBase):
    pass


class DeskUpdate(BaseModel):
    desk_number: Optional[str] = Field(None, min_length=1)
    zone: Optional[str] = Field(None, min_length=1)
    price_per_day: Optional[float] = Field(None, gt=0)
    status: Optional[DeskStatus] = None

    @validator("desk_number")
    def normalize_desk_number(cls, value: str) -> str:
        return value.strip().upper()

    @validator("zone")
    def normalize_zone(cls, value: str) -> str:
        return value.strip()


class Desk(DeskBase):
    id: int


class BookingBase(BaseModel):
    desk_id: int
    customer_name: str = Field(..., min_length=1)
    booking_date: str = Field(..., min_length=10, max_length=10)
    payment_status: PaymentStatus

    @validator("customer_name")
    def normalize_customer_name(cls, value: str) -> str:
        return value.strip()

    @validator("booking_date")
    def validate_booking_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("booking_date must be in YYYY-MM-DD format")
        return value


class BookingCreate(BookingBase):
    pass


class Booking(BookingBase):
    id: int


@app.post("/desks", response_model=Desk)
def create_desk(desk: DeskCreate):
    if not is_desk_number_unique(desk.desk_number):
        raise HTTPException(status_code=400, detail="desk_number must be unique")

    new_desk = desk.dict()
    new_desk["id"] = get_next_desk_id()
    desks.append(new_desk)
    return new_desk


@app.get("/desks", response_model=List[Desk])
def list_desks(
    zone_keyword: Optional[str] = Query(None, description="Search by zone keyword"),
    max_price: Optional[float] = Query(None, gt=0, description="Filter desks with price_per_day <= max_price"),
    status: Optional[DeskStatus] = Query(None, description="Filter by desk status"),
):
    results = desks

    if zone_keyword:
        lowered = zone_keyword.strip().lower()
        results = [desk for desk in results if lowered in desk["zone"].lower()]

    if max_price is not None:
        results = [desk for desk in results if desk["price_per_day"] <= max_price]

    if status:
        results = [desk for desk in results if desk["status"] == status]

    return results


@app.get("/desks/{desk_id}", response_model=Desk)
def get_desk(desk_id: int):
    desk = find_desk(desk_id)
    if desk is None:
        raise HTTPException(status_code=404, detail="Desk not found")
    return desk


@app.put("/desks/{desk_id}", response_model=Desk)
def update_desk(desk_id: int, desk_update: DeskUpdate):
    desk = find_desk(desk_id)
    if desk is None:
        raise HTTPException(status_code=404, detail="Desk not found")

    update_data = desk_update.dict(exclude_unset=True)
    if "desk_number" in update_data and not is_desk_number_unique(update_data["desk_number"], exclude_id=desk_id):
        raise HTTPException(status_code=400, detail="desk_number must be unique")

    desk.update(update_data)
    return desk


@app.delete("/desks/{desk_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_desk(desk_id: int):
    desk = find_desk(desk_id)
    if desk is None:
        raise HTTPException(status_code=404, detail="Desk not found")
    desks.remove(desk)


@app.post("/bookings", response_model=Booking, status_code=status.HTTP_201_CREATED)
def create_booking(booking: BookingCreate):
    desk = find_desk(booking.desk_id)
    if desk is None:
        raise HTTPException(status_code=400, detail="Desk does not exist")

    if desk["status"] != "AVAILABLE":
        raise HTTPException(status_code=400, detail="Desk is not available for booking")

    if any(
        existing["desk_id"] == booking.desk_id and existing["booking_date"] == booking.booking_date
        for existing in bookings
    ):
        raise HTTPException(
            status_code=400,
            detail="This desk is already booked for the selected date"
        )

    new_booking = booking.dict()
    new_booking["id"] = get_next_booking_id()
    bookings.append(new_booking)
    return new_booking


@app.get("/bookings", response_model=List[Booking])
def list_bookings():
    return bookings
