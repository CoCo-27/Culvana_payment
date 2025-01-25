# shared_code/billing_service.py
from datetime import datetime, timezone
import logging
from .db_client import CosmosDBClient
from .event_publisher import EventGridPublisher
from .constants import (
    DEFAULT_MONTHLY_FEE,
    DEFAULT_THRESHOLD,
    HOURS_IN_DAY,
    DAYS_IN_MONTH
)

class BillingService:
    def __init__(self):
        self.db_client = CosmosDBClient()
        self.event_publisher = EventGridPublisher()
    
    def calculate_hourly_rate(self, monthly_fee: int = DEFAULT_MONTHLY_FEE) -> float:
        return (monthly_fee / DAYS_IN_MONTH) / HOURS_IN_DAY
    
    def calculate_hours_since_update(self, last_update: str) -> float:
        try:
            last_update_time = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
            current_time = datetime.now(timezone.utc)
            delta = current_time - last_update_time
            return delta.total_seconds() / 3600
        except Exception as e:
            logging.error(f"Error calculating hours: {str(e)}")
            return 1.0
    
    async def process_location_billing(self, location: dict, current_time: str) -> float:
        try:
            hours_used = self.calculate_hours_since_update(
                location.get('last_billing_update', location['created_at'])
            )
            hourly_rate = self.calculate_hourly_rate(location.get('monthly_fee', DEFAULT_MONTHLY_FEE))
            period_fee = hourly_rate * hours_used
            
            location['current_period_fee'] = location.get('current_period_fee', 0) + period_fee
            location['last_billing_update'] = current_time
            location['updated_at'] = datetime.utcnow().isoformat()
            
            self.db_client.update_location(location)
            logging.info(f"Updated billing for location {location['id']}: {period_fee:.2f}")
            
            return period_fee
            
        except Exception as e:
            logging.error(f"Error processing location billing: {str(e)}")
            raise
    
    async def process_user_billing(self, user_id: str, new_fee: float):
        try:
            payment_setup = self.db_client.get_payment_setup(user_id)
            if not payment_setup:
                logging.warning(f"No payment setup found for user {user_id}")
                return
            
            current_fee = payment_setup.get('pending_fee', 0)
            total_fee = current_fee + new_fee
            threshold = payment_setup.get('custom_threshold', DEFAULT_THRESHOLD)
            
            payment_setup['pending_fee'] = total_fee
            payment_setup['updated_at'] = datetime.utcnow().isoformat()
            self.db_client.update_payment_setup(payment_setup)
            
            if total_fee > threshold:
                event_published = await self.event_publisher.publish_threshold_event(
                    user_id=user_id,
                    current_fee=total_fee,
                    threshold=threshold
                )
                if event_published:
                    logging.info(f"Threshold event published for user {user_id}")
                else:
                    logging.warning(f"Failed to publish threshold event for user {user_id}")
                    
        except Exception as e:
            logging.error(f"Error processing user billing: {str(e)}")
            raise