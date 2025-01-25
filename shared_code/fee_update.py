import logging
from shared_code.db_client import CosmosDBClient
import asyncio
from datetime import datetime, timezone

def calculate_hourly_fee(monthly_fee: float) -> float:
    """Calculate hourly fee from monthly fee"""
    daily_fee = monthly_fee / 30
    hourly_fee = daily_fee / 24
    return hourly_fee

async def update_location_fees(db_client: CosmosDBClient, location):
    """Update current_period_fee for a location"""
    try:
        if not location.get('is_active', False):
            logging.info(f"Skipping inactive location {location['id']}")
            return location.get('current_period_fee', 0)

        monthly_fee = location.get('monthly_fee', 0)
        hourly_fee = calculate_hourly_fee(monthly_fee)
        
        current_time = datetime.now(timezone.utc)
        
        current_period_fee = location.get('current_period_fee', 0) + hourly_fee
        
        await db_client.update_location_billing(
            location_id=location['id'],
            current_period_fee=current_period_fee,
            last_billing_update=current_time.isoformat()
        )
        
        logging.info(f"Updated current_period_fee for location {location['id']}: {current_period_fee}")
        return current_period_fee
        
    except Exception as e:
        logging.error(f"Error updating fee for location {location['id']}: {str(e)}")
        raise

async def update_user_pending_fee(db_client: CosmosDBClient, payment_setup):
    """Calculate and update pending fee for a user"""
    try:
        locations = db_client.get_locations(payment_setup['user_id'])
        
        location_fees = await asyncio.gather(*[
            update_location_fees(db_client, location)
            for location in locations
        ])

        total_pending_fee = sum(location_fees)      
        
        await db_client.update_payment_setup_pending_fee(
            email=payment_setup['user_id'],
            pending_fee=total_pending_fee
        )
        
        logging.info(f"Updated pending fee for {payment_setup['user_id']}: {total_pending_fee}")
        
    except Exception as e:
        logging.error(f"Error updating pending fee for {payment_setup['user_id']}: {str(e)}")
        raise