from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum

from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum

class PlanType(str, Enum):
    CAFE = "cafe"
    QUICK_SERVICE = "quick_service"
    FULL_SERVICE = "full_service"
    CUSTOM = "custom"

class Plan:
    THRESHOLDS = {
        PlanType.CAFE: 100_00,
        PlanType.QUICK_SERVICE: 150_00,
        PlanType.FULL_SERVICE: 225_00,
    }
    INITIAL_SETUP_FEE = 45_00
    INITIAL_TOKEN_VALUE = 20_00
    INITIAL_TOKEN_AMOUNT = 100_000
    LOCATION_SETUP_FEE = 45_00

class BaseModel:
    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

    @property
    def timestamp(self) -> str:
        return datetime.utcnow().isoformat()

class PaymentSetup(BaseModel):
    def __init__(self, email: str, status: str = 'pending', tokens: int = 0):
        self.id = f"payment_{email}"
        self.user_id = email  # Add for partition key
        self.type = "payment_setup"
        self.email = email
        self.status = status
        self.tokens = tokens
        self.stripe_customer_id = None
        self.plan_type = None
        self.custom_threshold = None
        self.billing_cycle_start = None
        self.next_billing_date = None
        self.created_at = self.timestamp
        self.updated_at = self.created_at

class Location(BaseModel):
    def __init__(self, user_id: str, name: str, address: str):
        self.id = f"loc_{user_id}_{name}"
        self.user_id = user_id  # Add for partition key
        self.type = "location"
        self.name = name
        self.address = address
        self.is_active = True
        self.current_usage = 0
        self.monthly_fee = Plan.LOCATION_SETUP_FEE
        self.created_at = self.timestamp
        self.updated_at = self.created_at

class Transaction(BaseModel):
    def __init__(
        self, 
        user_id: str,
        amount: int,
        transaction_type: str,
        location_id: Optional[str] = None,
        tokens: int = 0,
        status: str = 'pending',
        stripe_session_id: Optional[str] = None
    ):
        self.id = f"trans_{datetime.utcnow().timestamp()}"
        self.user_id = user_id
        self.type = "transaction"
        self.amount = amount
        self.transaction_type = transaction_type
        self.location_id = location_id
        self.status = status
        self.stripe_session_id = stripe_session_id
        self.tokens_included = tokens
        self.created_at = self.timestamp
        self.updated_at = self.created_at