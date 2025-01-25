import azure.functions as func
import logging
from datetime import datetime, timezone
import asyncio
from shared_code.billing_service import BillingService
from shared_code.constants import MAX_RETRIES, RETRY_DELAY

async def process_location_with_retry(
    billing_service: BillingService,
    location: dict,
    current_time: str,
    user_fees: dict
) -> None:
    """Process a single location with retry logic"""
    user_id = location['user_id']
    location_id = location['id']
    
    for attempt in range(MAX_RETRIES):
        try:
            period_fee = await billing_service.process_location_billing(location, current_time)
            user_fees[user_id] = user_fees.get(user_id, 0) + period_fee
            logging.info(f"Location {location_id} processed: ${period_fee:.4f}")
            return
        except Exception as e:
            logging.error(f"Attempt {attempt + 1} failed for location {location_id}: {str(e)}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY.total_seconds() * (attempt + 1))
            else:
                logging.error(f"All attempts failed for location {location_id}")
                raise

async def process_user_with_retry(
    billing_service: BillingService,
    user_id: str,
    fee: float
) -> None:
    """Process a single user's billing with retry logic"""
    for attempt in range(MAX_RETRIES):
        try:
            await billing_service.process_user_billing(user_id, fee)
            logging.info(f"User {user_id} billing processed: ${fee:.4f}")
            return
        except Exception as e:
            logging.error(f"Attempt {attempt + 1} failed for user {user_id}: {str(e)}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY.total_seconds() * (attempt + 1))
            else:
                logging.error(f"All attempts failed for user {user_id}")
                raise

async def main(mytimer: func.TimerRequest) -> None:
    """Main function for hourly billing updates"""
    start_time = datetime.utcnow()
    utc_timestamp = start_time.replace(microsecond=0).isoformat()
    logging.info(f'Billing update triggered at {utc_timestamp}')
    
    if mytimer.past_due:
        logging.warning('The timer is past due!')
    
    try:
        billing_service = BillingService()
        current_time = datetime.now(timezone.utc).isoformat()
        
        active_locations = billing_service.db_client.get_active_locations()
        total_locations = len(active_locations)
        logging.info(f"Starting to process {total_locations} active locations")
        
        user_fees = {}
        failed_locations = []
        
        for location in active_locations:
            try:
                await process_location_with_retry(
                    billing_service,
                    location,
                    current_time,
                    user_fees
                )
            except Exception as e:
                failed_locations.append(location['id'])
                continue
        
        successful_locations = total_locations - len(failed_locations)
        logging.info(f"Successfully processed {successful_locations}/{total_locations} locations")
        if failed_locations:
            logging.error(f"Failed to process locations: {', '.join(failed_locations)}")
        
        failed_users = []
        for user_id, fee in user_fees.items():
            try:
                await process_user_with_retry(billing_service, user_id, fee)
            except Exception as e:
                failed_users.append(user_id)
                continue
        
        total_users = len(user_fees)
        successful_users = total_users - len(failed_users)
        logging.info(f"Successfully processed {successful_users}/{total_users} users")
        if failed_users:
            logging.error(f"Failed to process users: {', '.join(failed_users)}")
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        logging.info(f'Billing update completed in {duration:.2f} seconds')
        
    except Exception as e:
        logging.error(f"Critical error in billing update: {str(e)}")
        raise