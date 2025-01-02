import azure.functions as func
import logging
from shared_code.db_client import CosmosDBClient
import asyncio
from datetime import datetime, timezone

def calculate_hourly_fee(monthly_fee: float) -> float:
    """Calculate hourly fee from monthly fee"""
    daily_fee = monthly_fee / 30  # Assuming 30 days per month
    hourly_fee = daily_fee / 24
    return hourly_fee

async def update_location_fees(db_client: CosmosDBClient, location):
    """Update current_period_fee for a location"""
    try:
        # Skip if location is not active
        if not location.get('is_active', False):
            logging.info(f"Skipping inactive location {location['id']}")
            return location.get('current_period_fee', 0)

        # Get the monthly fee and calculate hourly rate
        monthly_fee = location.get('monthly_fee', 0)
        hourly_fee = calculate_hourly_fee(monthly_fee)
        
        # Get current timestamp
        current_time = datetime.now(timezone.utc)
        
        # Get last billing update time
        last_billing_str = location.get('last_billing_update')
        if last_billing_str:
            try:
                last_billing_time = datetime.fromisoformat(last_billing_str.replace('Z', '+00:00'))
            except ValueError:
                last_billing_time = current_time
        else:
            last_billing_time = current_time
        
        # Calculate new current_period_fee
        current_period_fee = location.get('current_period_fee', 0) + hourly_fee
        
        # Update location with new fee
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
        # Get all locations for the user
        locations = db_client.get_locations(payment_setup['user_id'])
        
        # Update all location fees and get new values
        location_fees = await asyncio.gather(*[
            update_location_fees(db_client, location)
            for location in locations
        ])
        
        # Sum up all location fees for total pending fee
        total_pending_fee = sum(location_fees)
        
        # Update payment setup with new pending fee
        await db_client.update_payment_setup_pending_fee(
            email=payment_setup['user_id'],
            pending_fee=total_pending_fee
        )
        
        logging.info(f"Updated pending fee for {payment_setup['user_id']}: {total_pending_fee}")
        
    except Exception as e:
        logging.error(f"Error updating pending fee for {payment_setup['user_id']}: {str(e)}")
        raise

async def main(mytimer: func.TimerRequest) -> None:
    """Timer trigger function that runs every hour"""
    try:
        logging.info('Starting hourly fee update process')
        
        # Initialize database client
        db_client = CosmosDBClient()
        
        # Query all payment setups
        query = "SELECT * FROM c WHERE c.type = 'payment_setup'"
        payment_setups = list(db_client.payment_container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        
        # Update fees for all users
        tasks = [
            update_user_pending_fee(db_client, payment_setup)
            for payment_setup in payment_setups
        ]
        
        # Run all updates concurrently
        await asyncio.gather(*tasks)
        
        logging.info(f'Successfully updated fees for {len(payment_setups)} users')
        
    except Exception as e:
        logging.error(f'Error in fee update process: {str(e)}')
        raise