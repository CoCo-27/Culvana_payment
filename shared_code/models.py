from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum

PLAN_THRESHOLDS = {
    'cafe': 100_00,
    'quick_service': 150_00,
    'full_service': 225_00
}

class PlanType(str, Enum):
    CAFE = "cafe"
    QUICK_SERVICE = "quick_service"
    FULL_SERVICE = "full_service"
    CUSTOM = "custom"

class Plan:
    INITIAL_SETUP_FEE = 45_00
    INITIAL_TOKEN_VALUE = 20_00
    LOCATION_SETUP_FEE = 45_00
    INITIAL_REWARD = 20

class BaseModel:
    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
    
    @property
    def timestamp(self) -> str:
        return datetime.utcnow().isoformat()

class PaymentSetup(BaseModel):
    def __init__(
        self, 
        email: str, 
        status: str = 'pending', 
        tokens: int = 0,
        stripe_customer_id: str = None,
        plan_type: str = None,
        custom_threshold: int = None,
        num_locations: int = 0,
        pending_fee: int = 0,
        monthly_usage: float = 0,
        payment_methods: List[str] = None,
    ):
        self.id = f"payment_{email}"
        self.user_id = email
        self.type = "payment_setup"
        self.email = email
        self.status = status
        self.tokens = tokens
        self.stripe_customer_id = stripe_customer_id
        self.plan_type = plan_type
        self.custom_threshold = custom_threshold
        self.num_locations = num_locations
        self.pending_fee = pending_fee
        self.created_at = self.timestamp
        self.updated_at = self.created_at
        self.monthly_usage = monthly_usage
        self.payment_methods = payment_methods or []

class Location(BaseModel):
    def __init__(self, user_id: str, name: str, address: str):
        self.id = f"loc_{user_id}_{name}"
        self.user_id = user_id
        self.type = "location"
        self.name = name
        self.address = address
        self.is_active = True
        self.current_usage = 0
        self.monthly_fee = Plan.LOCATION_SETUP_FEE / 100
        self.created_at = self.timestamp
        self.updated_at = self.created_at
        self.billing_periods = []
        self.last_billing_update = self.created_at
        self.current_period_fee = 0
        self.accumulated_fee = 0

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